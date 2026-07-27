"""Running and retrieving executions - the 'Run Evaluation' path."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.models.experiment import Execution
from app.schemas.api import ExecutionOut, RunExecutionIn, RunExecutionOut
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
                dynamic_prompt_template_id=payload.dynamic_prompt_template_id,
                system_prompt_override=payload.system_prompt_override,
                technical_context_override=payload.technical_context_override,
                dynamic_template_override=payload.dynamic_template_override,
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

    # Push the first successful movement to any attached simulator client.
    for execution in executions:
        if execution.validation_passed and execution.movement is not None:
            await broadcast_movement(execution)
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
    stmt = select(Execution).order_by(desc(Execution.created_at)).limit(limit).offset(offset)
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
    execution = await session.get(Execution, execution_id)
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
    await broadcast_movement(execution)
    return {"replayed": True, "execution_id": str(execution.id)}
