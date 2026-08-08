"""Request/response contracts for the HTTP API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.hand_spec import Handedness, LimitProfileId
from app.prompts.dynamic_prompt import DynamicContent
from app.schemas.emg import EmgWindow
from app.schemas.multimodal import MechanicalTelemetry

# ═════════════════════════════════════════════════════════════════════════════
# Providers & models
# ═════════════════════════════════════════════════════════════════════════════


class ProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    display_name: str
    litellm_prefix: str
    api_base: str | None
    requires_api_key: bool
    is_local: bool
    is_enabled: bool
    notes: str | None = None


class ModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_id: uuid.UUID
    model_key: str
    display_name: str
    family: str | None = None
    parameter_count_b: float | None = None
    quantisation: str | None = None
    context_window: int | None = None
    max_output_tokens: int | None = None
    supports_json_mode: bool
    supports_json_schema: bool
    supports_seed: bool
    supports_top_k: bool
    supports_penalties: bool
    input_cost_per_1k: float
    output_cost_per_1k: float
    is_enabled: bool
    #: For local runtimes: is this model loaded right now? ``None`` means the
    #: question does not apply (hosted provider) or the runtime was unreachable,
    #: which is different from "not loaded" and is reported as such.
    is_available: bool | None = None


class ModelCreate(BaseModel):
    provider_id: uuid.UUID
    model_key: str = Field(max_length=256)
    display_name: str = Field(max_length=256)
    family: str | None = None
    parameter_count_b: float | None = None
    quantisation: str | None = None
    context_window: int | None = None
    max_output_tokens: int | None = None
    supports_json_mode: bool = True
    supports_json_schema: bool = False
    supports_seed: bool = False
    supports_top_k: bool = False
    supports_penalties: bool = True
    input_cost_per_1k: float = 0.0
    output_cost_per_1k: float = 0.0


class LmStudioProbeOut(BaseModel):
    """Live view of what LM Studio currently has loaded."""

    reachable: bool
    api_base: str
    error: str | None = None
    models: list[dict[str, Any]] = Field(default_factory=list)


class LmStudioSyncOut(BaseModel):
    imported: list[ModelOut]
    already_known: list[str]
    api_base: str


# ═════════════════════════════════════════════════════════════════════════════
# Sampling configurations & lab presets
# ═════════════════════════════════════════════════════════════════════════════


class SamplingConfigurationIn(BaseModel):
    name: str = Field(max_length=160)
    description: str | None = None
    model_id: uuid.UUID
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    top_p: float = Field(default=1.0, gt=0.0, le=1.0)
    top_k: int | None = Field(default=None, ge=1, le=500)
    #: A complete reply is the command line: one to four tokens. This shares the
    #: context window with the prompt, so anything generous is budget taken from
    #: the EMG matrix for nothing. 64 leaves ample room for a model that pads.
    max_tokens: int = Field(default=64, ge=1, le=131_072)
    seed: int | None = None
    frequency_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    presence_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    stop_sequences: list[str] = Field(default_factory=list, max_length=8)
    response_format: str = Field(default="json_object", pattern="^(text|json_object|json_schema)$")
    #: Suppress the model's thinking channel. On by default: a reasoning model
    #: given a hard classification can spend its whole budget deliberating and
    #: return an empty answer.
    disable_reasoning: bool = True
    extra_params: dict[str, Any] = Field(default_factory=dict)
    is_favorite: bool = False


class SamplingConfigurationOut(SamplingConfigurationIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    use_count: int
    created_at: datetime
    updated_at: datetime


class LabPresetIn(BaseModel):
    name: str = Field(max_length=160)
    description: str | None = None
    sampling_configuration_id: uuid.UUID
    system_prompt_version_id: uuid.UUID
    technical_context_version_id: uuid.UUID
    dynamic_prompt_template_id: uuid.UUID
    handedness: Handedness = Handedness.RIGHT
    limit_profile: LimitProfileId = LimitProfileId.TABLE_5_V3
    merge_context_into_system: bool = True
    is_favorite: bool = False


class LabPresetOut(LabPresetIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    use_count: int
    last_used_at: datetime | None = None
    created_at: datetime


# ═════════════════════════════════════════════════════════════════════════════
# Prompt artefacts
# ═════════════════════════════════════════════════════════════════════════════


class PromptVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    version: str
    content: str
    content_sha256: str
    description: str | None = None
    is_active: bool
    is_system_default: bool
    char_count: int
    created_at: datetime


class SystemPromptIn(BaseModel):
    name: str = Field(max_length=160)
    version: str = Field(max_length=32)
    content: str = Field(min_length=1)
    description: str | None = None
    activate: bool = False


class TechnicalContextIn(SystemPromptIn):
    limit_profile: LimitProfileId = LimitProfileId.TABLE_5_V3
    includes_json_schema: bool = True


class TechnicalContextOut(PromptVersionOut):
    limit_profile: str
    generated_from_domain: bool
    includes_json_schema: bool


class EmgContextIn(SystemPromptIn):
    """Block 3 — how EMG should be interpreted."""


class EmgContextOut(PromptVersionOut):
    generated_from_domain: bool


class DynamicTemplateIn(SystemPromptIn):
    include_channel_sites: bool = True
    include_extended_features: bool = True


class DynamicTemplateOut(PromptVersionOut):
    include_channel_sites: bool
    include_extended_features: bool


class PromptPreviewIn(BaseModel):
    """Assemble the exact prompt without spending a token.

    Backs the read-only 'Dynamic Prompt' viewer in the left panel: the
    researcher sees precisely what the backend will send, but never edits it.
    """

    window: EmgWindow
    mechanical_telemetry: MechanicalTelemetry | None = None
    mvc_by_channel: list[float] | None = Field(default=None, min_length=8, max_length=8)
    handedness: Handedness = Handedness.RIGHT
    #: Supplied so the preview can compare against that model's context window.
    model_id: uuid.UUID | None = None
    system_prompt_version_id: uuid.UUID | None = None
    technical_context_version_id: uuid.UUID | None = None
    emg_context_version_id: uuid.UUID | None = None
    dynamic_prompt_template_id: uuid.UUID | None = None
    system_prompt_override: str | None = None
    technical_context_override: str | None = None
    emg_context_override: str | None = None
    dynamic_template_override: str | None = None
    #: What the dynamic block carries: the raw matrix, the derived descriptors,
    #: or both. An experimental variable, not a display preference.
    dynamic_content: DynamicContent = DynamicContent.MATRIX
    #: Cap on printed matrix rows. None (the default) sends the whole window.
    matrix_max_rows: int | None = Field(default=None, ge=1)
    #: The command a domain expert says this window should produce. Optional,
    #: stored verbatim, and compared against what the model returned. It is a
    #: label, never an input: it is not placed in any prompt.
    expected_serial_command: str | None = Field(default=None, max_length=128)
    limit_profile: LimitProfileId | None = None
    experiment_type: str = "single_inference"
    subject_ref: str | None = None
    subject_notes: str | None = None
    extra_parameters: dict[str, Any] = Field(default_factory=dict)
    merge_context_into_system: bool = True


class PromptPreviewOut(BaseModel):
    system_prompt: str
    technical_context: str
    emg_context: str
    dynamic_prompt: str
    full_prompt: str
    messages: list[dict[str, str]]
    limit_profile: str
    char_counts: dict[str, int]
    system_prompt_sha256: str
    technical_context_sha256: str
    emg_context_sha256: str
    dynamic_prompt_sha256: str
    frozen_context_sha256: str
    full_prompt_sha256: str
    #: Weighted estimate. A plain characters/4 heuristic under-counts this
    #: content by more than half: the EMG matrix is almost entirely numbers, and
    #: a signed three-decimal value costs three to four tokens.
    estimated_prompt_tokens: int
    token_breakdown: dict[str, int] = Field(default_factory=dict)
    context_window: int | None = None
    fits_context: bool = True
    budget_advice: list[str] = Field(default_factory=list)
    #: What the preview actually rendered. Echoed back so the panel can state
    #: "64 of 404 rows" from the server's own answer rather than re-deriving it
    #: and risking a figure that disagrees with the text beside it.
    matrix_rows_sent: int = 0
    dynamic_content: str = "matrix"


# ═════════════════════════════════════════════════════════════════════════════
# Executions
# ═════════════════════════════════════════════════════════════════════════════


class RunExecutionIn(BaseModel):
    """Payload behind the "Run Evaluation" button."""

    #: The model is resolved from this. Accepting a separate `model_id` would
    #: create two ways to say which model runs, and therefore a way for them to
    #: disagree.
    sampling_configuration_id: uuid.UUID
    invocation_mode: Literal["structured_output", "tool_calling"] = "structured_output"
    window: EmgWindow
    mechanical_telemetry: MechanicalTelemetry | None = None
    mvc_by_channel: list[float] | None = Field(default=None, min_length=8, max_length=8)
    handedness: Handedness = Handedness.RIGHT
    system_prompt_version_id: uuid.UUID | None = None
    technical_context_version_id: uuid.UUID | None = None
    emg_context_version_id: uuid.UUID | None = None
    dynamic_prompt_template_id: uuid.UUID | None = None
    system_prompt_override: str | None = None
    technical_context_override: str | None = None
    emg_context_override: str | None = None
    dynamic_template_override: str | None = None
    #: What the dynamic block carries: the raw matrix, the derived descriptors,
    #: or both. An experimental variable, not a display preference.
    dynamic_content: DynamicContent = DynamicContent.MATRIX
    #: Cap on printed matrix rows. None (the default) sends the whole window.
    matrix_max_rows: int | None = Field(default=None, ge=1)
    #: The command a domain expert says this window should produce. Optional,
    #: stored verbatim, and compared against what the model returned. It is a
    #: label, never an input: it is not placed in any prompt.
    expected_serial_command: str | None = Field(default=None, max_length=128)
    limit_profile: LimitProfileId | None = None
    experiment_id: uuid.UUID | None = None
    experiment_type: str = "single_inference"
    subject_ref: str | None = None
    subject_notes: str | None = None
    extra_parameters: dict[str, Any] = Field(default_factory=dict)
    merge_context_into_system: bool = True
    #: Repeat the identical execution N times to measure determinism.
    repetitions: int = Field(default=1, ge=1, le=50)


class ValidationIssueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stage: str
    code: str
    severity: str
    message: str
    field_path: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class ValidationResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    passed: bool
    limit_profile: str
    failed_stage: str | None = None
    stages_completed: list[str] = Field(default_factory=list)
    error_count: int
    warning_count: int
    normalised_serial: str | None = None
    issues: list[ValidationIssueOut] = Field(default_factory=list)


class MovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    handedness: str
    limit_profile: str
    source: str
    serial_command: str | None = None
    actuator_positions: dict[str, Any] = Field(default_factory=dict)
    actuator_normalised: dict[str, Any] = Field(default_factory=dict)
    joint_angles: list[dict[str, Any]] = Field(default_factory=list)
    duration_ms: int


class MetricsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    is_valid_json: bool
    is_bare_json: bool
    schema_compliant: bool
    protocol_compliant: bool
    consistency_compliant: bool | None = None
    #: NULL when no expected command was given: "not compared" and "compared
    #: and wrong" are different facts and must not share a value.
    command_matches_expected: bool | None = None
    within_mechanical_limits: bool
    safety_compliant: bool
    ground_truth_gesture: str | None = None
    predicted_gesture: str | None = None
    gesture_correct: bool | None = None
    detected_pattern: str | None = None
    pose_mae: float | None = None
    pose_similarity: float | None = None
    model_confidence: float | None = None
    calibration_error: float | None = None
    actuators_commanded: int
    intent: str | None = None
    used_preset_gesture: bool
    refused_to_act: bool
    latency_ms: int | None = None
    tokens_per_second: float | None = None
    cost_usd: float
    response_fingerprint: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class ExecutionErrorOut(BaseModel):
    """A hard failure — provider outage, malformed response, platform bug.

    Carried on the execution because a provider rejection produces no validation
    result at all: without this the interface can only report that something
    failed, never what.
    """

    model_config = ConfigDict(from_attributes=True)

    category: str
    error_type: str
    message: str
    provider_status_code: int | None = None
    provider_error_code: str | None = None
    is_retryable: bool
    context: dict[str, Any] = Field(default_factory=dict)


class ExecutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    experiment_id: uuid.UUID | None = None
    status: str
    repetition_index: int
    litellm_model: str | None = None
    provider_slug: str | None = None
    handedness: str
    limit_profile: str
    experiment_type: str
    raw_response: str | None = None
    parsed_response: dict[str, Any] | None = None
    custom_parameters: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float
    tokens_per_second: float | None = None
    validation_passed: bool | None = None
    simulator_executed: bool
    #: What the researcher said this window should produce, and whether the
    #: model matched it. Both stored on the execution so a row in the dashboard
    #: is self-contained: the comparison cannot silently change later because
    #: someone relabelled the window.
    expected_serial_command: str | None = None
    dynamic_content: str | None = None
    matrix_rows_sent: int | None = None
    #: Which distinct frozen prompt setup produced this result.
    prompt_configuration_id: uuid.UUID | None = None
    prompt_configuration_label: str | None = None
    frozen_context_sha256: str | None = None
    full_prompt_sha256: str | None = None
    created_at: datetime
    validation_result: ValidationResultOut | None = None
    metrics: MetricsOut | None = None
    movement: MovementOut | None = None
    errors: list[ExecutionErrorOut] = Field(default_factory=list)


class RunExecutionOut(BaseModel):
    executions: list[ExecutionOut]
    determinism: dict[str, Any] | None = None


# ═════════════════════════════════════════════════════════════════════════════
# Experiments & comparison
# ═════════════════════════════════════════════════════════════════════════════


class ModelSummary(BaseModel):
    """One model's record, aggregated in SQL."""

    litellm_model: str
    provider_slug: str | None = None
    executions: int
    passed: int
    pass_rate: float
    mean_latency_ms: float | None = None
    total_tokens: int
    total_cost_usd: float
    last_run_at: datetime | None = None


