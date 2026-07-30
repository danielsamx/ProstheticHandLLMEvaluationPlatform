"""Running and retrieving executions - the 'Run Evaluation' path."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.session import get_session
from app.models.experiment import Execution
from app.models.metrics import ExecutionMetric
from app.models.prompt_configuration import PromptConfiguration
from app.models.validation import ValidationIssueRecord, ValidationResult
from app.schemas.api import (
    ExecutionOut,
    ConfigurationModelResult,
    ExecutionStats,
    ModelSummary,
    PromptConfigurationOut,
    RunExecutionIn,
    RunExecutionOut,
)
from app.models.movement_log import MovementSource
from app.services import movement_service
from app.services.execution_service import ExecutionRequestError, run_execution
from app.services.metrics_service import aggregate_determinism
from app.ws.emg_stream import broadcast_movement

router = APIRouter(prefix="/executions", tags=["executions"])


@router.post("/run", response_model=RunExecutionOut, status_code=status.HTTP_201_CREATED)
async def run(payload: RunExecutionIn, session: AsyncSession = Depends(get_session)):
    """Execute one independent experiment (optionally repeated N times).

    Repetitions share an identical prompt and configuration; the only thing that
    varies is the model's own sampling, which is exactly what the determinism
    statistics measure.
    """
    if payload.repetitions > settings.max_batch_executions:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"repetitions exceeds the configured maximum ({settings.max_batch_executions}).",
        )

    repetition_group = str(uuid.uuid4()) if payload.repetitions > 1 else None
    executions: list[Execution] = []

    for index in range(payload.repetitions):
        try:
            execution = await run_execution(
                session,
                sampling_configuration_id=payload.sampling_configuration_id,
                window=payload.window,
                handedness=payload.handedness,
                system_prompt_version_id=payload.system_prompt_version_id,
                technical_context_version_id=payload.technical_context_version_id,
                emg_context_version_id=payload.emg_context_version_id,
                dynamic_prompt_template_id=payload.dynamic_prompt_template_id,
                system_prompt_override=payload.system_prompt_override,
                technical_context_override=payload.technical_context_override,
                emg_context_override=payload.emg_context_override,
                dynamic_template_override=payload.dynamic_template_override,
                dynamic_content=payload.dynamic_content,
                matrix_max_rows=payload.matrix_max_rows,
                expected_serial_command=payload.expected_serial_command,
                limit_profile_id=payload.limit_profile.value if payload.limit_profile else None,
                experiment_id=payload.experiment_id,
                experiment_type=payload.experiment_type,
                subject_ref=payload.subject_ref,
                subject_notes=payload.subject_notes,
                extra_parameters=payload.extra_parameters,
                merge_context_into_system=payload.merge_context_into_system,
                repetition_index=index,
                repetition_group=repetition_group,
            )
        except ExecutionRequestError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
        executions.append(execution)

    await session.flush()

    # Push the first successful movement to any attached simulator client, and
    # log the transmission. The log is what answers "did the hand receive this?"
    # — a resolved pose is not a delivered one, and only the log distinguishes
    # them.
    for execution in executions:
        if execution.validation_passed and execution.movement is not None:
            delivered = await broadcast_movement(execution)
            await movement_service.record(
                session,
                serial_command=execution.movement.serial_command or "",
                handedness=execution.movement.handedness,
                source=MovementSource.EXECUTION,
                actuator_positions=execution.movement.actuator_positions,
                duration_ms=execution.movement.duration_ms,
                execution_id=execution.id,
                sent_to_simulator=delivered > 0,
                sent_to_prosthesis=False,
            )
            break

    determinism = None
    if repetition_group:
        determinism = aggregate_determinism(
            [e.metrics.response_fingerprint if e.metrics else None for e in executions]
        )

    return RunExecutionOut(
        executions=[ExecutionOut.model_validate(e) for e in executions],
        determinism=determinism,
    )


@router.get("/stats", response_model=ExecutionStats)
async def execution_stats(
    since: datetime | None = None,
    project_id: uuid.UUID | None = None,
    experiment_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
) -> ExecutionStats:
    """Aggregates over every matching execution, computed in the database.

    Deliberately not derived from the list endpoint's page: a dashboard that
    aggregates the rows it happens to have loaded reports a different number
    every time the page size changes.
    """
    filters = []
    if since:
        filters.append(Execution.created_at >= since)
    if project_id:
        filters.append(Execution.project_id == project_id)
    if experiment_id:
        filters.append(Execution.experiment_id == experiment_id)

    totals = (
        await session.execute(
            select(
                func.count(Execution.id),
                func.count(Execution.id).filter(Execution.validation_passed.is_(True)),
                func.count(Execution.id).filter(Execution.validation_passed.is_(False)),
                func.count(Execution.id).filter(
                    Execution.status.in_(("provider_error", "timeout"))
                ),
                func.count(func.distinct(Execution.litellm_model)),
                func.count(func.distinct(Execution.emg_window_id)),
                func.avg(Execution.latency_ms),
                func.percentile_cont(0.95).within_group(Execution.latency_ms.asc()),
                func.coalesce(func.sum(Execution.total_tokens), 0),
                func.coalesce(func.sum(Execution.cost_usd), 0),
                func.min(Execution.created_at),
                func.max(Execution.created_at),
                func.count(func.distinct(Execution.frozen_context_sha256)),
            ).where(*filters)
        )
    ).one()

    per_model = (
        await session.execute(
            select(
                Execution.litellm_model,
                Execution.provider_slug,
                func.count(Execution.id),
                func.count(Execution.id).filter(Execution.validation_passed.is_(True)),
                func.avg(Execution.latency_ms),
                func.coalesce(func.sum(Execution.total_tokens), 0),
                func.coalesce(func.sum(Execution.cost_usd), 0),
                func.max(Execution.created_at),
            )
            .where(*filters, Execution.litellm_model.is_not(None))
            .group_by(Execution.litellm_model, Execution.provider_slug)
            .order_by(func.count(Execution.id).desc())
        )
    ).all()

    # Accuracy against the researcher's own answer key.
    #
    # Counted over labelled runs only. Executions with no expected command are
    # excluded from the denominator rather than scored as failures: they were
    # never a test of correctness, and letting them dilute the rate would make
    # the figure fall every time someone ran an unlabelled window.
    #
    # Computed in SQL alongside the other aggregates for the same reason they
    # are: a rate derived from the page the browser happens to hold changes
    # whenever the page size does.
    expected = (
        await session.execute(
            select(
                func.count(ExecutionMetric.id),
                func.count(ExecutionMetric.id).filter(
                    ExecutionMetric.command_matches_expected.is_(True)
                ),
            )
            .join(Execution, Execution.id == ExecutionMetric.execution_id)
            .where(*filters, ExecutionMetric.command_matches_expected.is_not(None))
        )
    ).one()

    failures = (
        await session.execute(
            select(ValidationIssueRecord.code, func.count())
            .join(
                ValidationResult,
                ValidationResult.id == ValidationIssueRecord.validation_result_id,
            )
            .join(Execution, Execution.id == ValidationResult.execution_id)
            .where(*filters, ValidationIssueRecord.severity == "error")
            .group_by(ValidationIssueRecord.code)
            .order_by(func.count().desc())
            .limit(6)
        )
    ).all()

    executions = totals[0] or 0
    return ExecutionStats(
        executions=executions,
        passed=totals[1] or 0,
        failed=totals[2] or 0,
        provider_errors=totals[3] or 0,
        pass_rate=round((totals[1] or 0) / executions, 4) if executions else None,
        distinct_models=totals[4] or 0,
        distinct_windows=totals[5] or 0,
        mean_latency_ms=round(float(totals[6]), 1) if totals[6] is not None else None,
        p95_latency_ms=round(float(totals[7]), 1) if totals[7] is not None else None,
        total_tokens=int(totals[8] or 0),
        total_cost_usd=float(totals[9] or 0),
        first_run_at=totals[10],
        last_run_at=totals[11],
        # More than one frozen context means the per-model rows were produced
        # under different conditions and cannot be compared as they stand.
        comparable=(totals[12] or 0) <= 1,
        command_labelled=expected[0] or 0,
        command_matched=expected[1] or 0,
        command_accuracy=(
            round((expected[1] or 0) / expected[0], 4) if expected[0] else None
        ),
        by_model=[
            ModelSummary(
                litellm_model=row[0],
                provider_slug=row[1],
                executions=row[2],
                passed=row[3],
                pass_rate=round(row[3] / row[2], 4) if row[2] else 0.0,
                mean_latency_ms=round(float(row[4]), 1) if row[4] is not None else None,
                total_tokens=int(row[5] or 0),
                total_cost_usd=float(row[6] or 0),
                last_run_at=row[7],
            )
            for row in per_model
        ],
        top_failure_codes=[{"code": code, "count": count} for code, count in failures],
    )


# ═════════════════════════════════════════════════════════════════════════════
# Prompt configurations
# ═════════════════════════════════════════════════════════════════════════════


@router.get("/configurations", response_model=list[PromptConfigurationOut])
async def list_prompt_configurations(
    since: datetime | None = None,
    session: AsyncSession = Depends(get_session),
):
    """Every distinct frozen prompt setup, with what each model did under it.

    Deduplicated at write time, so this is a plain list rather than a grouping:
    three runs under two setups produce two rows, and going back to the first
    setup reuses its row instead of adding a third.

    Results are broken out **per model** because a configuration is only
    comparable within one. Averaging a 4B model and a 30B model under the same
    prompt yields a number that describes neither, and presenting the
    configuration as though it had a single accuracy would invite exactly that
    reading.
    """
    filters = [Execution.prompt_configuration_id.is_not(None)]
    if since:
        filters.append(Execution.created_at >= since)

    configurations = (
        await session.execute(
            select(PromptConfiguration).order_by(desc(PromptConfiguration.last_used_at))
        )
    ).scalars().all()

    # One grouped query for every configuration at once. Per-configuration
    # queries would be N+1, and this list is displayed in full.
    rows = (
        await session.execute(
            select(
                Execution.prompt_configuration_id,
                Execution.litellm_model,
                func.count(Execution.id),
                func.count(Execution.id).filter(Execution.validation_passed.is_(True)),
                func.count(ExecutionMetric.id).filter(
                    ExecutionMetric.command_matches_expected.is_not(None)
                ),
                func.count(ExecutionMetric.id).filter(
                    ExecutionMetric.command_matches_expected.is_(True)
                ),
                func.avg(Execution.latency_ms),
                func.max(Execution.created_at),
            )
            .outerjoin(ExecutionMetric, ExecutionMetric.execution_id == Execution.id)
            .where(*filters, Execution.litellm_model.is_not(None))
            .group_by(Execution.prompt_configuration_id, Execution.litellm_model)
            .order_by(func.count(Execution.id).desc())
        )
    ).all()

    per_configuration: dict[uuid.UUID, list[ConfigurationModelResult]] = {}
    for row in rows:
        per_configuration.setdefault(row[0], []).append(
            ConfigurationModelResult(
                litellm_model=row[1],
                executions=row[2],
                passed=row[3],
                pass_rate=round(row[3] / row[2], 4) if row[2] else 0.0,
                command_labelled=row[4] or 0,
                command_matched=row[5] or 0,
                # Unlabelled runs stay out of the denominator: they were never a
                # test of correctness, and letting them dilute the rate would
                # make it fall every time an unlabelled window was run.
                command_accuracy=(
                    round((row[5] or 0) / row[4], 4) if row[4] else None
                ),
                mean_latency_ms=round(float(row[6]), 1) if row[6] is not None else None,
                last_run_at=row[7],
            )
        )

    return [
        PromptConfigurationOut(
            id=configuration.id,
            label=configuration.label,
            frozen_context_sha256=configuration.frozen_context_sha256,
            system_prompt_version=configuration.system_prompt_version,
            technical_context_version=configuration.technical_context_version,
            emg_context_version=configuration.emg_context_version,
            first_used_at=configuration.first_used_at,
            last_used_at=configuration.last_used_at,
            executions=sum(
                result.executions
                for result in per_configuration.get(configuration.id, [])
            ),
            by_model=per_configuration.get(configuration.id, []),
        )
        for configuration in configurations
    ]


@router.get("", response_model=list[ExecutionOut])
async def list_executions(
    experiment_id: uuid.UUID | None = None,
    litellm_model: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    validation_passed: bool | None = None,
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    # `errors` is the one relationship on Execution that is not lazy="joined",
    # and ExecutionOut serialises it. On rows that came from a SELECT rather
    # than from this session's identity map, touching it emits a lazy load
    # outside the greenlet — MissingGreenlet, a 500, and a dashboard that shows
    # nothing at all. Eager-loading it here is the fix.
    #
    # selectinload rather than joinedload: `errors` is a collection, and joining
    # it alongside the four already-joined relationships would multiply the
    # result set by the error count and silently break LIMIT.
    stmt = (
        select(Execution)
        .options(selectinload(Execution.errors))
        .order_by(desc(Execution.created_at))
        .limit(limit)
        .offset(offset)
    )
    if experiment_id:
        stmt = stmt.where(Execution.experiment_id == experiment_id)
    if litellm_model:
        stmt = stmt.where(Execution.litellm_model == litellm_model)
    if status_filter:
        stmt = stmt.where(Execution.status == status_filter)
    if validation_passed is not None:
        stmt = stmt.where(Execution.validation_passed.is_(validation_passed))
    return list((await session.execute(stmt)).scalars().unique().all())


@router.get("/{execution_id}", response_model=ExecutionOut)
async def get_execution(execution_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    execution = (
        await session.execute(
            select(Execution)
            .options(selectinload(Execution.errors))
            .where(Execution.id == execution_id)
        )
    ).scalars().unique().one_or_none()
    if execution is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Execution not found.")
    return execution


@router.get("/{execution_id}/prompt", response_model=dict)
async def get_execution_prompt(
    execution_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    """The literal prompt that was sent. Reproducibility depends on this being
    stored verbatim rather than reconstructed."""
    execution = await session.get(Execution, execution_id)
    if execution is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Execution not found.")
    return {
        "system_prompt": execution.system_prompt_text,
        "technical_context": execution.technical_context_text,
        "dynamic_prompt": execution.dynamic_prompt_text,
        "messages": execution.messages_json,
        "hashes": {
            "system_prompt": execution.system_prompt_sha256,
            "technical_context": execution.technical_context_sha256,
            "dynamic_prompt": execution.dynamic_prompt_sha256,
            "frozen_context": execution.frozen_context_sha256,
            "full_prompt": execution.full_prompt_sha256,
        },
        "model_snapshot": execution.model_snapshot,
    }


@router.post("/{execution_id}/replay-movement", response_model=dict)
async def replay_movement(
    execution_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    """Re-emit a stored, previously validated movement to the simulator.

    Only executions that passed validation have a movement row, so this can
    never resurrect an unsafe pose.
    """
    execution = await session.get(Execution, execution_id)
    if execution is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Execution not found.")
    if execution.movement is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This execution produced no validated movement; nothing to replay.",
        )
    delivered = await broadcast_movement(execution)
    # A replay moves the hand exactly as the original did, so it is logged as a
    # transmission in its own right. Attributing it to the original execution
    # would make the log claim one movement where two happened.
    await movement_service.record(
        session,
        serial_command=execution.movement.serial_command or "",
        handedness=execution.movement.handedness,
        source=MovementSource.REPLAY,
        actuator_positions=execution.movement.actuator_positions,
        duration_ms=execution.movement.duration_ms,
        execution_id=execution.id,
        sent_to_simulator=delivered > 0,
    )
    return {"replayed": True, "execution_id": str(execution.id)}
