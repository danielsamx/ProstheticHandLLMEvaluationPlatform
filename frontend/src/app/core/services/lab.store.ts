import { HttpErrorResponse } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { environment } from '@env/environment';

import { ApiService, RunExecutionPayload } from '../api/api.service';
import {
  EMG_CHANNEL_COUNT,
  EmgChannelFeatures,
  EmgMatrixFormat,
  EmgSourceMode,
  EmgWindow,
  NormalisationMode,
  computeFeatures,
  toWindowPayload,
} from '../models/emg.model';
import { HandSpec, Handedness, LimitProfileId, MovementFrame } from '../models/hand.model';
import {
  Execution,
  LlmModel,
  LmStudioProbe,
  PromptPreview,
  PromptVersion,
  Provider,
  SamplingConfiguration,
} from '../models/llm.model';
import { SimulatorBridgeService } from './simulator-bridge.service';

const CHANNEL_LABELS = Array.from({ length: EMG_CHANNEL_COUNT }, (_, i) => `CH${i + 1}`);
const DEFAULT_ROWS = 200;

function blankMatrix(rows = DEFAULT_ROWS): number[][] {
  return Array.from({ length: rows }, () => new Array<number>(EMG_CHANNEL_COUNT).fill(0));
}

/**
 * Central signal store for the evaluation laboratory.
 *
 * Deliberately holds no conversation state: an execution is a pure function of
 * (configuration, frozen prompts, EMG window). Nothing carries over between
 * runs except the reusable presets the researcher chose to save.
 */
@Injectable({ providedIn: 'root' })
export class LabStore {
  private readonly api = inject(ApiService);
  private readonly bridge = inject(SimulatorBridgeService);

  // ── Reference data ────────────────────────────────────────────────────────
  readonly handSpec = signal<HandSpec | null>(null);
  readonly providers = signal<Provider[]>([]);
  readonly models = signal<LlmModel[]>([]);
  readonly configurations = signal<SamplingConfiguration[]>([]);
  readonly systemPrompts = signal<PromptVersion[]>([]);
  readonly technicalContexts = signal<PromptVersion[]>([]);
  readonly dynamicTemplates = signal<PromptVersion[]>([]);
  readonly syntheticGestures = signal<string[]>([]);
  readonly lmStudio = signal<LmStudioProbe | null>(null);

  // ── Current selection ─────────────────────────────────────────────────────
  readonly selectedProviderId = signal<string | null>(null);
  readonly selectedModelId = signal<string | null>(null);
  readonly selectedConfigurationId = signal<string | null>(null);
  readonly selectedSystemPromptId = signal<string | null>(null);
  readonly selectedContextId = signal<string | null>(null);
  readonly selectedTemplateId = signal<string | null>(null);
  readonly handedness = signal<Handedness>('right');
  readonly limitProfile = signal<LimitProfileId>('TABLE_5_V3');
  readonly repetitions = signal(1);
  readonly subjectRef = signal<string>('');

  // ── Decoding parameters (bound to the left panel) ─────────────────────────
  readonly temperature = signal(0);
  readonly topP = signal(1);
  readonly topK = signal<number | null>(null);
  readonly maxTokens = signal(1024);
  readonly seed = signal<number | null>(42);
  readonly frequencyPenalty = signal(0);
  readonly presencePenalty = signal(0);
  readonly responseFormat = signal<'text' | 'json_object' | 'json_schema'>('json_object');

  // ── Prompt editing ────────────────────────────────────────────────────────
  readonly systemPromptDraft = signal<string>('');
  readonly technicalContextDraft = signal<string>('');
  readonly promptPreview = signal<PromptPreview | null>(null);
  readonly previewLoading = signal(false);

  // ── EMG stimulus: an N x 8 matrix of normalised raw samples ───────────────
  readonly emgMode = signal<EmgSourceMode>('manual');
  readonly liveMode = signal(false);
  readonly matrix = signal<number[][]>(blankMatrix());
  readonly sampleRateHz = signal(1000);
  readonly groundTruth = signal<string | null>(null);
  readonly matrixFormat = signal<EmgMatrixFormat | null>(null);
  readonly matrixError = signal<string | null>(null);
  readonly matrixWarnings = signal<string[]>([]);
  /** Divisor applied to the last imported matrix, and whether it was declared. */
  readonly normalisation = signal<NormalisationMode>('full_scale');
  readonly fullScale = signal<number | null>(512);
  readonly appliedDivisor = signal<number | null>(null);
  readonly inferredFullScale = signal(false);
  readonly channelLabels = CHANNEL_LABELS;

