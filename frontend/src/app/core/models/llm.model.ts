import { Handedness, LimitProfileId } from './hand.model';

export interface Provider {
  id: string;
  slug: string;
  display_name: string;
  litellm_prefix: string;
  api_base: string | null;
  requires_api_key: boolean;
  is_local: boolean;
  is_enabled: boolean;
  notes?: string | null;
}

export interface LlmModel {
  id: string;
  provider_id: string;
  model_key: string;
  display_name: string;
  family?: string | null;
  parameter_count_b?: number | null;
  quantisation?: string | null;
  context_window?: number | null;
  max_output_tokens?: number | null;
  supports_json_mode: boolean;
  supports_json_schema: boolean;
  supports_seed: boolean;
  supports_top_k: boolean;
  supports_penalties: boolean;
  input_cost_per_1k: number;
  output_cost_per_1k: number;
  is_enabled: boolean;
  /**
   * For local runtimes: is this model loaded right now?
   * `null` means unknown — a hosted provider, or the runtime was unreachable,
   * which is not the same as "not loaded".
   */
  is_available?: boolean | null;
}

export interface SamplingConfiguration {
  id?: string;
  name: string;
  description?: string | null;
  model_id: string;
  temperature: number;
  top_p: number;
  top_k: number | null;
  max_tokens: number;
  seed: number | null;
  frequency_penalty: number;
  presence_penalty: number;
  stop_sequences: string[];
  response_format: 'text' | 'json_object' | 'json_schema';
  /**
   * Suppress the model's thinking channel.
   *
   * The single most consequential setting for a reasoning model on this task. A
   * Qwen3-class model splits its output — working-out to a reasoning channel,
   * answer to `content` — and given a hard classification with a small budget it
   * can spend the whole budget deliberating and return nothing usable.
   */
  disable_reasoning: boolean;
  extra_params: Record<string, unknown>;
  is_favorite: boolean;
  use_count?: number;
  created_at?: string;
}

export interface PromptVersion {
  id: string;
  name: string;
  version: string;
  content: string;
  content_sha256: string;
  description?: string | null;
  is_active: boolean;
  is_system_default: boolean;
  char_count: number;
  created_at: string;
  limit_profile?: LimitProfileId;
  generated_from_domain?: boolean;
  includes_json_schema?: boolean;
}

export interface PromptPreview {
  system_prompt: string;
  technical_context: string;
  emg_context: string;
  /** Block 3: how to read the picture. Generated per window, never stored. */
  image_context: string;
  /** The picture itself. It is the stimulus, so the preview is incomplete
   *  without it — a preview that does not match what will be sent is worse
   *  than no preview, because it is trusted. */
  image_data_url: string | null;
  image_sha256: string | null;
  image_context_sha256: string;
  /** The user turn's text: the derived feature table. */
  dynamic_prompt: string;
  /** Every text block joined. Not the whole stimulus: the picture is not text. */
  full_prompt: string;
  /** `content` is a list of typed parts, because the user turn carries text
   *  plus the image. */
  messages: { role: string; content: unknown }[];
  limit_profile: string;
  char_counts: Record<string, number>;
  system_prompt_sha256: string;
  technical_context_sha256: string;
  emg_context_sha256: string;
  dynamic_prompt_sha256: string;
  frozen_context_sha256: string;
  full_prompt_sha256: string;
  estimated_prompt_tokens: number;
  token_breakdown: Record<string, number>;
  context_window: number | null;
  fits_context: boolean;
  budget_advice: string[];
  /** Which signal was drawn and measured, echoed back by the server so the
   *  panel cannot label the picture from its own copy of the toggle. */
  feature_source: FeatureSource;
}

export interface ValidationIssue {
  stage: string;
  code: string;
  severity: 'error' | 'warning';
  message: string;
  field_path?: string | null;
  context: Record<string, unknown>;
}

export interface ValidationResult {
  passed: boolean;
  limit_profile: string;
  failed_stage: string | null;
  stages_completed: string[];
  error_count: number;
  warning_count: number;
  normalised_serial: string | null;
  issues: ValidationIssue[];
}

/** Which signal the model was shown and measured on.
 *
 *  One switch, both halves of the stimulus: it governs the plotted trace and
 *  the descriptor table together, so the picture and the numbers can never
 *  describe signals that were processed differently.
 *
 *  It replaces `DynamicContent` ('matrix' | 'features' | 'both' | 'semantic'),
 *  which selected between renderings of a text prompt that no longer exists.
 */
export type FeatureSource = 'raw' | 'preprocessed';

export interface ExecutionMetrics {
  is_valid_json: boolean;
  is_bare_json: boolean;
  schema_compliant: boolean;
  protocol_compliant: boolean;
  /** The serial_command agreed with the intent, gesture and commands beside it. */
  consistency_compliant: boolean;
  /** null when no expected command was supplied: not compared, not wrong. */
  command_matches_expected: boolean | null;
  within_mechanical_limits: boolean;
  safety_compliant: boolean;
  ground_truth_gesture: string | null;
  predicted_gesture: string | null;
  gesture_correct: boolean | null;
  detected_pattern: string | null;
  model_confidence: number | null;
  calibration_error: number | null;
  actuators_commanded: number;
  intent: string | null;
  used_preset_gesture: boolean;
  refused_to_act: boolean;
  latency_ms: number | null;
  tokens_per_second: number | null;
  cost_usd: number;
  response_fingerprint: string | null;
  extra: Record<string, unknown>;
}

