"""Reconstruct a past experiment in full.

The platform's central promise is that any recorded run can be replayed and
audited. This module turns that promise into a single payload and — just as
importantly — states honestly when it cannot be kept, by listing what is missing
instead of returning a record that merely looks complete.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit import AuditLog
from app.models.emg import EmgWindowRecord
from app.models.experiment import Execution, Experiment
from app.models.project import Project
from app.models.validation import ValidationResult
from app.schemas.governance import AuditLogOut, ExecutionLogOut, TraceabilityRecord

#: Without these an execution cannot be faithfully replayed.
REPRODUCIBILITY_REQUIREMENTS: tuple[tuple[str, str], ...] = (
    ("system_prompt_text", "system prompt text"),
    ("technical_context_text", "technical context text"),
    ("dynamic_prompt_text", "dynamic prompt text"),
    ("litellm_model", "model identity"),
    ("model_snapshot", "model and decoding snapshot"),
    ("emg_window_id", "EMG stimulus"),
    ("full_prompt_sha256", "prompt digest"),
)


async def build_record(session: AsyncSession, execution_id: uuid.UUID) -> TraceabilityRecord | None:
    """Assemble the complete provenance of one execution."""
    stmt = (
        select(Execution)
        .where(Execution.id == execution_id)
        .options(
            selectinload(Execution.validation_result).selectinload(ValidationResult.issues),
            selectinload(Execution.metrics),
            selectinload(Execution.movement),
            selectinload(Execution.errors),
            selectinload(Execution.logs),
        )
    )
    execution = (await session.execute(stmt)).scalars().unique().one_or_none()
    if execution is None:
        return None

    missing = [
        label
        for attribute, label in REPRODUCIBILITY_REQUIREMENTS
        if not getattr(execution, attribute, None)
    ]

    experiment = (
        await session.get(Experiment, execution.experiment_id)
        if execution.experiment_id else None
    )
    project = (
        await session.get(Project, execution.project_id) if execution.project_id else None
    )
    window = (
        await session.get(EmgWindowRecord, execution.emg_window_id)
        if execution.emg_window_id else None
    )

    audit_rows = (
        await session.execute(
            select(AuditLog)
            .where(AuditLog.entity_type == "execution", AuditLog.entity_id == execution.id)
            .order_by(AuditLog.created_at)
        )
    ).scalars().all()

    return TraceabilityRecord(
        execution_id=execution.id,
        executed_at=execution.created_at,
        status=execution.status,
        reproducible=not missing,
        missing_for_reproduction=missing,

        actor={
            "user_id": str(execution.triggered_by_id) if execution.triggered_by_id else None,
            "email": execution.triggered_by_email,
        },
        origin={
            "client_ip": execution.client_ip,
            "browser": execution.browser,
            "operating_system": execution.operating_system,
            "device_type": execution.device_type,
            "user_agent": execution.user_agent,
            "session_id": execution.session_id,
            "request_id": execution.request_id,
            "app_version": execution.app_version,
        },

        project=(
            {"id": str(project.id), "name": project.name, "slug": project.slug}
            if project else None
        ),
        experiment=(
            {
                "id": str(experiment.id),
                "name": experiment.name,
                "hypothesis": experiment.hypothesis,
                "repetition_index": execution.repetition_index,
            }
            if experiment else None
        ),

        prompt={
            "system_prompt": execution.system_prompt_text,
            "technical_context": execution.technical_context_text,
            "dynamic_prompt": execution.dynamic_prompt_text,
            "messages": execution.messages_json,
            "template_ids": {
                "system_prompt_version_id": _uuid(execution.system_prompt_version_id),
                "technical_context_version_id": _uuid(execution.technical_context_version_id),
                "dynamic_prompt_template_id": _uuid(execution.dynamic_prompt_template_id),
            },
            "digests": {
                "system_prompt": execution.system_prompt_sha256,
                "technical_context": execution.technical_context_sha256,
                "dynamic_prompt": execution.dynamic_prompt_sha256,
                # Two runs sharing this saw identical frozen conditions, which is
                # what makes their comparison meaningful.
                "frozen_context": execution.frozen_context_sha256,
                "full_prompt": execution.full_prompt_sha256,
            },
        },

        model={
            "litellm_model": execution.litellm_model,
            "provider": execution.provider_slug,
            "model_key": execution.model_key,
            "api_base": execution.api_base,
            "api_flavour": execution.api_flavour,
            "snapshot": execution.model_snapshot,
        },

        parameters={
            "temperature": execution.temperature,
            "top_p": execution.top_p,
            "top_k": execution.top_k,
            "max_tokens": execution.max_tokens,
            "seed": execution.seed,
            "frequency_penalty": execution.frequency_penalty,
            "presence_penalty": execution.presence_penalty,
            "stop_sequences": execution.stop_sequences,
            "response_format": execution.response_format,
            "reasoning_mode": execution.reasoning_mode,
            "custom_parameters": execution.custom_parameters,
            # A knob the runtime ignored makes a run look reproducible when it
            # is not, so it is reported alongside what was requested.
            "dropped_by_runtime": execution.dropped_parameters,
            "limit_profile": execution.limit_profile,
            "handedness": execution.handedness,
        },

        stimulus=(
            {
                "emg_window_id": str(window.id),
                "checksum": window.checksum,
                "source_mode": window.source_mode,
                "sample_count": window.sample_count,
                "sample_rate_hz": window.sample_rate_hz,
                "window_ms": window.window_ms,
                "mean_rms": window.mean_rms,
                "ground_truth_gesture": window.ground_truth_gesture,
                "subject_ref": window.subject_ref,
                "features": window.features,
            }
            if window else {}
        ),

        response={
            "raw": execution.raw_response,
            "parsed": execution.parsed_response,
            "finish_reason": execution.finish_reason,
            "provider_response_id": execution.provider_response_id,
        },

        performance={
            "latency_ms": execution.latency_ms,
            "time_to_first_token_ms": execution.time_to_first_token_ms,
            "prompt_tokens": execution.prompt_tokens,
            "completion_tokens": execution.completion_tokens,
            "total_tokens": execution.total_tokens,
            "tokens_per_second": execution.tokens_per_second,
            "cost_usd": float(execution.cost_usd or 0),
            "started_at": execution.started_at,
            "finished_at": execution.finished_at,
        },

        validation=(
            {
                "passed": execution.validation_result.passed,
                "failed_stage": execution.validation_result.failed_stage,
                "stages_completed": execution.validation_result.stages_completed,
                "error_count": execution.validation_result.error_count,
                "warning_count": execution.validation_result.warning_count,
                "normalised_serial": execution.validation_result.normalised_serial,
                "issues": [
                    {
                        "stage": i.stage, "code": i.code, "severity": i.severity,
                        "message": i.message, "field_path": i.field_path,
                    }
                    for i in execution.validation_result.issues
                ],
            }
            if execution.validation_result else None
        ),

        metrics=(
            {
                column.name: getattr(execution.metrics, column.name)
                for column in execution.metrics.__table__.columns
                if column.name not in ("id", "execution_id", "created_at", "updated_at")
            }
            if execution.metrics else None
        ),

        movement=(
            {
                "serial_command": execution.movement.serial_command,
                "actuator_positions": execution.movement.actuator_positions,
                "actuator_normalised": execution.movement.actuator_normalised,
                "joint_angles": execution.movement.joint_angles,
                "duration_ms": execution.movement.duration_ms,
                "source": execution.movement.source,
                "was_rendered": execution.movement.was_rendered,
                "dispatched_to_hardware": execution.movement.dispatched_to_hardware,
            }
            if execution.movement else None
        ),

        errors=[
            {
                "category": e.category, "error_type": e.error_type, "message": e.message,
                "provider_status_code": e.provider_status_code,
                "is_retryable": e.is_retryable,
            }
            for e in execution.errors
        ],
        logs=[ExecutionLogOut.model_validate(log) for log in execution.logs],
        audit=[AuditLogOut.model_validate(row) for row in audit_rows],
    )


def _uuid(value: Any) -> str | None:
    return str(value) if value else None
