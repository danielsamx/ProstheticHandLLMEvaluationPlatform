"""Execution orchestrator - one independent experiment, start to finish.

    resolve configuration
        -> assemble the three-block prompt
        -> call LiteLLM
        -> validate (7 stages)
        -> compute metrics
        -> persist everything
        -> emit the simulator frame (only if validation passed)

There is no conversation state anywhere in this path.  Each call starts from a
frozen prompt and a single EMG window, which is precisely what makes the
comparison between models causal rather than anecdotal.
"""

from __future__ import annotations

import traceback
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.hand_spec import Handedness, get_limit_profile
from app.models.emg import EmgWindowRecord
from app.models.enums import ErrorCategory, ExecutionStatus
from app.models.experiment import Execution
from app.models.llm import LlmModel, SamplingConfiguration
from app.models.metrics import ExecutionMetric, SimulatorMovement
from app.models.prompts import (
    DynamicPromptTemplate,
    SystemPromptVersion,
    TechnicalContextVersion,
)
from app.models.validation import ExecutionError, ValidationIssueRecord, ValidationResult
from app.prompts.builder import build_prompt
from app.schemas.emg import EmgWindow
from app.schemas.llm_output import llm_json_schema
from app.services import emg_service
from app.services.llm_service import LlmCallError, LlmCallResult, call_llm
from app.services.metrics_service import compute_metrics
from app.validation.pipeline import validate_response
from app.validation.results import ValidationReport

logger = get_logger(__name__)


class ExecutionRequestError(ValueError):
    """The requested configuration could not be resolved."""


