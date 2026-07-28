"""Projects: the container above experiments, with a full audit trail."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.audit import AuditAction, AuditOutcome
from app.models.experiment import Execution, Experiment
from app.models.project import Project, ProjectStatus
from app.schemas.governance import (
    ProjectIn,
    ProjectOut,
    ProjectStats,
    ProjectUpdate,
)
from app.services import audit_service

router = APIRouter(prefix="/projects", tags=["projects"])

#: Fields tracked in the audit diff. Timestamps are excluded — they change on
#: every write and would drown the actual edit.
AUDITED_FIELDS = ("name", "slug", "description", "research_question", "status", "tags", "settings")


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return cleaned[:120] or "project"


async def _unique_slug(session: AsyncSession, base: str) -> str:
    """Append a counter until the slug is free.

    Slugs are user-visible identifiers, so a collision has to be resolved rather
    than rejected — the researcher should not have to invent a name twice.
    """
    candidate = base
    suffix = 2
    while True:
        exists = (
            await session.execute(select(Project.id).where(Project.slug == candidate))
        ).scalar_one_or_none()
        if exists is None:
            return candidate
        candidate = f"{base}-{suffix}"[:120]
        suffix += 1


async def _get_or_404(session: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await session.get(Project, project_id)
    if project is None or project.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found.")
    return project


@router.get("", response_model=list[ProjectOut])
async def list_projects(
    include_archived: bool = Query(default=False),
    include_deleted: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Project).order_by(Project.created_at.desc())
    if not include_deleted:
        stmt = stmt.where(Project.is_deleted.is_(False))
    if not include_archived:
        stmt = stmt.where(Project.status != ProjectStatus.ARCHIVED)
    return list((await session.execute(stmt)).scalars().all())


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(payload: ProjectIn, session: AsyncSession = Depends(get_session)):
    slug = await _unique_slug(session, payload.slug or slugify(payload.name))
    project = Project(
        name=payload.name,
        slug=slug,
        description=payload.description,
        research_question=payload.research_question,
        tags=payload.tags,
        settings=payload.settings,
        status=ProjectStatus.ACTIVE,
    )
    session.add(project)
    await session.flush()

    await audit_service.record(
        session, AuditAction.PROJECT_CREATED,
        summary=f"Created project '{project.name}'",
        entity_type="project", entity_id=project.id, entity_label=project.name,
        project_id=project.id,
        changes=audit_service.diff(None, audit_service.snapshot(project, AUDITED_FIELDS)),
    )
    return project


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    return await _get_or_404(session, project_id)


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    session: AsyncSession = Depends(get_session),
):
    project = await _get_or_404(session, project_id)
    before = audit_service.snapshot(project, AUDITED_FIELDS)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    if payload.status == ProjectStatus.ARCHIVED and project.archived_at is None:
        project.archived_at = datetime.now(timezone.utc)
    await session.flush()

    after = audit_service.snapshot(project, AUDITED_FIELDS)
    action = (
        AuditAction.PROJECT_ARCHIVED
        if payload.status == ProjectStatus.ARCHIVED
        else AuditAction.PROJECT_UPDATED
    )
    await audit_service.record(
        session, action,
        summary=f"Updated project '{project.name}'",
        entity_type="project", entity_id=project.id, entity_label=project.name,
        project_id=project.id, changes=audit_service.diff(before, after),
    )
    return project


@router.delete("/{project_id}", response_model=ProjectOut)
async def delete_project(project_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    """Soft delete.

    Records are never physically removed. An experiment that produced published
    results must remain reconstructible after the project it belonged to is
    retired, and a hard delete would break exactly the traceability this
    platform exists to provide.
    """
    project = await _get_or_404(session, project_id)
    project.is_deleted = True
    project.deleted_at = datetime.now(timezone.utc)
    await session.flush()

    await audit_service.record(
        session, AuditAction.PROJECT_DELETED,
        summary=f"Deleted project '{project.name}' (soft delete; data retained)",
        entity_type="project", entity_id=project.id, entity_label=project.name,
        project_id=project.id,
        context={"soft_delete": True, "experiments_retained": True},
    )
    return project


@router.post("/{project_id}/restore", response_model=ProjectOut)
async def restore_project(project_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found.")
    if not project.is_deleted:
        raise HTTPException(status.HTTP_409_CONFLICT, "Project is not deleted.")

    project.is_deleted = False
    project.deleted_at = None
    await session.flush()

    await audit_service.record(
        session, AuditAction.PROJECT_RESTORED,
        summary=f"Restored project '{project.name}'",
        entity_type="project", entity_id=project.id, entity_label=project.name,
        project_id=project.id,
    )
    return project


@router.get("/{project_id}/stats", response_model=ProjectStats)
async def project_stats(project_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    """Headline numbers, computed in the database rather than in Python.

    A project can accumulate hundreds of thousands of executions; loading them
    to count in the application would not survive the first serious sweep.
    """
    await _get_or_404(session, project_id)

    experiments = (
        await session.execute(
            select(func.count(Experiment.id)).where(Experiment.project_id == project_id)
        )
    ).scalar_one()

    row = (
        await session.execute(
            select(
                func.count(Execution.id),
                func.count(Execution.id).filter(Execution.validation_passed.is_(True)),
                func.count(Execution.id).filter(Execution.validation_passed.is_(False)),
                func.count(func.distinct(Execution.litellm_model)),
                func.coalesce(func.sum(Execution.total_tokens), 0),
                func.coalesce(func.sum(Execution.cost_usd), 0),
                func.avg(Execution.latency_ms),
                func.min(Execution.created_at),
                func.max(Execution.created_at),
            ).where(Execution.project_id == project_id)
        )
    ).one()

    return ProjectStats(
        project_id=project_id,
        experiments=experiments,
        executions=row[0],
        successful_executions=row[1],
        failed_executions=row[2],
        distinct_models=row[3],
        total_tokens=int(row[4] or 0),
        total_cost_usd=float(row[5] or 0),
        mean_latency_ms=round(float(row[6]), 2) if row[6] is not None else None,
        first_execution_at=row[7],
        last_execution_at=row[8],
    )


@router.get("/{project_id}/audit", response_model=list[dict])
async def project_audit(
    project_id: uuid.UUID,
    limit: int = Query(default=200, le=1000),
    session: AsyncSession = Depends(get_session),
):
    """Everything that has happened inside this project."""
    from app.models.audit import AuditLog

    stmt = (
        select(AuditLog)
        .where(AuditLog.project_id == project_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": str(r.id), "created_at": r.created_at, "action": r.action,
            "outcome": r.outcome, "summary": r.summary,
            "actor_email": r.actor_email, "entity_type": r.entity_type,
            "entity_label": r.entity_label, "changes": r.changes,
        }
        for r in rows
    ]