  // ── Run state ─────────────────────────────────────────────────────────────
  readonly apiReachable = signal(true);
  readonly running = signal(false);
  readonly lastResult = signal<Execution | null>(null);
  readonly history = signal<Execution[]>([]);
  readonly determinism = signal<{ distinct_responses: number; determinism_rate: number | null } | null>(null);
  readonly error = signal<string | null>(null);

  // ── Derived ───────────────────────────────────────────────────────────────
  readonly selectedModel = computed(() =>
    this.models().find((m) => m.id === this.selectedModelId()) ?? null,
  );

  /**
   * Models for the selected provider.
   *
   * Falls back to the full list when the filter would come back empty, so a
   * stale or mismatched provider id shows every model rather than an empty
   * dropdown with no explanation.
   */
  readonly modelsForProvider = computed(() => {
    const providerId = this.selectedProviderId();
    if (!providerId) return this.models();
    const filtered = this.models().filter((m) => m.provider_id === providerId);
    return filtered.length ? filtered : this.models();
  });

  readonly currentWindow = computed<EmgWindow>(() => ({
    samples: this.matrix(),
    source_mode: this.emgMode(),
    sample_rate_hz: this.sampleRateHz(),
    ground_truth_gesture: this.groundTruth(),
  }));

  readonly sampleCount = computed(() => this.matrix().length);

  readonly windowMs = computed(
    () => (this.sampleCount() / this.sampleRateHz()) * 1000,
  );

  /** Descriptors recomputed locally so the panel stays responsive while typing. */
  readonly features = computed<EmgChannelFeatures[]>(
    () => computeFeatures(this.matrix(), CHANNEL_LABELS),
  );

  readonly meanRms = computed(() => {
    const list = this.features();
    return list.length ? list.reduce((sum, f) => sum + f.rms, 0) / list.length : 0;
  });

  readonly flexorActivation = computed(() => {
    const list = this.features().slice(0, 4);
    return list.reduce((sum, f) => sum + f.rms, 0) / 4;
  });

  readonly extensorActivation = computed(() => {
    const list = this.features().slice(4, 7);
    return list.reduce((sum, f) => sum + f.rms, 0) / 3;
  });

  /** Below this the correct answer is "do not move". */
  readonly belowActivationThreshold = computed(() => this.meanRms() < 0.1);

  readonly coContraction = computed(
    () => this.flexorActivation() > 0.2 && this.extensorActivation() > 0.2,
  );

  readonly matrixValid = computed(() => {
    const rows = this.matrix();
    return rows.length >= 4 && rows.every((row) => row.length === EMG_CHANNEL_COUNT);
  });

  readonly canRun = computed(
    () => !this.running() && !!this.selectedConfigurationId() && this.matrixValid(),
  );

  readonly successRate = computed(() => {
    const runs = this.history();
    if (!runs.length) return null;
    return runs.filter((e) => e.validation_passed).length / runs.length;
  });

  // ── Bootstrap ─────────────────────────────────────────────────────────────

