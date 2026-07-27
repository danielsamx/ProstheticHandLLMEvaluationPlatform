"""Experiments and the cross-model comparison endpoint."""

from __future__ import annotations

import statistics
import uuid
from collections import Counter, defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models.experiment import Execution, Experiment
from app.models.validation import ValidationIssueRecord, ValidationResult
from app.schemas.api import (
    ComparisonOut,
    ExperimentIn,
    ExperimentOut,
    ModelComparisonRow,
)

router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.get("", response_model=list[ExperimentOut])
async def list_experiments(session: AsyncSession = Depends(get_session)):
    stmt = select(Experiment).order_by(Experiment.created_at.desc())
    return list((await session.execute(stmt)).scalars().all())


@router.post("", response_model=ExperimentOut, status_code=status.HTTP_201_CREATED)
async def create_experiment(payload: ExperimentIn, session: AsyncSession = Depends(get_session)):
    row = Experiment(
        **payload.model_dump(exclude={"limit_profile", "handedness"}),
        limit_profile=payload.limit_profile.value,
        handedness=payload.handedness.value,
    )
    session.add(row)
    await session.flush()
    return row


@router.get("/{experiment_id}", response_model=ExperimentOut)
async def get_experiment(experiment_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    row = await session.get(Experiment, experiment_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Experiment not found.")
    return row


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(pct * (len(ordered) - 1)))))
    return round(ordered[index], 2)


def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 4) if values else None


@router.get("/{experiment_id}/comparison", response_model=ComparisonOut)
async def compare_models(
    experiment_id: uuid.UUID,
    min_executions: int = Query(default=1, ge=1),
    session: AsyncSession = Depends(get_session),
) -> ComparisonOut:
    """Leaderboard across every model run inside one experiment.

    ``comparable`` is the honest flag: if the executions did not all share the
    same frozen context hash, the differences cannot be attributed to the model
    and the caller is told so rather than being handed a misleading ranking.
    """
    experiment = await session.get(Experiment, experiment_id)
    if experiment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Experiment not found.")

    stmt = (
        select(Execution)
        .where(Execution.experiment_id == experiment_id)
        .options(
            selectinload(Execution.metrics),
            selectinload(Execution.validation_result).selectinload(ValidationResult.issues),
        )
    )
    executions = list((await session.execute(stmt)).scalars().unique().all())
    if not executions:
        return ComparisonOut(
            experiment_id=experiment_id, frozen_context_sha256=None,
            comparable=True, rows=[],
        )

    context_hashes = {e.frozen_context_sha256 for e in executions if e.frozen_context_sha256}
    comparable = len(context_hashes) <= 1

    grouped: dict[str, list[Execution]] = defaultdict(list)
    for execution in executions:
        grouped[execution.litellm_model or "unknown"].append(execution)

    rows: list[ModelComparisonRow] = []
    for model_key, group in grouped.items():
        if len(group) < min_executions:
            continue

        metrics = [e.metrics for e in group if e.metrics is not None]
        total = len(group)

        failure_codes: Counter[str] = Counter()
        for execution in group:
            result = execution.validation_result
            if result is not None:
                for issue in result.issues:
                    if issue.severity == "error":
                        failure_codes[issue.code] += 1

        accuracy_pool = [m.gesture_correct for m in metrics if m.gesture_correct is not None]
        latencies = [float(e.latency_ms) for e in group if e.latency_ms is not None]

        fingerprint_groups: dict[str, Counter[str]] = defaultdict(Counter)
        for m in metrics:
            if m.repetition_group and m.response_fingerprint:
                fingerprint_groups[m.repetition_group][m.response_fingerprint] += 1
        determinism_rates = [
            max(counter.values()) / sum(counter.values())
            for counter in fingerprint_groups.values()
            if counter
        ]

        rows.append(
            ModelComparisonRow(
                litellm_model=model_key,
                provider_slug=group[0].provider_slug,
                executions=total,
                validation_pass_rate=round(
                    sum(1 for e in group if e.validation_passed) / total, 4
                ),
                json_validity_rate=round(
                    sum(1 for m in metrics if m.is_valid_json) / total, 4
                ),
                schema_compliance_rate=round(
                    sum(1 for m in metrics if m.schema_compliant) / total, 4
                ),
                within_limits_rate=round(
                    sum(1 for m in metrics if m.within_mechanical_limits) / total, 4
                ),
                gesture_accuracy=(
                    round(sum(1 for c in accuracy_pool if c) / len(accuracy_pool), 4)
                    if accuracy_pool else None
                ),
                mean_confidence=_mean(
                    [m.model_confidence for m in metrics if m.model_confidence is not None]
                ),
                mean_calibration_error=_mean(
                    [m.calibration_error for m in metrics if m.calibration_error is not None]
                ),
                mean_latency_ms=_mean(latencies),
                p95_latency_ms=_percentile(latencies, 0.95),
                mean_tokens_per_second=_mean(
                    [m.tokens_per_second for m in metrics if m.tokens_per_second is not None]
                ),
                total_cost_usd=round(sum(float(e.cost_usd or 0) for e in group), 8),
                determinism_rate=_mean(determinism_rates),
                top_failure_codes=[
                    {"code": code, "count": count}
                    for code, count in failure_codes.most_common(5)
                ],
            )
        )

    rows.sort(key=lambda r: (-r.validation_pass_rate, r.mean_latency_ms or 1e9))
    return ComparisonOut(
        experiment_id=experiment_id,
        frozen_context_sha256=next(iter(context_hashes), None),
        comparable=comparable,
        rows=rows,
    )


@router.get("/{experiment_id}/failure-modes", response_model=list[dict])
async def failure_modes(
    experiment_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    """How each model fails, not just how often - the diagnostic view."""
    stmt = (
        select(
            Execution.litellm_model,
            ValidationIssueRecord.stage,
            ValidationIssueRecord.code,
            ValidationIssueRecord.severity,
        )
        .join(ValidationResult, ValidationResult.execution_id == Execution.id)
        .join(
            ValidationIssueRecord,
            ValidationIssueRecord.validation_result_id == ValidationResult.id,
        )
        .where(Execution.experiment_id == experiment_id)
    )
    rows = (await session.execute(stmt)).all()
    counter: Counter[tuple] = Counter(tuple(r) for r in rows)
    return [
        {
            "litellm_model": key[0],
            "stage": key[1],
            "code": key[2],
            "severity": key[3],
            "count": count,
        }
        for key, count in counter.most_common()
    ]
