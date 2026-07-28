"""Experiments and executions - the core scientific record."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import ExecutionStatus, ExperimentStatus


class Experiment(UUIDMixin, TimestampMixin, Base):
    """A campaign of executions run under one pinned set of frozen conditions.

    Pinning the three prompt versions and the limit profile at the experiment
    level is what makes "any difference is attributable to the model" a
    structural guarantee rather than a convention.
    """

    __tablename__ = "experiments"

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    hypothesis: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(24), default=ExperimentStatus.DRAFT.value, nullable=False, index=True
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )

    # ── Frozen experimental conditions ──────────────────────────────────────
    system_prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("system_prompt_versions.id", ondelete="RESTRICT")
    )
    technical_context_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("technical_context_versions.id", ondelete="RESTRICT")
    )
    dynamic_prompt_template_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("dynamic_prompt_templates.id", ondelete="RESTRICT")
    )
    limit_profile: Mapped[str] = mapped_column(String(32), nullable=False)
    handedness: Mapped[str] = mapped_column(String(8), default="right", nullable=False)
    #: SHA-256 of system + technical context. Executions sharing it are directly
    #: comparable; a mismatch invalidates cross-run statistics.
    frozen_context_sha256: Mapped[str | None] = mapped_column(String(64), index=True)

    repetitions_per_condition: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    tags: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    owner = relationship("User", back_populates="experiments", lazy="joined")
    project = relationship("Project", back_populates="experiments", lazy="joined")
    executions = relationship(
        "Execution", back_populates="experiment", cascade="all, delete-orphan"
    )


class Execution(UUIDMixin, TimestampMixin, Base):
    """One independent inference. No conversation, no memory, no history.

    Every field the platform needs to reproduce or audit the run is snapshotted
    here, including the literal prompt text, so results survive deletion or
    editing of the referenced configuration rows.
    """

    __tablename__ = "executions"
    __table_args__ = (
        Index("ix_executions_experiment_status", "experiment_id", "status"),
        Index("ix_executions_model_created", "llm_model_id", "created_at"),
        Index("ix_executions_frozen_context", "frozen_context_sha256"),
    )

    experiment_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("experiments.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    triggered_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    #: Identity snapshot: who ran this, preserved independently of the account.
    triggered_by_email: Mapped[str | None] = mapped_column(String(320), index=True)
    repetition_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ── What was run ────────────────────────────────────────────────────────
    llm_model_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("llm_models.id", ondelete="SET NULL"), index=True
    )
    sampling_configuration_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("sampling_configurations.id", ondelete="SET NULL")
    )
    system_prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("system_prompt_versions.id", ondelete="SET NULL")
    )
    technical_context_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("technical_context_versions.id", ondelete="SET NULL")
    )
    dynamic_prompt_template_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("dynamic_prompt_templates.id", ondelete="SET NULL")
    )
    emg_window_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("emg_windows.id", ondelete="SET NULL"), index=True
    )

    #: Immutable copy of provider/model/decoding parameters at run time.
    #: The explicit columns below duplicate part of it deliberately: the JSON
    #: preserves fidelity, the columns make `GROUP BY temperature` a plain query
    #: instead of a JSON traversal across millions of rows.
    model_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    litellm_model: Mapped[str | None] = mapped_column(String(320), index=True)
    provider_slug: Mapped[str | None] = mapped_column(String(64), index=True)
    model_key: Mapped[str | None] = mapped_column(String(256), index=True)
    #: Where the request actually went. Two runs of "the same model" against
    #: different endpoints are not the same condition.
    api_base: Mapped[str | None] = mapped_column(String(512))
    api_flavour: Mapped[str | None] = mapped_column(String(32))

    # ── Decoding parameters as sent ─────────────────────────────────────────
    temperature: Mapped[float | None] = mapped_column(Float, index=True)
    top_p: Mapped[float | None] = mapped_column(Float)
    top_k: Mapped[int | None] = mapped_column(Integer)
    max_tokens: Mapped[int | None] = mapped_column(Integer)
    seed: Mapped[int | None] = mapped_column(Integer)
    frequency_penalty: Mapped[float | None] = mapped_column(Float)
    presence_penalty: Mapped[float | None] = mapped_column(Float)
    stop_sequences: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    response_format: Mapped[str | None] = mapped_column(String(32))
    #: Provider-specific reasoning controls (effort, thinking budget…).
    reasoning_mode: Mapped[str | None] = mapped_column(String(32))
    custom_parameters: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    #: Knobs the runtime silently ignored. Without this a run looks reproducible
    #: when it is not.
    dropped_parameters: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    handedness: Mapped[str] = mapped_column(String(8), default="right", nullable=False)
    limit_profile: Mapped[str] = mapped_column(String(32), nullable=False)
    experiment_type: Mapped[str] = mapped_column(String(48), default="single_inference", nullable=False)

    #: The command a domain expert says this window should have produced.
    #:
    #: Stored on the execution rather than on the EMG window, and copied at run
    #: time rather than joined. A window's label can be corrected later, and if
    #: the comparison read through a foreign key then correcting one label would
    #: silently rewrite the recorded accuracy of every run that used it. An
    #: execution has to stay a fixed account of what was expected *at the time*.
    #:
    #: Never enters a prompt. It is the answer key, and showing the model the
    #: answer key would make every measurement worthless.
    expected_serial_command: Mapped[str | None] = mapped_column(String(128))

    #: Which rendering of the EMG the model was shown: matrix, features, both.
    dynamic_content: Mapped[str] = mapped_column(String(16), default="matrix", nullable=False)
    #: How many matrix rows actually reached the prompt. The window's own row
    #: count is not the same number when a cap is applied, and comparing a run
    #: that saw 404 rows against one that saw 32 without knowing which is which
    #: is how a result gets misread.
    matrix_rows_sent: Mapped[int | None] = mapped_column(Integer)

    # ── The exact prompt sent ───────────────────────────────────────────────
    system_prompt_text: Mapped[str | None] = mapped_column(Text)
    technical_context_text: Mapped[str | None] = mapped_column(Text)
    dynamic_prompt_text: Mapped[str | None] = mapped_column(Text)
    messages_json: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    system_prompt_sha256: Mapped[str | None] = mapped_column(String(64))
    technical_context_sha256: Mapped[str | None] = mapped_column(String(64))
    dynamic_prompt_sha256: Mapped[str | None] = mapped_column(String(64))
    frozen_context_sha256: Mapped[str | None] = mapped_column(String(64))
    full_prompt_sha256: Mapped[str | None] = mapped_column(String(64), index=True)

    # ── What came back ──────────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(24), default=ExecutionStatus.PENDING.value, nullable=False, index=True
    )
    raw_response: Mapped[str | None] = mapped_column(Text)
    parsed_response: Mapped[dict | None] = mapped_column(JSONB)
    finish_reason: Mapped[str | None] = mapped_column(String(48))
    provider_response_id: Mapped[str | None] = mapped_column(String(160))

    # ── Cost & latency ──────────────────────────────────────────────────────
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[int | None] = mapped_column(Integer, index=True)
    time_to_first_token_ms: Mapped[int | None] = mapped_column(Integer)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    #: 8 decimals: local LM Studio runs are 0, hosted models can be sub-cent.
    cost_usd: Mapped[float] = mapped_column(Numeric(14, 8), default=0, nullable=False)
    tokens_per_second: Mapped[float | None] = mapped_column(Float)

    # ── Outcome ─────────────────────────────────────────────────────────────
    validation_passed: Mapped[bool | None] = mapped_column(Boolean, index=True)
    simulator_executed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    retry_of_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("executions.id", ondelete="SET NULL")
    )
    warning_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ── Origin of the request ───────────────────────────────────────────────
    #: Recorded so a result can be traced to the machine and session that
    #: produced it. `client_ip` is nullable and may be disabled by policy.
    client_ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    browser: Mapped[str | None] = mapped_column(String(64))
    operating_system: Mapped[str | None] = mapped_column(String(64))
    device_type: Mapped[str | None] = mapped_column(String(24))
    session_id: Mapped[str | None] = mapped_column(String(64), index=True)
    #: Correlates this execution with its audit entries and log lines.
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    app_version: Mapped[str | None] = mapped_column(String(32))

    experiment = relationship("Experiment", back_populates="executions")
    emg_window = relationship("EmgWindowRecord", back_populates="executions", lazy="joined")
    system_prompt_version = relationship("SystemPromptVersion", back_populates="executions")
    technical_context_version = relationship("TechnicalContextVersion", back_populates="executions")
    dynamic_prompt_template = relationship("DynamicPromptTemplate", back_populates="executions")
    validation_result = relationship(
        "ValidationResult", back_populates="execution",
        uselist=False, cascade="all, delete-orphan", lazy="joined",
    )
    metrics = relationship(
        "ExecutionMetric", back_populates="execution",
        uselist=False, cascade="all, delete-orphan", lazy="joined",
    )
    movement = relationship(
        "SimulatorMovement", back_populates="execution",
        uselist=False, cascade="all, delete-orphan", lazy="joined",
    )
    errors = relationship(
        "ExecutionError", back_populates="execution", cascade="all, delete-orphan"
    )
    logs = relationship(
        "ExecutionLog", back_populates="execution",
        cascade="all, delete-orphan", order_by="ExecutionLog.sequence",
    )
    project = relationship("Project", lazy="joined")