  /**
   * Load the reference data the laboratory needs.
   *
   * Each endpoint is settled independently. `Promise.all` was wrong here: one
   * failing request rejected the whole batch and left every list empty, so a
   * single new or unreachable endpoint silently blanked the model dropdown, the
   * providers and all three prompt blocks at once. Now a failure costs only its
   * own section, and the message names the endpoint that broke.
   */
  async bootstrap(): Promise<void> {
    // One reachability check up front. Without it, a stopped backend produces
    // nine identical failures and buries the single fact that matters.
    this.apiReachable.set(await this.api.ping());
    if (!this.apiReachable()) {
      this.error.set(
        `Cannot reach the backend at ${environment.apiBase}. ` +
        'Check that the API container is running (docker compose ps) and that ' +
        'nothing else holds port 8000.',
      );
      return;
    }

    const results = await Promise.allSettled([
      firstValueFrom(this.api.getHandSpec()),
      firstValueFrom(this.api.emgFormat()),
      firstValueFrom(this.api.listProviders()),
      firstValueFrom(this.api.listModels()),
      firstValueFrom(this.api.listConfigurations()),
      firstValueFrom(this.api.listSystemPrompts()),
      firstValueFrom(this.api.listTechnicalContexts()),
      firstValueFrom(this.api.listDynamicTemplates()),
      firstValueFrom(this.api.syntheticGestures()),
    ]);

    const labels = [
      'hand specification', 'EMG format', 'providers', 'models',
      'configurations', 'system prompts', 'technical contexts',
      'dynamic templates', 'synthetic gestures',
    ];

    const failed: string[] = [];
    const value = <T,>(index: number, fallback: T): T => {
      const result = results[index];
      if (result.status === 'fulfilled') return result.value as T;
      failed.push(`${labels[index]} (${this.describe(result.reason)})`);
      return fallback;
    };

    const spec = value(0, null as HandSpec | null);
    const format = value(1, null as EmgMatrixFormat | null);
    const providers = value<Provider[]>(2, []);
    const models = value<LlmModel[]>(3, []);
    const configs = value<SamplingConfiguration[]>(4, []);
    const systems = value<PromptVersion[]>(5, []);
    const contexts = value<PromptVersion[]>(6, []);
    const templates = value<PromptVersion[]>(7, []);
    const gestures = value<string[]>(8, []);

    if (spec) this.handSpec.set(spec);
    if (format) this.matrixFormat.set(format);
    this.providers.set(providers);
    this.models.set(models);
    this.configurations.set(configs);
    this.systemPrompts.set(systems);
    this.technicalContexts.set(contexts);
    this.dynamicTemplates.set(templates);
    this.syntheticGestures.set(gestures);

    // Prefer the local LM Studio provider: it is the primary runtime here.
    const local = providers.find((p) => p.slug === 'lm_studio') ?? providers[0];
    if (local) this.selectedProviderId.set(local.id);

    const activeSystem = systems.find((p) => p.is_active) ?? systems[0];
    if (activeSystem) {
      this.selectedSystemPromptId.set(activeSystem.id);
      this.systemPromptDraft.set(activeSystem.content);
    }
    const activeContext = contexts.find((p) => p.is_active) ?? contexts[0];
    if (activeContext) {
      this.selectedContextId.set(activeContext.id);
      this.technicalContextDraft.set(activeContext.content);
      if (activeContext.limit_profile) this.limitProfile.set(activeContext.limit_profile);
    }
    const activeTemplate = templates.find((p) => p.is_active) ?? templates[0];
    if (activeTemplate) this.selectedTemplateId.set(activeTemplate.id);

    const firstConfig = configs[0];
    if (firstConfig?.id) this.applyConfiguration(firstConfig);

    if (failed.length) {
      this.error.set(`Could not load: ${failed.join('; ')}.`);
    }

    void this.probeLmStudio();
    void this.refreshHistory();
    this.bridge.connect();
  }

  async probeLmStudio(): Promise<void> {
    try {
      this.lmStudio.set(await firstValueFrom(this.api.probeLmStudio()));
    } catch {
      this.lmStudio.set(null);
    }
  }

  async syncLmStudioModels(): Promise<void> {
    try {
      await firstValueFrom(this.api.syncLmStudio());
      this.models.set(await firstValueFrom(this.api.listModels()));
      await this.probeLmStudio();
    } catch (err) {
      this.error.set(this.describe(err));
    }
  }

  // ── Configuration handling ────────────────────────────────────────────────
  applyConfiguration(config: SamplingConfiguration): void {
    if (config.id) this.selectedConfigurationId.set(config.id);
    this.selectedModelId.set(config.model_id);
    const model = this.models().find((m) => m.id === config.model_id);
    if (model) this.selectedProviderId.set(model.provider_id);

    this.temperature.set(config.temperature);
    this.topP.set(config.top_p);
    this.topK.set(config.top_k);
    this.maxTokens.set(config.max_tokens);
    this.seed.set(config.seed);
    this.frequencyPenalty.set(config.frequency_penalty);
    this.presencePenalty.set(config.presence_penalty);
    this.responseFormat.set(config.response_format);
  }

