"""Audit trail service.

One entry point, :func:`record`, used by every mutating operation. Entries are
append-only and carry the actor, the action, the affected entity, the outcome
and a field-level diff.

Auditing never breaks the operation it describes: a failure to write the trail
is logged loudly but does not roll back the user's work. The alternative —
refusing an experiment because the audit insert failed — trades a real capability
for a bookkeeping detail.
"""

from __future__ import annotations

import uuid
from typing import Any, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.request_context import RequestContext, current_context
from app.models.audit import AuditAction, AuditLog, AuditOutcome

logger = get_logger(__name__)

#: Never written to the audit trail, whatever the caller passes.
REDACTED_FIELDS: frozenset[str] = frozenset(
    {"password", "hashed_password", "api_key", "secret", "token", "authorization"}
)

#: Long text is summarised rather than duplicated. The full content already
#: lives in its own versioned row; copying it here would multiply storage for
#: no gain.
_MAX_VALUE_CHARS: int = 500


def _redact(key: str, value: Any) -> Any:
    if key.lower() in REDACTED_FIELDS or any(f in key.lower() for f in REDACTED_FIELDS):
        return "[redacted]"
    if isinstance(value, str) and len(value) > _MAX_VALUE_CHARS:
        return f"{value[:_MAX_VALUE_CHARS]}… ({len(value)} chars)"
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def diff(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    *,
    ignore: Sequence[str] = ("updated_at", "created_at"),
) -> dict[str, dict[str, Any]]:
    """Field-level difference, redacted and truncated.

    Only changed fields are recorded. Storing whole rows would bury the actual
    change and grow the table without bound.
    """
    before = before or {}
    after = after or {}
    skip = set(ignore)

    changes: dict[str, dict[str, Any]] = {}
    for key in set(before) | set(after):
        if key in skip:
            continue
        old, new = before.get(key), after.get(key)
        if old != new:
            changes[key] = {"from": _redact(key, old), "to": _redact(key, new)}
    return changes


async def record(
    session: AsyncSession,
    action: AuditAction,
    *,
    summary: str,
    outcome: AuditOutcome = AuditOutcome.SUCCESS,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    entity_label: str | None = None,
    project_id: uuid.UUID | None = None,
    changes: Mapping[str, Any] | None = None,
    context: Mapping[str, Any] | None = None,
    error_message: str | None = None,
    http_status: int | None = None,
    duration_ms: int | None = None,
    request_context: RequestContext | None = None,
) -> AuditLog | None:
    """Append one audit entry. Returns ``None`` if the write itself failed."""
    origin = request_context or current_context()

    entry = AuditLog(
        actor_id=origin.actor_id,
        actor_email=origin.actor_email,
        actor_role=origin.actor_role,
        action=action.value,
        outcome=outcome.value,
        summary=summary,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_label=entity_label[:320] if entity_label else None,
        project_id=project_id,
        changes=dict(changes or {}),
        context=dict(context or {}),
        error_message=error_message,
        client_ip=origin.client_ip,
        user_agent=(origin.user_agent or "")[:512] or None,
        browser=origin.browser,
        operating_system=origin.operating_system,
        device_type=origin.device_type,
        session_id=origin.session_id,
        request_id=origin.request_id,
        http_method=origin.http_method,
        http_path=(origin.http_path or "")[:512] or None,
        http_status=http_status,
        duration_ms=duration_ms,
    )

    try:
        session.add(entry)
        await session.flush()
    except Exception as exc:  # pragma: no cover - defensive
        # Deliberately swallowed: losing an audit line is bad, losing the
        # researcher's experiment because of it is worse. The failure is logged
        # at error level so it is not invisible.
        logger.error(
            "audit_write_failed",
            extra={"action": action.value, "entity_type": entity_type, "error": str(exc)},
        )
        return None

    return entry


async def record_change(
    session: AsyncSession,
    action: AuditAction,
    *,
    summary: str,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    **kwargs: Any,
) -> AuditLog | None:
    """Convenience wrapper that computes the diff for an update."""
    return await record(session, action, summary=summary, changes=diff(before, after), **kwargs)


async def history_for(
    session: AsyncSession,
    entity_type: str,
    entity_id: uuid.UUID,
    limit: int = 200,
) -> list[AuditLog]:
    """Everything that has happened to one entity, newest first."""
    stmt = (
        select(AuditLog)
        .where(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


def snapshot(instance: Any, fields: Sequence[str]) -> dict[str, Any]:
    """Read selected attributes off a model instance, for before/after diffs."""
    return {field: _redact(field, getattr(instance, field, None)) for field in fields}
