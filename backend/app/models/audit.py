"""Audit trail.

Append-only record of who did what, when, and with what outcome. Rows are never
updated or deleted — an audit log that can be edited is not an audit log.

Every entry captures the actor, the action, the affected entity, the outcome and
a before/after diff where one applies, plus the request metadata (address, agent,
session) that identifies the origin of the change.
"""

from __future__ import annotations

import uuid
from enum import Enum

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class AuditAction(str, Enum):
    """Closed catalogue of auditable actions.

    Closed on purpose: a free-text action column drifts into a dozen spellings
    of the same event and stops being aggregatable.
    """

    # ── Session ─────────────────────────────────────────────────────────────
    LOGIN = "auth.login"
    LOGIN_FAILED = "auth.login_failed"
    LOGOUT = "auth.logout"

    # ── Projects ────────────────────────────────────────────────────────────
    PROJECT_CREATED = "project.created"
    PROJECT_UPDATED = "project.updated"
    PROJECT_ARCHIVED = "project.archived"
    PROJECT_DELETED = "project.deleted"
    PROJECT_RESTORED = "project.restored"

    # ── Experiments ─────────────────────────────────────────────────────────
    EXPERIMENT_CREATED = "experiment.created"
    EXPERIMENT_UPDATED = "experiment.updated"
    EXPERIMENT_DELETED = "experiment.deleted"

    # ── Prompts ─────────────────────────────────────────────────────────────
    PROMPT_CREATED = "prompt.created"
    PROMPT_EDITED = "prompt.edited"
    PROMPT_ACTIVATED = "prompt.activated"
    PROMPT_DELETED = "prompt.deleted"

    # ── Models & configuration ──────────────────────────────────────────────
    MODEL_REGISTERED = "model.registered"
    MODEL_UPDATED = "model.updated"
    MODEL_IMPORTED = "model.imported"
    MODEL_SELECTED = "model.selected"
    CONFIG_CREATED = "config.created"
    CONFIG_UPDATED = "config.updated"
    CONFIG_DELETED = "config.deleted"
    PRESET_CREATED = "preset.created"
    PRESET_DELETED = "preset.deleted"

    # ── Execution ───────────────────────────────────────────────────────────
    EXECUTION_STARTED = "execution.started"
    EXECUTION_COMPLETED = "execution.completed"
    EXECUTION_FAILED = "execution.failed"
    EXECUTION_REPLAYED = "execution.replayed"

    # ── Data movement ───────────────────────────────────────────────────────
    EXPORT_REQUESTED = "export.requested"
    EMG_IMPORTED = "emg.imported"
    ATTACHMENT_UPLOADED = "attachment.uploaded"
    ATTACHMENT_DELETED = "attachment.deleted"

    # ── Administration ──────────────────────────────────────────────────────
    USER_CREATED = "admin.user_created"
    USER_UPDATED = "admin.user_updated"
    USER_DEACTIVATED = "admin.user_deactivated"
    ROLE_CHANGED = "admin.role_changed"
    SETTINGS_CHANGED = "admin.settings_changed"


class AuditOutcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"


class AuditLog(UUIDMixin, TimestampMixin, Base):
    """One auditable event. Append-only."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_actor_created", "actor_id", "created_at"),
        Index("ix_audit_logs_action_created", "action", "created_at"),
    )

    # ── Who ─────────────────────────────────────────────────────────────────
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    #: Identity snapshot. The foreign key may be nulled by account deletion, but
    #: the record of who performed the action must survive it.
    actor_email: Mapped[str | None] = mapped_column(String(320), index=True)
    actor_role: Mapped[str | None] = mapped_column(String(32))

    # ── What ────────────────────────────────────────────────────────────────
    action: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    outcome: Mapped[str] = mapped_column(
        String(16), default=AuditOutcome.SUCCESS.value, nullable=False, index=True
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    entity_type: Mapped[str | None] = mapped_column(String(48), index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), index=True)
    #: Human-readable label captured at the time, so the log still reads
    #: correctly after the entity is renamed or removed.
    entity_label: Mapped[str | None] = mapped_column(String(320))

    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )

    # ── Change detail ───────────────────────────────────────────────────────
    #: Only the fields that changed, not whole rows: a full snapshot of every
    #: edit would bloat the table and bury the actual change.
    changes: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    context: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)

    # ── Origin ──────────────────────────────────────────────────────────────
    client_ip: Mapped[str | None] = mapped_column(String(45), index=True)
    user_agent: Mapped[str | None] = mapped_column(String(512))
    browser: Mapped[str | None] = mapped_column(String(64))
    operating_system: Mapped[str | None] = mapped_column(String(64))
    device_type: Mapped[str | None] = mapped_column(String(24))
    session_id: Mapped[str | None] = mapped_column(String(64), index=True)
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    http_method: Mapped[str | None] = mapped_column(String(8))
    http_path: Mapped[str | None] = mapped_column(String(512))
    http_status: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    actor = relationship("User", lazy="joined")
