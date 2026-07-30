"""Every command that reached the simulator or the prosthesis.

Distinct from :class:`SimulatorMovement`, which records the pose an execution
*resolved to*. This records the **transmission**: where the command went,
whether it arrived, and what produced it.

The difference matters as soon as real hardware is attached. A pose that
resolved is not a pose that was delivered — the link may be closed, or may drop
mid-session — and without a transmission log there is no way to answer "did the
hand actually receive this?", which is the first question after any unexpected
movement.

It also covers commands that never came from a model at all: a manual test typed
into the interface to check the wiring, or a replay of a stored movement. Those
move the hand exactly as a model's command does, so they belong in the same log.
Keeping them out would leave a record that explains only some of the movements
that happened.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MovementSource(str, Enum):
    """What produced the command."""

    #: A model response that cleared all seven validation stages.
    EXECUTION = "execution"
    #: A command typed into the interface to test the link or the mechanics.
    MANUAL = "manual"
    #: A stored, previously validated movement re-sent from the record.
    REPLAY = "replay"


class MovementLogEntry(Base):
    """One transmission, to one or both destinations."""

    __tablename__ = "movement_log"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # ── What was sent ────────────────────────────────────────────────────────
    serial_command: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    handedness: Mapped[str] = mapped_column(String(8), default="right", nullable=False)
    #: Resolved positions, so the log can be read without re-parsing the command.
    actuator_positions: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    # ── Where it came from ───────────────────────────────────────────────────
    source: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    execution_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("executions.id", ondelete="SET NULL"), index=True
    )
    triggered_by_email: Mapped[str | None] = mapped_column(String(320))

    # ── Where it went ────────────────────────────────────────────────────────
    #
    # Two independent booleans rather than one destination field. The simulator
    # always renders; the prosthesis only when a link is open; and either can
    # fail while the other succeeds. A single field would force a lie in the
    # common case where one arrived and the other did not.
    sent_to_simulator: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sent_to_prosthesis: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: "serial" or "ble" when it reached hardware; NULL when it did not.
    transport: Mapped[str | None] = mapped_column(String(16))
    delivery_error: Mapped[str | None] = mapped_column(Text)

    notes: Mapped[str | None] = mapped_column(Text)