async def run_execution(
    session: AsyncSession,
    *,
    sampling_configuration_id: uuid.UUID,
    window: EmgWindow,
    handedness: Handedness = Handedness.RIGHT,
    system_prompt_version_id: uuid.UUID | None = None,
    technical_context_version_id: uuid.UUID | None = None,
    dynamic_prompt_template_id: uuid.UUID | None = None,
    system_prompt_override: str | None = None,
    technical_context_override: str | None = None,
    dynamic_template_override: str | None = None,
    limit_profile_id: str | None = None,
    experiment_id: uuid.UUID | None = None,
    triggered_by_id: uuid.UUID | None = None,
    experiment_type: str = "single_inference",
    subject_ref: str | None = None,
    subject_notes: str | None = None,
    extra_parameters: dict[str, Any] | None = None,
    merge_context_into_system: bool = True,
    repetition_index: int = 0,
    repetition_group: str | None = None,
    emg_session_id: str | None = None,
    emg_sequence: int | None = None,
) -> Execution:
    """Run one execution and persist the complete scientific record."""

    # ── 1. Resolve configuration ────────────────────────────────────────────
    config = await session.get(SamplingConfiguration, sampling_configuration_id)
    if config is None:
        raise ExecutionRequestError(
            f"Sampling configuration {sampling_configuration_id} does not exist."
        )
    model: LlmModel | None = config.model
    if model is None or model.provider is None:
        raise ExecutionRequestError("Sampling configuration is not bound to a usable model.")
    provider = model.provider

    system_version = await _resolve_prompt(
        session, SystemPromptVersion, system_prompt_version_id
    )
    context_version = await _resolve_prompt(
        session, TechnicalContextVersion, technical_context_version_id
    )
    template_version = await _resolve_prompt(
        session, DynamicPromptTemplate, dynamic_prompt_template_id
    )

    profile = get_limit_profile(
        limit_profile_id
        or (context_version.limit_profile if context_version else None)
        or settings.default_limit_profile
    )

    # ── 2. Persist the stimulus ─────────────────────────────────────────────
    emg_record: EmgWindowRecord = await emg_service.persist_window(
        session, window, subject_ref=subject_ref,
        session_id=emg_session_id, sequence=emg_sequence,
    )

    # ── 3. Assemble the prompt (never authored by hand) ─────────────────────
    assembled = build_prompt(
        window,
        handedness=handedness,
        system_prompt=system_prompt_override
        or (system_version.content if system_version else None),
        technical_context=technical_context_override
        or (context_version.content if context_version else None),
        dynamic_template=dynamic_template_override
        or (template_version.content if template_version else None),
        limit_profile=profile,
        experiment_type=experiment_type,
        subject_ref=subject_ref,
        subject_notes=subject_notes,
        extra_parameters=extra_parameters,
        merge_context_into_system=merge_context_into_system,
    )

    execution = Execution(
        experiment_id=experiment_id,
        triggered_by_id=triggered_by_id,
        repetition_index=repetition_index,
        llm_model_id=model.id,
        sampling_configuration_id=config.id,
        system_prompt_version_id=system_version.id if system_version else None,
        technical_context_version_id=context_version.id if context_version else None,
        dynamic_prompt_template_id=template_version.id if template_version else None,
        emg_window_id=emg_record.id,
        model_snapshot=_model_snapshot(model, provider, config),
        litellm_model=f"{provider.litellm_prefix}/{model.model_key}",
        provider_slug=provider.slug,
        handedness=handedness.value,
        limit_profile=profile.id.value,
        experiment_type=experiment_type,
        system_prompt_text=assembled.system_prompt,
        technical_context_text=assembled.technical_context,
        dynamic_prompt_text=assembled.dynamic_prompt,
        messages_json=assembled.messages,
        system_prompt_sha256=assembled.system_prompt_sha256,
        technical_context_sha256=assembled.technical_context_sha256,
        dynamic_prompt_sha256=assembled.dynamic_prompt_sha256,
        frozen_context_sha256=assembled.frozen_context_sha256,
        full_prompt_sha256=assembled.full_prompt_sha256,
        status=ExecutionStatus.RUNNING.value,
        started_at=datetime.now(timezone.utc),
    )
    session.add(execution)
    await session.flush()

    # ── 4. Invoke the model ─────────────────────────────────────────────────
    call: LlmCallResult | None = None
    try:
        call = await call_llm(
            messages=assembled.messages,
            litellm_prefix=provider.litellm_prefix,
            model_key=model.model_key,
            api_base=provider.api_base,
            is_local=provider.is_local,
            sampling=config.to_litellm_kwargs(),
            response_format_mode=_response_format_mode(config, model),
            json_schema=llm_json_schema() if model.supports_json_schema else None,
        )
    except LlmCallError as exc:
        execution.status = (
            ExecutionStatus.TIMEOUT.value
            if exc.error_type == "Timeout"
            else ExecutionStatus.PROVIDER_ERROR.value
        )
        execution.finished_at = datetime.now(timezone.utc)
        execution.validation_passed = False
        session.add(
            ExecutionError(
                execution_id=execution.id,
                category=ErrorCategory.PROVIDER.value,
                error_type=exc.error_type,
                message=str(exc),
                provider_status_code=exc.status_code,
                provider_error_code=exc.provider_code,
                is_retryable=exc.retryable,
                context={"model": execution.litellm_model, "provider": provider.slug},
            )
        )
        await session.flush()
        logger.error(
            "execution_provider_error",
            extra={"execution_id": str(execution.id), "model": execution.litellm_model,
                   "error_type": exc.error_type},
        )
        return execution
    except Exception as exc:  # platform bug - never silently swallowed
        execution.status = ExecutionStatus.PROVIDER_ERROR.value
        execution.finished_at = datetime.now(timezone.utc)
        execution.validation_passed = False
        session.add(
            ExecutionError(
                execution_id=execution.id,
                category=ErrorCategory.INTERNAL.value,
                error_type=type(exc).__name__,
                message=str(exc),
                traceback=traceback.format_exc(limit=20),
            )
        )
        await session.flush()
        raise

    execution.finished_at = datetime.now(timezone.utc)
    execution.raw_response = call.content
    execution.finish_reason = call.finish_reason
    execution.provider_response_id = call.response_id
    execution.latency_ms = call.latency_ms
    execution.prompt_tokens = call.prompt_tokens
    execution.completion_tokens = call.completion_tokens
    execution.total_tokens = call.total_tokens
    execution.cost_usd = call.cost_usd
    execution.tokens_per_second = call.tokens_per_second

    # ── 5. Validate before anything touches the simulator ───────────────────
    report: ValidationReport = validate_response(
        call.content, expected_hand=handedness, limit_profile=profile
    )
    execution.validation_passed = report.passed
    execution.status = (
        ExecutionStatus.COMPLETED.value if report.passed
        else ExecutionStatus.VALIDATION_FAILED.value
    )
    if report.parsed_command is not None:
        execution.parsed_response = report.parsed_command.model_dump(mode="json")

    result_row = ValidationResult(
        execution_id=execution.id,
        passed=report.passed,
        limit_profile=report.limit_profile,
        failed_stage=report.failed_stage.value if report.failed_stage else None,
        stages_completed=[s.value for s in report.stages_completed],
        error_count=len(report.errors),
        warning_count=len(report.warnings),
        normalised_serial=report.normalised_serial,
        duration_ms=report.resolved_pose.duration_ms if report.resolved_pose else None,
    )
    session.add(result_row)
    await session.flush()

    for issue in report.issues:
        session.add(
            ValidationIssueRecord(
                validation_result_id=result_row.id,
                stage=issue.stage.value,
                code=issue.code,
                severity=issue.severity.value,
                message=issue.message,
                field_path=issue.field_path,
                context=issue.context,
            )
        )

    # A failed validation is a first-class error record, categorised by the
    # stage that rejected it, so failure modes are queryable per model.
    for issue in report.errors:
        session.add(
            ExecutionError(
                execution_id=execution.id,
                category=_stage_to_category(issue.stage.value),
                error_type=issue.code,
                message=issue.message,
                is_retryable=False,
                context={"stage": issue.stage.value, "field_path": issue.field_path},
            )
        )

    # ── 6. Metrics ──────────────────────────────────────────────────────────
    session.add(
        ExecutionMetric(
            execution_id=execution.id,
            **compute_metrics(
                report=report, call=call, window=window,
                handedness=handedness, profile=profile,
                repetition_group=repetition_group,
            ),
        )
    )

    # ── 7. Simulator frame - ONLY when every stage passed ───────────────────
    if report.passed and report.resolved_pose is not None:
        pose = report.resolved_pose
        session.add(
            SimulatorMovement(
                execution_id=execution.id,
                handedness=pose.handedness.value,
                limit_profile=pose.limit_profile,
                source=pose.source,
                serial_command=report.normalised_serial,
                actuator_positions=pose.actuator_positions,
                actuator_normalised=pose.actuator_normalised,
                joint_angles=[
                    {
                        "joint_id": j.joint_id, "digit": j.digit,
                        "joint_type": j.joint_type,
                        "angle_deg": round(j.angle_deg, 3),
                        "normalised": round(j.normalised, 4),
                        "driven_by": j.driven_by,
                    }
                    for j in pose.joints
                ],
                duration_ms=pose.duration_ms,
                was_rendered=False,
            )
        )
        execution.simulator_executed = True

    config.use_count += 1
    await session.flush()

    logger.info(
        "execution_finished",
        extra={
            "execution_id": str(execution.id),
            "model": execution.litellm_model,
            "status": execution.status,
            "latency_ms": execution.latency_ms,
            "validation_passed": report.passed,
            "failed_stage": result_row.failed_stage,
        },
    )
    return execution


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════


