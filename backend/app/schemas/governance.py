"""Contracts for projects, auditing, traceability and export."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.audit import AuditAction, AuditOutcome

# ═════════════════════════════════════════════════════════════════════════════
# Projects
# ═════════════════════════════════════════════════════════════════════════════


class ProjectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(default=None, max_length=120)
    description: str | None = None
    research_question: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=32)
    settings: dict[str, Any] = Field(default_factory=dict)

    @field_validator("slug")
    @classmethod
    def _slug_shape(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().lower().replace(" ", "-")
        if not cleaned.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Slug may contain only letters, digits, hyphens and underscores.")
        return cleaned


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    research_question: str | None = None
    status: Literal["active", "paused", "archived"] | None = None
    tags: list[str] | None = None
    settings: dict[str, Any] | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    description: str | None = None
    research_question: str | None = None
    status: str
    owner_id: uuid.UUID | None = None
    owner_email: str | None = None
    tags: list[str] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)
    is_deleted: bool
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ProjectStats(BaseModel):
    """Headline numbers for a project, for the overview screen."""

    project_id: uuid.UUID
    experiments: int
    executions: int
    successful_executions: int
    failed_executions: int
    distinct_models: int
    total_tokens: int
    total_cost_usd: float
    mean_latency_ms: float | None = None
    first_execution_at: datetime | None = None
    last_execution_at: datetime | None = None


# ═════════════════════════════════════════════════════════════════════════════
# Audit
# ═════════════════════════════════════════════════════════════════════════════


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    actor_id: uuid.UUID | None = None
    actor_email: str | None = None
    actor_role: str | None = None
    action: str
    outcome: str
    summary: str
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    entity_label: str | None = None
    project_id: uuid.UUID | None = None
    changes: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    client_ip: str | None = None
    browser: str | None = None
    operating_system: str | None = None
    device_type: str | None = None
    session_id: str | None = None
    request_id: str | None = None
    http_method: str | None = None
    http_path: str | None = None
    http_status: int | None = None


class AuditQuery(BaseModel):
    """Filters for the audit browser."""

    model_config = ConfigDict(extra="forbid")

    action: AuditAction | None = None
    outcome: AuditOutcome | None = None
    actor_email: str | None = None
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    since: datetime | None = None
    until: datetime | None = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class AuditActionInfo(BaseModel):
    value: str
    group: str
    description: str


# ═════════════════════════════════════════════════════════════════════════════
# Traceability
# ═════════════════════════════════════════════════════════════════════════════


class ExecutionLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sequence: int
    level: str
    stage: str
    message: str
    context: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class TraceabilityRecord(BaseModel):
    """Everything needed to reconstruct one past experiment.

    Answers, in one payload: what prompt, which model, which parameters, what
    stimulus, what came back, how long it took, how many tokens, who ran it and
    when. If a field here is empty, that run is not reproducible — which is
    itself the finding.
    """

    execution_id: uuid.UUID
    executed_at: datetime
    status: str
    reproducible: bool = Field(
        description="True when prompt text, model, parameters and stimulus were "
        "all captured. False means the run cannot be replayed faithfully."
    )
    missing_for_reproduction: list[str] = Field(default_factory=list)

    # Who and where
    actor: dict[str, Any] = Field(default_factory=dict)
    origin: dict[str, Any] = Field(default_factory=dict)

    # Organisation
    project: dict[str, Any] | None = None
    experiment: dict[str, Any] | None = None

    # What was asked
    prompt: dict[str, Any] = Field(default_factory=dict)
    model: dict[str, Any] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    stimulus: dict[str, Any] = Field(default_factory=dict)

    # What came back
    response: dict[str, Any] = Field(default_factory=dict)
    performance: dict[str, Any] = Field(default_factory=dict)
    validation: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None
    movement: dict[str, Any] | None = None

    errors: list[dict[str, Any]] = Field(default_factory=list)
    logs: list[ExecutionLogOut] = Field(default_factory=list)
    audit: list[AuditLogOut] = Field(default_factory=list)


# ═════════════════════════════════════════════════════════════════════════════
# Export
# ═════════════════════════════════════════════════════════════════════════════


class ExportFormat(str):
    CSV = "csv"
    JSON = "json"
    JSONL = "jsonl"


class ExportRequest(BaseModel):
    """Pull the experimental record out for statistical analysis."""

    model_config = ConfigDict(extra="forbid")

    project_id: uuid.UUID | None = None
    experiment_id: uuid.UUID | None = None
    since: datetime | None = None
    until: datetime | None = None
    litellm_model: str | None = None
    only_validated: bool = Field(
        default=False,
        description="Restrict to executions that cleared validation. Off by "
        "default: failures are data, and excluding them silently biases any "
        "success-rate computed downstream.",
    )
    include_prompts: bool = Field(
        default=False,
        description="Include the full prompt text. Off by default because it "
        "multiplies file size by roughly thirty.",
    )
    include_raw_response: bool = False
    include_emg_matrix: bool = Field(
        default=False,
        description="Include the raw sample matrix. Very large; usually the "
        "checksum is enough to join against the stored window.",
    )
    limit: int = Field(default=10_000, ge=1, le=200_000)
