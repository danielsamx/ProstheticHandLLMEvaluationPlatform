"""Validation outcomes, individual issues and hard errors."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class ValidationResult(UUIDMixin, TimestampMixin, Base):
    """Verdict of the seven-stage pipeline for one execution."""

    __tablename__ = "validation_results"

    execution_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("executions.id", ondelete="CASCADE"),
        unique=True, index=True, nullable=False,
    )
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    limit_profile: Mapped[str] = mapped_column(String(32), nullable=False)
    #: First stage that produced an error, or NULL when everything passed.
    failed_stage: Mapped[str | None] = mapped_column(String(24), index=True)
    stages_completed: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    warning_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    normalised_serial: Mapped[str | None] = mapped_column(String(160))
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    execution = relationship("Execution", back_populates="validation_result")
    issues = relationship(
        "ValidationIssueRecord", back_populates="result",
        cascade="all, delete-orphan", lazy="selectin",
    )


class ValidationIssueRecord(UUIDMixin, TimestampMixin, Base):
    """One error or warning. Aggregating ``code`` across executions is the
    primary way of characterising *how* a model fails, not just whether."""

    __tablename__ = "validation_issues"

    validation_result_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("validation_results.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    stage: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    field_path: Mapped[str | None] = mapped_column(String(160))
    context: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    result = relationship("ValidationResult", back_populates="issues")


class ExecutionError(UUIDMixin, TimestampMixin, Base):
    """A hard failure: provider outage, timeout, or platform bug."""

    __tablename__ = "execution_errors"

    execution_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("executions.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    category: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    error_type: Mapped[str] = mapped_column(String(160), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    provider_status_code: Mapped[int | None] = mapped_column(Integer)
    provider_error_code: Mapped[str | None] = mapped_column(String(96))
    is_retryable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    traceback: Mapped[str | None] = mapped_column(Text)
    context: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    execution = relationship("Execution", back_populates="errors")