async def _resolve_prompt(session: AsyncSession, model_cls, artefact_id):
    """Fetch an explicit version, else the active one, else the system default."""
    if artefact_id is not None:
        row = await session.get(model_cls, artefact_id)
        if row is None:
            raise ExecutionRequestError(
                f"{model_cls.__name__} {artefact_id} does not exist."
            )
        return row
    result = await session.execute(
        select(model_cls).where(model_cls.is_active.is_(True)).limit(1)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        return row
    result = await session.execute(
        select(model_cls).where(model_cls.is_system_default.is_(True)).limit(1)
    )
    return result.scalar_one_or_none()


def _model_snapshot(model: LlmModel, provider, config: SamplingConfiguration) -> dict[str, Any]:
    """Immutable copy of the run conditions, independent of later edits."""
    return {
        "provider": {
            "slug": provider.slug,
            "display_name": provider.display_name,
            "litellm_prefix": provider.litellm_prefix,
            "api_base": provider.api_base,
            "is_local": provider.is_local,
        },
        "model": {
            "model_key": model.model_key,
            "display_name": model.display_name,
            "family": model.family,
            "parameter_count_b": model.parameter_count_b,
            "quantisation": model.quantisation,
            "context_window": model.context_window,
            "supports_json_mode": model.supports_json_mode,
            "supports_json_schema": model.supports_json_schema,
            "supports_seed": model.supports_seed,
        },
        "sampling": {
            "name": config.name,
            "temperature": config.temperature,
            "top_p": config.top_p,
            "top_k": config.top_k,
            "max_tokens": config.max_tokens,
            "seed": config.seed,
            "frequency_penalty": config.frequency_penalty,
            "presence_penalty": config.presence_penalty,
            "stop_sequences": config.stop_sequences,
            "response_format": config.response_format,
            "extra_params": config.extra_params,
        },
    }


def _response_format_mode(config: SamplingConfiguration, model: LlmModel) -> str:
    """Downgrade gracefully when the runtime cannot enforce a format.

    LM Studio supports ``json_schema`` for most GGUF models through its
    structured-output layer, but the capability is per-model, so we only ask for
    what the catalogue says is available.
    """
    requested = config.response_format or "json_object"
    if requested == "json_schema" and not model.supports_json_schema:
        requested = "json_object"
    if requested == "json_object" and not model.supports_json_mode:
        requested = "text"
    return requested


def _stage_to_category(stage: str) -> str:
    mapping = {
        "parse": ErrorCategory.PARSE.value,
        "schema": ErrorCategory.SCHEMA.value,
        "protocol": ErrorCategory.PROTOCOL.value,
        "consistency": ErrorCategory.PROTOCOL.value,
        "range": ErrorCategory.RANGE.value,
        "kinematic": ErrorCategory.KINEMATIC.value,
        "safety": ErrorCategory.SAFETY.value,
    }
    return mapping.get(stage, ErrorCategory.INTERNAL.value)