  private draftConfiguration(name: string): SamplingConfiguration {
    return {
      name,
      model_id: this.selectedModelId()!,
      temperature: this.temperature(),
      top_p: this.topP(),
      top_k: this.topK(),
      max_tokens: this.maxTokens(),
      seed: this.seed(),
      frequency_penalty: this.frequencyPenalty(),
      presence_penalty: this.presencePenalty(),
      stop_sequences: [],
      response_format: this.responseFormat(),
      extra_params: {},
      is_favorite: false,
    };
  }

  /** Persist the current knob positions so the exact condition can be replayed. */
  async saveConfiguration(name: string): Promise<void> {
    if (!this.selectedModelId()) {
      this.error.set('Select a model before saving a configuration.');
      return;
    }
    try {
      const saved = await firstValueFrom(
        this.api.createConfiguration(this.draftConfiguration(name)),
      );
      this.configurations.update((list) => [saved, ...list]);
      if (saved.id) this.selectedConfigurationId.set(saved.id);
    } catch (err) {
      this.error.set(this.describe(err));
    }
  }

  /** Push edited knobs onto the selected configuration before running. */
  private async syncSelectedConfiguration(): Promise<void> {
    const id = this.selectedConfigurationId();
    const current = this.configurations().find((c) => c.id === id);
    if (!id || !current) return;
    const updated = { ...current, ...this.draftConfiguration(current.name) };
    const saved = await firstValueFrom(this.api.updateConfiguration(id, updated));
    this.configurations.update((list) => list.map((c) => (c.id === id ? saved : c)));
  }

  // ── EMG matrix editing ────────────────────────────────────────────────────

  setMatrix(samples: number[][], mode: EmgSourceMode = 'manual'): void {
    this.matrix.set(samples);
    this.emgMode.set(mode);
    this.matrixError.set(null);
  }

  /** Edit a single cell. Used by the inline matrix grid. */
  setSample(row: number, column: number, value: number): void {
    const clamped = Math.max(-1, Math.min(1, value));
    this.matrix.update((rows) =>
      rows.map((r, i) => (i === row ? r.map((v, c) => (c === column ? clamped : v)) : r)),
    );
  }

  /** Scale one electrode's whole column - the practical way to shape a window
   *  by hand without typing hundreds of samples. */
  scaleChannel(column: number, factor: number): void {
    this.matrix.update((rows) =>
      rows.map((r) => r.map((v, c) => (c === column ? Math.max(-1, Math.min(1, v * factor)) : v))),
    );
  }

  /** Overwrite one electrode with band-limited noise at a target RMS. */
  fillChannel(column: number, targetRms: number, seed = Date.now()): void {
    const rows = this.matrix().length;
    let state = seed >>> 0;
    const random = (): number => {
      // xorshift32: deterministic given the seed, so a hand-built window is
      // reproducible from the seed alone.
      state ^= state << 13; state >>>= 0;
      state ^= state >> 17;
      state ^= state << 5; state >>>= 0;
      return state / 4294967296 - 0.5;
    };

    const raw: number[] = [];
    let low = 0;
    for (let i = 0; i < rows + 1; i++) {
      low = 0.6 * low + 0.4 * random();
      raw.push(low);
    }
    const band = raw.slice(1).map((v, i) => v - raw[i]);
    const rms = Math.sqrt(band.reduce((s, v) => s + v * v, 0) / (band.length || 1)) || 1;
    const gain = targetRms / rms;

    this.matrix.update((matrix) =>
      matrix.map((r, i) =>
        r.map((v, c) => (c === column ? Math.max(-1, Math.min(1, band[i] * gain)) : v)),
      ),
    );
  }

  resizeMatrix(rows: number): void {
    const target = Math.max(4, Math.min(8192, Math.round(rows)));
    this.matrix.update((matrix) => {
      if (matrix.length === target) return matrix;
      if (matrix.length > target) return matrix.slice(0, target);
      const padded = [...matrix];
      while (padded.length < target) {
        padded.push(new Array<number>(EMG_CHANNEL_COUNT).fill(0));
      }
      return padded;
    });
  }

