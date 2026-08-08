"""Human or sensor feedback about a physically executed gesture."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class GestureFeedback(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "gesture_feedback"

    execution_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("executions.id", ondelete="CASCADE"), index=True
    )
    evaluator_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    evaluator_email: Mapped[str | None] = mapped_column(String(320))
    source: Mapped[str] = mapped_column(String(24), default="human", nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    score: Mapped[int | None] = mapped_column(Integer)
    expected_gesture: Mapped[str | None] = mapped_column(String(64))
    observed_gesture: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)
    sensor_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    correction_attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    correction_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("executions.id", ondelete="SET NULL")
    )
