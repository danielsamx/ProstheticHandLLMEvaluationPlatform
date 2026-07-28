"""Per-execution scientific metrics and the resulting simulator movement."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class ExecutionMetric(UUIDMixin, TimestampMixin, Base):
    """Derived measures. One row per execution, wide by design so that
    cross-model aggregation is a plain SQL GROUP BY."""

    __tablename__ = "execution_metrics"

    execution_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("executions.id", ondelete="CASCADE"),
        unique=True, index=True, nullable=False,
    )

    # ── Format compliance ───────────────────────────────────────────────────
    is_valid_json: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: True when the model returned bare JSON with no fences or prose.
    is_bare_json: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    schema_compliant: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    protocol_compliant: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: The serial_command agreed with the intent, gesture and commands stated
    #: beside it. Nullable: executions recorded under the bare-command contract
    #: carried one representation, so there was nothing that could disagree and
    #: `false` would assert a failure that never happened.
    consistency_compliant: Mapped[bool | None] = mapped_column(Boolean, index=True)
    within_mechanical_limits: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    safety_compliant: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ── Task accuracy (only when the EMG window is labelled) ────────────────
    ground_truth_gesture: Mapped[str | None] = mapped_column(String(32), index=True)
    predicted_gesture: Mapped[str | None] = mapped_column(String(32), index=True)
    gesture_correct: Mapped[bool | None] = mapped_column(Boolean, index=True)
    detected_pattern: Mapped[str | None] = mapped_column(String(64), index=True)
    #: Mean absolute normalised error between commanded and reference pose.
    pose_mae: Mapped[float | None] = mapped_column(Float)
    #: 1 - normalised L2 distance to the reference pose, in [0, 1].
    pose_similarity: Mapped[float | None] = mapped_column(Float)

    # ── Model behaviour ─────────────────────────────────────────────────────
    model_confidence: Mapped[float | None] = mapped_column(Float)
    #: |confidence - correctness|: how well calibrated the model's self-report is.
    calibration_error: Mapped[float | None] = mapped_column(Float)
    actuators_commanded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(24), index=True)
    used_preset_gesture: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    refused_to_act: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ── Efficiency ──────────────────────────────────────────────────────────
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    tokens_per_second: Mapped[float | None] = mapped_column(Float)
    cost_usd: Mapped[float] = mapped_column(Numeric(14, 8), default=0, nullable=False)
    output_token_efficiency: Mapped[float | None] = mapped_column(
        Float, doc="Useful JSON characters divided by completion tokens."
    )

    # ── Determinism (filled by repeated-run analysis) ───────────────────────
    #: SHA-256 of the canonicalised parsed response; identical digests across
    #: repetitions at temperature 0 prove the model is deterministic.
    response_fingerprint: Mapped[str | None] = mapped_column(String(64), index=True)
    repetition_group: Mapped[str | None] = mapped_column(String(64), index=True)

    extra: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    execution = relationship("Execution", back_populates="metrics")


class SimulatorMovement(UUIDMixin, TimestampMixin, Base):
    """The pose the 3D simulator actually rendered.

    A row exists only when validation passed; a failed execution leaves the
    simulator untouched and this table records nothing, which is itself the
    audit trail that the safety gate held.
    """

    __tablename__ = "simulator_movements"

    execution_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("executions.id", ondelete="CASCADE"),
        unique=True, index=True, nullable=False,
    )
    handedness: Mapped[str] = mapped_column(String(8), nullable=False)
    limit_profile: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(48), nullable=False)
    serial_command: Mapped[str | None] = mapped_column(String(160))
    #: {"A": 320, "B": 180, ...}
    actuator_positions: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    actuator_normalised: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    #: [{joint_id, digit, joint_type, angle_deg, normalised, driven_by}, ...]
    joint_angles: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    was_rendered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: True once the same frame has been forwarded to physical hardware.
    dispatched_to_hardware: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    execution = relationship("Execution", back_populates="movement")