  resetMatrix(): void {
    this.matrix.set(blankMatrix(this.matrix().length || DEFAULT_ROWS));
    this.groundTruth.set(null);
    this.matrixError.set(null);
  }

  async loadSynthetic(gesture: string, seed = 42): Promise<void> {
    try {
      const window = await firstValueFrom(
        this.api.synthesise(gesture, 0.12, this.matrix().length || DEFAULT_ROWS, seed),
      );
      this.matrix.set(window.samples);
      this.sampleRateHz.set(window.sample_rate_hz);
      this.groundTruth.set(window.ground_truth_gesture ?? gesture);
      this.emgMode.set('synthetic');
      this.matrixError.set(null);
    } catch (err) {
      this.error.set(this.describe(err));
    }
  }

  /**
   * Parse pasted CSV / TSV / JSON server-side.
   *
   * Parsing on the backend rather than in the browser keeps one implementation
   * of the shape rules - including the transposed-matrix diagnostic, which is
   * the mistake most likely to silently corrupt an experiment.
   */
  async loadMatrixFromText(text: string): Promise<boolean> {
    this.matrixError.set(null);
    this.matrixWarnings.set([]);
    try {
      const result = await firstValueFrom(this.api.parseMatrix({
        text,
        sample_rate_hz: this.sampleRateHz(),
        normalisation: this.normalisation(),
        full_scale: this.normalisation() === 'full_scale' ? this.fullScale() : null,
        ground_truth_gesture: this.groundTruth(),
      }));
      this.matrix.set(result.window.samples);
      this.emgMode.set('manual');
      this.appliedDivisor.set(result.divisor);
      this.inferredFullScale.set(result.inferred_full_scale);
      this.matrixWarnings.set(result.warnings);
      return true;
    } catch (err) {
      this.matrixError.set(this.describe(err));
      return false;
    }
  }

  matrixAsCsv(precision = 4): string {
    const header = CHANNEL_LABELS.join(',');
    const rows = this.matrix().map((row) => row.map((v) => v.toFixed(precision)).join(','));
    return [header, ...rows].join('\n');
  }

  setLiveMode(enabled: boolean): void {
    this.liveMode.set(enabled);
    this.emgMode.set(enabled ? 'live' : 'manual');
  }

  /** Apply a window that arrived over the live socket. */
  ingestLiveWindow(window: EmgWindow): void {
    this.matrix.set(window.samples);
    this.sampleRateHz.set(window.sample_rate_hz);
  }

  // ── Prompt preview ────────────────────────────────────────────────────────
  async refreshPreview(): Promise<void> {
    this.previewLoading.set(true);
    try {
      const preview = await firstValueFrom(this.api.previewPrompt({
        window: toWindowPayload(this.currentWindow()),
        handedness: this.handedness(),
        system_prompt_version_id: this.selectedSystemPromptId(),
        technical_context_version_id: this.selectedContextId(),
        dynamic_prompt_template_id: this.selectedTemplateId(),
        system_prompt_override: this.dirtySystemPrompt() ? this.systemPromptDraft() : null,
        technical_context_override: this.dirtyContext() ? this.technicalContextDraft() : null,
        limit_profile: this.limitProfile(),
        subject_ref: this.subjectRef() || null,
      }));
      this.promptPreview.set(preview);
    } catch (err) {
      this.error.set(this.describe(err));
    } finally {
      this.previewLoading.set(false);
    }
  }

  dirtySystemPrompt(): boolean {
    const active = this.systemPrompts().find((p) => p.id === this.selectedSystemPromptId());
    return !!active && active.content !== this.systemPromptDraft();
  }

  dirtyContext(): boolean {
    const active = this.technicalContexts().find((p) => p.id === this.selectedContextId());
    return !!active && active.content !== this.technicalContextDraft();
  }

  /** Save an edited block as a NEW version - existing rows are immutable. */
  async saveSystemPromptVersion(name: string, version: string): Promise<void> {
    const saved = await firstValueFrom(this.api.createSystemPrompt({
      name, version, content: this.systemPromptDraft(), activate: true,
    }));
    this.systemPrompts.update((list) => [saved, ...list.map((p) => ({ ...p, is_active: false }))]);
    this.selectedSystemPromptId.set(saved.id);
  }

