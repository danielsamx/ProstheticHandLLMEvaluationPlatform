"""Export the experimental record for statistical analysis.

Produces one row per execution with every variable an analysis needs already
flattened — model, decoding parameters, stimulus descriptors, outcome, cost and
timing — so the file drops straight into pandas or R without a join.

Failures are included by default. Excluding them would silently bias any
success rate computed downstream, and *how* a model fails is usually the more
interesting result.
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import datetime
from typing import Any, Iterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.emg import EmgWindowRecord
from app.models.experiment import Execution
from app.schemas.governance import ExportRequest

#: Column order for the tabular export. Stable across releases: an analysis
#: script that positionally indexes these should not break on an upgrade.
BASE_COLUMNS: tuple[str, ...] = (
    "execution_id", "created_at", "project_id", "experiment_id", "repetition_index",
    "repetition_group", "status", "validation_passed", "failed_stage",
    # Condition
    "provider", "litellm_model", "model_key", "api_base",
    "temperature", "top_p", "top_k", "max_tokens", "seed",
    "frequency_penalty", "presence_penalty", "response_format", "reasoning_mode",
    "dropped_parameters", "limit_profile", "handedness",
    # Comparability
    "frozen_context_sha256", "full_prompt_sha256", "app_version",
    # Stimulus
    "emg_window_id", "emg_checksum", "emg_source_mode", "emg_sample_count",
    "emg_sample_rate_hz", "emg_window_ms", "emg_mean_rms", "ground_truth_gesture",
    "subject_ref",
    # Outcome
    "intent", "predicted_gesture", "gesture_correct", "detected_pattern",
    "model_confidence", "calibration_error", "actuators_commanded",
    "serial_command", "is_valid_json", "is_bare_json", "schema_compliant",
    "protocol_compliant", "consistency_compliant", "within_mechanical_limits",
    "safety_compliant",
    "error_count", "warning_count", "response_fingerprint",
    # Cost and speed
    "latency_ms", "prompt_tokens", "completion_tokens", "total_tokens",
    "tokens_per_second", "cost_usd",
    # Provenance
    "triggered_by_email", "session_id", "request_id", "browser", "operating_system",
)


async def collect(session: AsyncSession, request: ExportRequest) -> list[dict[str, Any]]:
    """Flatten matching executions into analysis-ready rows."""
    stmt = (
        select(Execution)
        .options(
            selectinload(Execution.validation_result),
            selectinload(Execution.metrics),
            selectinload(Execution.movement),
        )
        .order_by(Execution.created_at)
        .limit(request.limit)
    )

    if request.project_id:
        stmt = stmt.where(Execution.project_id == request.project_id)
    if request.experiment_id:
        stmt = stmt.where(Execution.experiment_id == request.experiment_id)
    if request.since:
        stmt = stmt.where(Execution.created_at >= request.since)
    if request.until:
        stmt = stmt.where(Execution.created_at <= request.until)
    if request.litellm_model:
        stmt = stmt.where(Execution.litellm_model == request.litellm_model)
    if request.only_validated:
        stmt = stmt.where(Execution.validation_passed.is_(True))

    executions = list((await session.execute(stmt)).scalars().unique().all())

    # One query for every window, rather than one per row.
    window_ids = {e.emg_window_id for e in executions if e.emg_window_id}
    windows: dict[uuid.UUID, EmgWindowRecord] = {}
    if window_ids:
        rows = (
            await session.execute(
                select(EmgWindowRecord).where(EmgWindowRecord.id.in_(window_ids))
            )
        ).scalars().all()
        windows = {w.id: w for w in rows}

    return [_flatten(e, windows.get(e.emg_window_id), request) for e in executions]


def _flatten(
    execution: Execution,
    window: EmgWindowRecord | None,
    request: ExportRequest,
) -> dict[str, Any]:
    validation = execution.validation_result
    metrics = execution.metrics
    movement = execution.movement

    row: dict[str, Any] = {
        "execution_id": str(execution.id),
        "created_at": execution.created_at.isoformat() if execution.created_at else None,
        "project_id": str(execution.project_id) if execution.project_id else None,
        "experiment_id": str(execution.experiment_id) if execution.experiment_id else None,
        "repetition_index": execution.repetition_index,
        "repetition_group": metrics.repetition_group if metrics else None,
        "status": execution.status,
        "validation_passed": execution.validation_passed,
        "failed_stage": validation.failed_stage if validation else None,

        "provider": execution.provider_slug,
        "litellm_model": execution.litellm_model,
        "model_key": execution.model_key,
        "api_base": execution.api_base,
        "temperature": execution.temperature,
        "top_p": execution.top_p,
        "top_k": execution.top_k,
        "max_tokens": execution.max_tokens,
        "seed": execution.seed,
        "frequency_penalty": execution.frequency_penalty,
        "presence_penalty": execution.presence_penalty,
        "response_format": execution.response_format,
        "reasoning_mode": execution.reasoning_mode,
        "dropped_parameters": ";".join(execution.dropped_parameters or []),
        "limit_profile": execution.limit_profile,
        "handedness": execution.handedness,

        "frozen_context_sha256": execution.frozen_context_sha256,
        "full_prompt_sha256": execution.full_prompt_sha256,
        "app_version": execution.app_version,

        "emg_window_id": str(execution.emg_window_id) if execution.emg_window_id else None,
        "emg_checksum": window.checksum if window else None,
        "emg_source_mode": window.source_mode if window else None,
        "emg_sample_count": window.sample_count if window else None,
        "emg_sample_rate_hz": window.sample_rate_hz if window else None,
        "emg_window_ms": window.window_ms if window else None,
        "emg_mean_rms": window.mean_rms if window else None,
        "ground_truth_gesture": window.ground_truth_gesture if window else None,
        "subject_ref": window.subject_ref if window else None,

        "intent": metrics.intent if metrics else None,
        "predicted_gesture": metrics.predicted_gesture if metrics else None,
        "gesture_correct": metrics.gesture_correct if metrics else None,
        "detected_pattern": metrics.detected_pattern if metrics else None,
        "model_confidence": metrics.model_confidence if metrics else None,
        "calibration_error": metrics.calibration_error if metrics else None,
        "actuators_commanded": metrics.actuators_commanded if metrics else None,
        "serial_command": movement.serial_command if movement else None,
        "is_valid_json": metrics.is_valid_json if metrics else None,
        "is_bare_json": metrics.is_bare_json if metrics else None,
        "schema_compliant": metrics.schema_compliant if metrics else None,
        "protocol_compliant": metrics.protocol_compliant if metrics else None,
        "consistency_compliant": metrics.consistency_compliant if metrics else None,
        "within_mechanical_limits": metrics.within_mechanical_limits if metrics else None,
        "safety_compliant": metrics.safety_compliant if metrics else None,
        "error_count": validation.error_count if validation else None,
        "warning_count": execution.warning_count,
        "response_fingerprint": metrics.response_fingerprint if metrics else None,

        "latency_ms": execution.latency_ms,
        "prompt_tokens": execution.prompt_tokens,
        "completion_tokens": execution.completion_tokens,
        "total_tokens": execution.total_tokens,
        "tokens_per_second": execution.tokens_per_second,
        "cost_usd": float(execution.cost_usd or 0),

        "triggered_by_email": execution.triggered_by_email,
        "session_id": execution.session_id,
        "request_id": execution.request_id,
        "browser": execution.browser,
        "operating_system": execution.operating_system,
    }

    # Optional heavy columns, off by default: prompts multiply the file size by
    # roughly thirty and the matrix by far more.
    if request.include_prompts:
        row["system_prompt"] = execution.system_prompt_text
        row["technical_context"] = execution.technical_context_text
        row["dynamic_prompt"] = execution.dynamic_prompt_text
    if request.include_raw_response:
        row["raw_response"] = execution.raw_response
        row["parsed_response"] = json.dumps(execution.parsed_response, ensure_ascii=False)
    if request.include_emg_matrix and window is not None:
        row["emg_matrix"] = json.dumps(window.samples)

    return row


def to_csv(rows: list[dict[str, Any]]) -> str:
    """RFC 4180 CSV with a stable column order."""
    if not rows:
        return ",".join(BASE_COLUMNS) + "\n"

    columns = list(BASE_COLUMNS) + [c for c in rows[0] if c not in BASE_COLUMNS]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: _cell(v) for k, v in row.items()})
    return buffer.getvalue()


def to_jsonl(rows: list[dict[str, Any]]) -> Iterator[str]:
    """Newline-delimited JSON: streamable, and safe for very large exports."""
    for row in rows:
        yield json.dumps(row, ensure_ascii=False, default=_json_default) + "\n"


def _cell(value: Any) -> Any:
    if isinstance(value, bool):
        # 'true'/'false' rather than 'True'/'False': R and pandas both read the
        # lowercase form as boolean without a converter.
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        return ""
    return value


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, uuid.UUID)):
        return str(value)
    return repr(value)