class ConfigurationModelResult(BaseModel):
    """One model's record under one configuration."""

    litellm_model: str
    executions: int
    passed: int
    pass_rate: float
    command_labelled: int = 0
    command_matched: int = 0
    command_accuracy: float | None = None
    mean_latency_ms: float | None = None
    last_run_at: datetime | None = None


class PromptConfigurationOut(BaseModel):
    """A distinct frozen prompt setup, and what each model did under it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    frozen_context_sha256: str
    system_prompt_version: str | None = None
    technical_context_version: str | None = None
    emg_context_version: str | None = None
    first_used_at: datetime
    last_used_at: datetime
    executions: int = 0
    #: Broken out per model, because a configuration is only comparable within
    #: one. Averaging a 4B model and a 30B model under the same prompt produces
    #: a number that describes neither.
    by_model: list[ConfigurationModelResult] = Field(default_factory=list)


class ManualCommandIn(BaseModel):
    """A command typed by a researcher to test the link or the mechanics."""

    serial_command: str = Field(max_length=128)
    handedness: Handedness = Handedness.RIGHT
    limit_profile: LimitProfileId | None = None
    notes: str | None = None


class ManualCommandOut(BaseModel):
    id: uuid.UUID
    serial_command: str
    normalised_serial: str | None = None
    actuator_positions: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int | None = None
    #: How many simulator clients received it. Zero means nothing is watching,
    #: which is a different situation from a rejected command and worth saying.
    simulator_clients: int = 0
    warnings: list[str] = Field(default_factory=list)


class MovementLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    serial_command: str
    handedness: str
    actuator_positions: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int | None = None
    source: str
    execution_id: uuid.UUID | None = None
    triggered_by_email: str | None = None
    sent_to_simulator: bool
    sent_to_prosthesis: bool
    transport: str | None = None
    delivery_error: str | None = None
    notes: str | None = None


class ExecutionStats(BaseModel):
    """Headline numbers for the dashboard.

    Computed in the database rather than over whatever page the client happens
    to have loaded: aggregating a visible slice and presenting it as the whole
    is how a dashboard starts lying.
    """

    executions: int
    passed: int
    failed: int
    provider_errors: int
    pass_rate: float | None = None
    distinct_models: int
    distinct_windows: int
    mean_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    total_tokens: int
    total_cost_usd: float
    first_run_at: datetime | None = None
    last_run_at: datetime | None = None
    by_model: list[ModelSummary] = Field(default_factory=list)
    top_failure_codes: list[dict[str, Any]] = Field(default_factory=list)
    #: False when the set spans more than one frozen context, in which case the
    #: per-model rows are not a fair comparison.
    comparable: bool = True

    #: Accuracy against the expected commands the researcher supplied.
    #: `command_labelled` is the denominator and is reported explicitly: an
    #: accuracy of 1.00 over three runs and over three hundred are different
    #: claims, and a bare percentage hides which one is on screen.
    command_labelled: int = 0
    command_matched: int = 0
    command_accuracy: float | None = None


class ExperimentIn(BaseModel):
    name: str = Field(max_length=200)
    description: str | None = None
    hypothesis: str | None = None
    system_prompt_version_id: uuid.UUID | None = None
    technical_context_version_id: uuid.UUID | None = None
    dynamic_prompt_template_id: uuid.UUID | None = None
    limit_profile: LimitProfileId = LimitProfileId.TABLE_5_V3
    handedness: Handedness = Handedness.RIGHT
    repetitions_per_condition: int = Field(default=1, ge=1, le=50)
    tags: list[str] = Field(default_factory=list)


class ExperimentOut(ExperimentIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    frozen_context_sha256: str | None = None
    created_at: datetime


class ModelComparisonRow(BaseModel):
    """One row of the cross-model leaderboard."""

    litellm_model: str
    provider_slug: str | None = None
    executions: int
    validation_pass_rate: float
    json_validity_rate: float
    schema_compliance_rate: float
    within_limits_rate: float
    gesture_accuracy: float | None = None
    mean_confidence: float | None = None
    mean_calibration_error: float | None = None
    mean_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    mean_tokens_per_second: float | None = None
    total_cost_usd: float
    determinism_rate: float | None = None
    top_failure_codes: list[dict[str, Any]] = Field(default_factory=list)


class ComparisonOut(BaseModel):
    experiment_id: uuid.UUID | None = None
    frozen_context_sha256: str | None = None
    comparable: bool = Field(
        description="False when the rows were produced under different frozen "
        "contexts, in which case differences cannot be attributed to the model."
    )
    rows: list[ModelComparisonRow]


# ═════════════════════════════════════════════════════════════════════════════
# Hand specification (consumed by the 3D simulator)
# ═════════════════════════════════════════════════════════════════════════════


class HandSpecOut(BaseModel):
    driven_dof: int
    kinematic_dof: int
    potentiometer_count: int
    fsr_count: int
    actuators: list[dict[str, Any]]
    joints: list[dict[str, Any]]
    gestures: list[dict[str, Any]]
    limit_profiles: list[dict[str, Any]]
    protocol: dict[str, Any]
    safety: dict[str, Any]
    emg: dict[str, Any]
