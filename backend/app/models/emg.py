"""Stored EMG windows and live acquisition sessions."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class EmgWindowRecord(UUIDMixin, TimestampMixin, Base):
    """One analysis window - the experimental stimulus.

    The raw ``samples`` matrix is the primary record; ``features`` is a
    denormalised cache of the descriptors derived from it, stored so that
    cross-model queries do not have to recompute them over thousands of rows.

    Windows are content-addressed via ``checksum`` (a hash of the matrix and
    sampling rate alone), so replaying the same physiological input across
    models is provable rather than assumed.
    """

    __tablename__ = "emg_windows"

    #: "manual" | "live" | "dataset" | "synthetic"
    source_mode: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    sample_rate_hz: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Raw matrix: N rows (time steps) x 8 columns (CH1..CH8), amplitudes in [-1, 1].
    samples: Mapped[list] = mapped_column(JSONB, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    window_ms: Mapped[float] = mapped_column(Float, nullable=False)
    #: [{label, rms, mav, zc, ssc, wl, min, max, variance}, ...] - always 8 entries.
    features: Mapped[list] = mapped_column(JSONB, nullable=False)
    #: Denormalised mean RMS across the 8 channels, indexed for fast filtering.
    mean_rms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, index=True)
    ground_truth_gesture: Mapped[str | None] = mapped_column(String(32), index=True)
    subject_ref: Mapped[str | None] = mapped_column(String(64), index=True)
    session_id: Mapped[str | None] = mapped_column(String(64), index=True)
    sequence: Mapped[int | None] = mapped_column(Integer)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text)

    executions = relationship("Execution", back_populates="emg_window")


class EmgStreamSession(UUIDMixin, TimestampMixin, Base):
    """A live acquisition session opened over the WebSocket endpoint."""

    __tablename__ = "emg_stream_sessions"

    session_key: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    experiment_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("experiments.id", ondelete="SET NULL"), index=True
    )
    device_label: Mapped[str | None] = mapped_column(String(160))
    subject_ref: Mapped[str | None] = mapped_column(String(64))
    frames_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    executions_triggered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