export interface ExecutionError {
  category: string;
  error_type: string;
  message: string;
  provider_status_code?: number | null;
  provider_error_code?: string | null;
  is_retryable: boolean;
  context: Record<string, unknown>;
}

export interface Execution {
  id: string;
  experiment_id: string | null;
  status: string;
  repetition_index: number;
  litellm_model: string | null;
  provider_slug: string | null;
  handedness: Handedness;
  limit_profile: string;
  experiment_type: string;
  raw_response: string | null;
  parsed_response: Record<string, unknown> | null;
  custom_parameters: Record<string, unknown>;
  latency_ms: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  cost_usd: number;
  tokens_per_second: number | null;
  temperature?: number | null;
  validation_passed: boolean | null;
  simulator_executed: boolean;
  /** The answer key this run was scored against, as it stood at run time. */
  expected_serial_command: string | null;
  /** Leftovers of the removed content switch, still returned because the
   *  columns still hold the executions recorded under it. New runs write
   *  'features' and a null row count; migration 0011 replaces both with the
   *  feature source and the filter parameters. */
  dynamic_content: string | null;
  matrix_rows_sent: number | null;
  /** The distinct frozen prompt setup that produced this result. */
  prompt_configuration_id: string | null;
  prompt_configuration_label: string | null;
  frozen_context_sha256: string | null;
  full_prompt_sha256: string | null;
  created_at: string;
  validation_result: ValidationResult | null;
  metrics: ExecutionMetrics | null;
  movement: {
    handedness: Handedness;
    limit_profile: string;
    source: string;
    serial_command: string | null;
    actuator_positions: Record<string, number>;
    actuator_normalised: Record<string, number>;
    joint_angles: import('./hand.model').JointAngle[];
    duration_ms: number;
  } | null;
  errors: ExecutionError[];
}

export interface RunExecutionResult {
  executions: Execution[];
  determinism: {
    repetitions: number;
    valid_responses?: number;
    distinct_responses: number;
    modal_frequency?: number;
    determinism_rate: number | null;
  } | null;
}

export interface ModelSummary {
  litellm_model: string;
  provider_slug: string | null;
  executions: number;
  passed: number;
  pass_rate: number;
  mean_latency_ms: number | null;
  total_tokens: number;
  total_cost_usd: number;
  last_run_at: string | null;
}

/** Aggregates computed in the database, not over the loaded page. */
export interface ExecutionStats {
  executions: number;
  passed: number;
  failed: number;
  provider_errors: number;
  pass_rate: number | null;
  distinct_models: number;
  distinct_windows: number;
  mean_latency_ms: number | null;
  p95_latency_ms: number | null;
  total_tokens: number;
  total_cost_usd: number;
  first_run_at: string | null;
  last_run_at: string | null;
  by_model: ModelSummary[];
  top_failure_codes: Record<string, unknown>[];
  /** False when the rows span more than one frozen context. */
  comparable: boolean;
  /**
   * Accuracy against the expected commands supplied by the researcher.
   * `command_labelled` is the denominator and is shown alongside the rate:
   * 100% of three runs and 100% of three hundred are different claims.
   */
  command_labelled: number;
  command_matched: number;
  command_accuracy: number | null;
}

/** One model's record under one prompt configuration. */
export interface ConfigurationModelResult {
  litellm_model: string;
  executions: number;
  passed: number;
  pass_rate: number;
  command_labelled: number;
  command_matched: number;
  command_accuracy: number | null;
  mean_latency_ms: number | null;
  last_run_at: string | null;
}

/**
 * A distinct combination of the three frozen prompt blocks.
 *
 * Deduplicated at write time: three runs under two setups leave two rows, and
 * returning to an earlier setup reuses its row.
 */
export interface PromptConfiguration {
  id: string;
  label: string;
  frozen_context_sha256: string;
  system_prompt_version: string | null;
  technical_context_version: string | null;
  emg_context_version: string | null;
  first_used_at: string;
  last_used_at: string;
  executions: number;
  /** Per model, because a configuration is only comparable within one. */
  by_model: ConfigurationModelResult[];
}

/** One command that reached the simulator, the prosthesis, or both. */
export interface MovementLogEntry {
  id: string;
  created_at: string;
  serial_command: string;
  handedness: Handedness;
  actuator_positions: Record<string, number>;
  duration_ms: number | null;
  /** What produced it: a model run, a manual test, or a replay. */
  source: 'execution' | 'manual' | 'replay';
  execution_id: string | null;
  triggered_by_email: string | null;
  /** Two independent destinations: either can arrive while the other does not. */
  sent_to_simulator: boolean;
  sent_to_prosthesis: boolean;
  transport: 'serial' | 'ble' | null;
  delivery_error: string | null;
  notes: string | null;
}

export interface ManualCommandResult {
  id: string;
  serial_command: string;
  normalised_serial: string | null;
  actuator_positions: Record<string, number>;
  duration_ms: number | null;
  /** Zero means nothing is watching — different from a rejected command. */
  simulator_clients: number;
  warnings: string[];
}

export interface LabPreset {
  id: string;
  name: string;
  description?: string | null;
  sampling_configuration_id: string;
  system_prompt_version_id: string;
  technical_context_version_id: string;
  dynamic_prompt_template_id: string;
  handedness: Handedness;
  limit_profile: LimitProfileId;
  merge_context_into_system: boolean;
  is_favorite: boolean;
  use_count: number;
  last_used_at: string | null;
  created_at: string;
}

export interface LmStudioProbe {
  reachable: boolean;
  api_base: string;
  error: string | null;
  models: { id: string; object?: string; owned_by?: string }[];
}
