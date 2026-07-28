"""Audit browsing, traceability and export."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.audit import AuditAction, AuditLog, AuditOutcome
from app.schemas.governance import (
    AuditActionInfo,
    AuditLogOut,
    ExportRequest,
    TraceabilityRecord,
)
from app.services import audit_service, export_service, traceability_service

router = APIRouter(tags=["governance"])


# ═════════════════════════════════════════════════════════════════════════════
# Audit
# ═════════════════════════════════════════════════════════════════════════════

audit_router = APIRouter(prefix="/audit", tags=["audit"])


@audit_router.get("/actions", response_model=list[AuditActionInfo])
async def list_audit_actions() -> list[AuditActionInfo]:
    """The closed catalogue of auditable actions, grouped for the UI."""
    descriptions = {
        "auth": "Session activity",
        "project": "Project lifecycle",
        "experiment": "Experiment lifecycle",
        "prompt": "Prompt authoring and versioning",
        "model": "Model catalogue",
        "config": "Sampling configuration",
        "preset": "Laboratory presets",
        "execution": "Inference runs",
        "export": "Data extraction",
        "emg": "Stimulus import",
        "attachment": "File attachments",
        "admin": "Administrative actions",
    }
    return [
        AuditActionInfo(
            value=action.value,
            group=action.value.split(".")[0],
            description=descriptions.get(action.value.split(".")[0], "Other"),
        )
        for action in AuditAction
    ]


@audit_router.get("", response_model=list[AuditLogOut])
async def query_audit(
    action: AuditAction | None = None,
    outcome: AuditOutcome | None = None,
    actor_email: str | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    """Browse the audit trail. Newest first."""
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)

    if action:
        stmt = stmt.where(AuditLog.action == action.value)
    if outcome:
        stmt = stmt.where(AuditLog.outcome == outcome.value)
    if actor_email:
        stmt = stmt.where(AuditLog.actor_email == actor_email)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if project_id:
        stmt = stmt.where(AuditLog.project_id == project_id)
    if since:
        stmt = stmt.where(AuditLog.created_at >= since)
    if until:
        stmt = stmt.where(AuditLog.created_at <= until)

    return list((await session.execute(stmt)).scalars().all())


@audit_router.get("/entity/{entity_type}/{entity_id}", response_model=list[AuditLogOut])
async def entity_history(
    entity_type: str,
    entity_id: uuid.UUID,
    limit: int = Query(default=200, le=1000),
    session: AsyncSession = Depends(get_session),
):
    """Everything that has happened to one entity."""
    return await audit_service.history_for(session, entity_type, entity_id, limit)


# ═════════════════════════════════════════════════════════════════════════════
# Traceability
# ═════════════════════════════════════════════════════════════════════════════

trace_router = APIRouter(prefix="/traceability", tags=["traceability"])


@trace_router.get("/{execution_id}", response_model=TraceabilityRecord)
async def reconstruct(execution_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    """Reconstruct one past experiment in full.

    Returns what was asked, of which model, with which parameters, over which
    stimulus, what came back, how long it took, what it cost, who ran it and
    from where — plus ``reproducible`` and, when false, exactly which pieces are
    missing. A record that merely looks complete is worse than one that admits
    a gap.
    """
    record = await traceability_service.build_record(session, execution_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Execution not found.")
    return record


# ═════════════════════════════════════════════════════════════════════════════
# Export
# ═════════════════════════════════════════════════════════════════════════════

export_router = APIRouter(prefix="/export", tags=["export"])


@export_router.post("/executions.csv")
async def export_csv(payload: ExportRequest, session: AsyncSession = Depends(get_session)):
    """One row per execution, every analysis variable pre-flattened."""
    rows = await export_service.collect(session, payload)
    await audit_service.record(
        session, AuditAction.EXPORT_REQUESTED,
        summary=f"Exported {len(rows)} execution(s) as CSV",
        project_id=payload.project_id,
        context={"format": "csv", "rows": len(rows), "filters": payload.model_dump(mode="json")},
    )
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Response(
        content=export_service.to_csv(rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="executions-{stamp}.csv"'},
    )


@export_router.post("/executions.jsonl")
async def export_jsonl(payload: ExportRequest, session: AsyncSession = Depends(get_session)):
    """Newline-delimited JSON. Streamed, so a large export does not have to be
    held in memory on either side."""
    rows = await export_service.collect(session, payload)
    await audit_service.record(
        session, AuditAction.EXPORT_REQUESTED,
        summary=f"Exported {len(rows)} execution(s) as JSONL",
        project_id=payload.project_id,
        context={"format": "jsonl", "rows": len(rows)},
    )
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return StreamingResponse(
        export_service.to_jsonl(rows),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="executions-{stamp}.jsonl"'},
    )


@export_router.post("/executions.json", response_model=list[dict])
async def export_json(payload: ExportRequest, session: AsyncSession = Depends(get_session)):
    """Same rows as JSON, for consumption straight from the API."""
    rows = await export_service.collect(session, payload)
    await audit_service.record(
        session, AuditAction.EXPORT_REQUESTED,
        summary=f"Exported {len(rows)} execution(s) as JSON",
        project_id=payload.project_id,
        context={"format": "json", "rows": len(rows)},
    )
    return rows


@export_router.get("/columns", response_model=list[str])
async def export_columns() -> list[str]:
    """Stable column order, so an analysis script can rely on it."""
    return list(export_service.BASE_COLUMNS)


router.include_router(audit_router)
router.include_router(trace_router)
router.include_router(export_router)