  async saveContextVersion(name: string, version: string): Promise<void> {
    const saved = await firstValueFrom(this.api.createTechnicalContext({
      name, version, content: this.technicalContextDraft(), activate: true,
      limit_profile: this.limitProfile(), includes_json_schema: true,
    }));
    this.technicalContexts.update((list) => [saved, ...list.map((p) => ({ ...p, is_active: false }))]);
    this.selectedContextId.set(saved.id);
  }

  async regenerateContextFromDomain(): Promise<void> {
    const generated = await firstValueFrom(this.api.getGeneratedContext(this.limitProfile()));
    this.technicalContextDraft.set(generated.content);
  }

  // ── Execution ─────────────────────────────────────────────────────────────
  async runEvaluation(): Promise<void> {
    if (!this.canRun()) return;
    this.running.set(true);
    this.error.set(null);
    this.determinism.set(null);

    try {
      await this.syncSelectedConfiguration();

      const payload: RunExecutionPayload = {
        sampling_configuration_id: this.selectedConfigurationId()!,
        window: toWindowPayload(this.currentWindow()),
        handedness: this.handedness(),
        system_prompt_version_id: this.selectedSystemPromptId(),
        technical_context_version_id: this.selectedContextId(),
        dynamic_prompt_template_id: this.selectedTemplateId(),
        system_prompt_override: this.dirtySystemPrompt() ? this.systemPromptDraft() : null,
        technical_context_override: this.dirtyContext() ? this.technicalContextDraft() : null,
        limit_profile: this.limitProfile(),
        subject_ref: this.subjectRef() || null,
        repetitions: this.repetitions(),
        experiment_type: this.liveMode() ? 'live_stream' : 'single_inference',
      };

      const result = await firstValueFrom(this.api.runExecution(payload));
      const first = result.executions[0] ?? null;
      this.lastResult.set(first);
      this.determinism.set(result.determinism);
      this.history.update((list) => [...result.executions, ...list].slice(0, 100));

      // Only a validated execution carries a movement; anything else leaves the
      // simulator exactly where it was.
      if (first?.movement) {
        this.bridge.emitLocal({ ...first.movement, execution_id: first.id } as MovementFrame);
      }
    } catch (err) {
      this.error.set(this.describe(err));
    } finally {
      this.running.set(false);
    }
  }

  async refreshHistory(): Promise<void> {
    try {
      this.history.set(await firstValueFrom(this.api.listExecutions(50)));
    } catch {
      /* history is best-effort */
    }
  }

  async replay(execution: Execution): Promise<void> {
    if (!execution.movement) return;
    this.lastResult.set(execution);
    this.bridge.emitLocal({ ...execution.movement, execution_id: execution.id } as MovementFrame);
  }

  /**
   * Turn an HTTP failure into something a human can act on.
   *
   * `HttpErrorResponse` does not extend `Error`, so the previous
   * `instanceof Error` branch never matched and every failure fell through to
   * `String(err)` — which is how nine endpoints all reported "[object Object]"
   * and told nobody anything.
   */
  private describe(err: unknown): string {
    if (err instanceof HttpErrorResponse) {
      // Status 0 means the request never reached a server: the backend is
      // down, the port is wrong, or CORS rejected it before any response.
      if (err.status === 0) {
        return `cannot reach ${environment.apiBase} (backend down, or CORS)`;
      }
      const body = err.error as { detail?: unknown } | string | null;
      if (typeof body === 'string' && body.trim()) return `${err.status} ${body}`;
      const detail = typeof body === 'object' && body ? body.detail : undefined;
      if (typeof detail === 'string') return `${err.status} ${detail}`;
      if (Array.isArray(detail)) {
        return `${err.status} ${detail.map((d) => JSON.stringify(d)).join('; ')}`;
      }
      return `${err.status} ${err.statusText || 'request failed'}`;
    }
    if (err instanceof Error) return err.message;
    if (typeof err === 'string') return err;
    try {
      return JSON.stringify(err);
    } catch {
      return String(err);
    }
  }
}
