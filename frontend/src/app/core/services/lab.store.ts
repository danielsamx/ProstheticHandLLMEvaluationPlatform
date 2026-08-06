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
  computeFeatures,
  toWindowPayload,
} from '../models/emg.model';
import { HandSpec, Handedness, LimitProfileId, MovementFrame } from '../models/hand.model';
import {
  DynamicContent,
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
  readonly emgContexts = signal<PromptVersion[]>([]);
  readonly dynamicTemplates = signal<PromptVersion[]>([]);
  readonly lmStudio = signal<LmStudioProbe | null>(null);

  // ── Current selection ─────────────────────────────────────────────────────
  readonly selectedProviderId = signal<string | null>(null);
  readonly selectedModelId = signal<string | null>(null);
  readonly selectedConfigurationId = signal<string | null>(null);
  readonly selectedSystemPromptId = signal<string | null>(null);
  readonly selectedContextId = signal<string | null>(null);
  readonly selectedEmgContextId = signal<string | null>(null);
  readonly selectedTemplateId = signal<string | null>(null);
  //
  // Pinned rather than exposed. Each was a control with no decision behind it,
  // and each was a way for two runs to become quietly incomparable. They stay
  // as signals so the API contract and the simulator are unchanged.
  //
  readonly handedness = signal<Handedness>('right');
  readonly limitProfile = signal<LimitProfileId>('TABLE_5_V3');
  readonly repetitions = signal(1);
  readonly subjectRef = signal<string>('');

  // ── What the model is shown, and what it is scored against ───────────────

  /**
   * Which rendering of the EMG goes into the dynamic block.
   *
   * A real experimental variable rather than a display option: "can a model
   * read raw EMG?" and "can a model act on extracted features?" are different
   * questions, and the second is much the easier one because the signal
   * processing has already been done for it.
   */
  readonly dynamicContent = signal<DynamicContent>('matrix');

  /**
   * Cap on the matrix rows sent; null means the whole window.
   *
   * Null by default. The old fixed cap of 32 meant an imported 404-row
   * recording reached the model as an eighth of itself while the panel
   * reported the full count.
   */
  readonly matrixMaxRows = signal<number | null>(null);

  /**
   * The command a domain expert says this window should produce.
   *
   * Never enters a prompt — it is the answer key. It is stored on the
   * execution and compared against what the model returned, which is what
   * turns a run from a demonstration into a measurement.
   */
  readonly expectedCommand = signal<string>('');

  // ── Decoding parameters (bound to the left panel) ─────────────────────────
  readonly temperature = signal(0);
  readonly topP = signal(1);
  readonly topK = signal<number | null>(null);
  readonly maxTokens = signal(1024);
  readonly seed = signal<number | null>(42);
  readonly frequencyPenalty = signal(0);
  readonly presencePenalty = signal(0);
  readonly responseFormat = signal<'text' | 'json_object' | 'json_schema'>('json_object');
  readonly invocationMode = signal<'structured_output' | 'tool_calling'>('tool_calling');

  /**
   * Suppress the model's thinking channel. On by default.
   *
   * The setting that most changes the answer on this task. A reasoning model
   * splits its output — working-out to a reasoning channel, answer to
   * `content` — and given a hard classification with a small token budget it can
   * spend the whole budget deliberating and return nothing usable. The same
   * model, same prompt, thinking off, returned a pose; thinking on, it returned
   * `no_action` with an empty command list.
   *
   * There is nothing to deliberate about anyway: read eight numbers, name a
   * gesture.
   */
  readonly disableReasoning = signal(true);

  // ── Prompt editing ────────────────────────────────────────────────────────
  readonly systemPromptDraft = signal<string>('');
  readonly technicalContextDraft = signal<string>('');
  readonly emgContextDraft = signal<string>('');
  readonly dynamicTemplateDraft = signal<string>('');
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
    const all = this.models();
    const scoped = providerId ? all.filter((m) => m.provider_id === providerId) : all;
    const list = scoped.length ? scoped : all;

    // Runnable models first. Availability is only known for local runtimes;
    // `undefined`/`null` means "not applicable", not "unavailable".
    return [...list].sort((a, b) => {
      const rank = (m: LlmModel) => (m.is_available === false ? 1 : 0);
      return rank(a) - rank(b) || a.display_name.localeCompare(b.display_name);
    });
  });

  /** Models that can be run right now. */
  readonly runnableModels = computed(
    () => this.modelsForProvider().filter((m) => m.is_available !== false),
  );

  readonly syncingCatalogue = signal(false);

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

  /**
   * Flexor share of flexor + extensor activity.
   *
   * The decisive quantity now that the matrix is raw. It is dimensionless, so
   * it survives a change of gain, electrode placement or subject — none of
   * which an absolute amplitude threshold survives.
   */
  readonly flexorRatio = computed(() => {
    const flexor = this.flexorActivation();
    const extensor = this.extensorActivation();
    const total = flexor + extensor;
    return total ? flexor / total : 0.5;
  });

  /**
   * The window's own noise floor: the quietest channel's RMS, with headroom.
   *
   * Rest has to be defined by contrast rather than by a fixed number, because
   * "quiet" in converter counts depends entirely on the front end.
   */
  readonly restFloor = computed(() => {
    const values = this.features().map((f) => f.rms).filter((v) => v > 0);
    if (!values.length) return Infinity;
    return Math.min(...values) * 2.5;
  });

  readonly matrixValid = computed(() => {
    const rows = this.matrix();
    return rows.length >= 4 && rows.every((row) => row.length === EMG_CHANNEL_COUNT);
  });

  readonly canRun = computed(() => this.blockingReason() === null);

  /**
   * Why Run Evaluation is unavailable, or `null` when it is.
   *
   * A disabled button with no explanation is the worst state this panel can be
   * in: every prerequisite is satisfied somewhere else on screen, and nothing
   * points at the one that is missing.
   */
  readonly blockingReason = computed<string | null>(() => {
    if (this.running()) return 'A run is already in progress.';
    if (!this.apiReachable()) return 'The backend is not reachable.';

    if (!this.models().length) {
      return 'No model in the catalogue. Start LM Studio, load a model, then press Refresh.';
    }
    if (!this.selectedModelId()) return 'Select a model.';

    if (!this.configurations().length) {
      return 'No sampling configuration exists yet. Press Refresh to create a '
           + 'baseline for the loaded models.';
    }
    if (!this.selectedConfigurationId()) {
      return 'Select a saved configuration, or press the bookmark button to save '
           + 'the current parameters.';
    }

    const rows = this.matrix();
    if (rows.length < 4) return 'Load an EMG matrix — import a CSV or generate a synthetic window.';
    if (!rows.every((row) => row.length === EMG_CHANNEL_COUNT)) {
      return `Every row must have exactly ${EMG_CHANNEL_COUNT} columns.`;
    }
    if (rows.every((row) => row.every((value) => value === 0))) {
      return 'The matrix is all zeros. Load a recording or a synthetic window.';
    }

    return null;
  });

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
    const health = await this.api.ping();
    this.apiReachable.set(health.reachable);

    // A backend that is up but migrating-behind will serve reference data and
    // then fail on the first write. Say so before the user hits Run Evaluation.
    if (health.reachable && health.schema && health.schema.ok === false) {
      this.error.set(
        `The backend is running but its database schema is out of date. ` +
        `${health.schema.detail ?? ''} Run: docker compose down && docker compose up --build`,
      );
    }

    if (!this.apiReachable()) {
      this.error.set(
        `Cannot reach the backend at ${environment.apiBase}. ` +
        'Check that the API container is running (docker compose ps) and that ' +
        'nothing else holds the published port 8081.',
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
      firstValueFrom(this.api.listEmgContexts()),
      firstValueFrom(this.api.listDynamicTemplates()),
    ]);

    const labels = [
      'hand specification', 'EMG format', 'providers', 'models',
      'configurations', 'system prompts', 'technical contexts',
      'EMG contexts', 'dynamic templates',
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
    const emgContexts = value<PromptVersion[]>(7, []);
    const templates = value<PromptVersion[]>(8, []);

    if (spec) this.handSpec.set(spec);
    if (format) this.matrixFormat.set(format);
    this.providers.set(providers);
    this.models.set(models);
    this.configurations.set(configs);
    this.systemPrompts.set(systems);
    this.technicalContexts.set(contexts);
    this.emgContexts.set(emgContexts);
    this.dynamicTemplates.set(templates);

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
    const activeEmg = emgContexts.find((p) => p.is_active) ?? emgContexts[0];
    if (activeEmg) {
      this.selectedEmgContextId.set(activeEmg.id);
      this.emgContextDraft.set(activeEmg.content);
    }
    const activeTemplate = templates.find((p) => p.is_active) ?? templates[0];
    if (activeTemplate) {
      this.selectedTemplateId.set(activeTemplate.id);
      this.dynamicTemplateDraft.set(activeTemplate.content);
    }

    const firstConfig = configs[0];
    if (firstConfig?.id) this.applyConfiguration(firstConfig);
    this.ensureSelectableConfiguration();

    if (failed.length) {
      this.error.set(`Could not load: ${failed.join('; ')}.`);
    }

    void this.syncCatalogueWithRuntime();
    void this.refreshHistory();
    this.bridge.connect();
  }

  /**
   * Reconcile the catalogue with what LM Studio actually has loaded.
   *
   * The dropdown offering a model the researcher never downloaded is worse than
   * offering nothing: it fails at inference time with a provider error that
   * looks like a connectivity problem. Importing on boot keeps the list honest
   * without a manual step.
   */
  private async syncCatalogueWithRuntime(): Promise<void> {
    await this.probeLmStudio();
    const probe = this.lmStudio();
    if (!probe?.reachable || !probe.models.length) return;

    const known = new Set(this.models().map((m) => m.model_key));
    const missing = probe.models.filter((m) => !known.has(m.id));
    if (!missing.length) {
      // Still refresh: availability flags may have changed even if the set has not.
      this.models.set(await firstValueFrom(this.api.listModels()));
      this.ensureSelectableModel();
      return;
    }

    await this.syncLmStudioModels();
  }

  async probeLmStudio(): Promise<void> {
    try {
      this.lmStudio.set(await firstValueFrom(this.api.probeLmStudio()));
    } catch {
      this.lmStudio.set(null);
    }
  }

  async syncLmStudioModels(): Promise<void> {
    this.syncingCatalogue.set(true);
    try {
      await firstValueFrom(this.api.syncLmStudio());
      this.models.set(await firstValueFrom(this.api.listModels()));
      await this.probeLmStudio();
      this.configurations.set(await firstValueFrom(this.api.listConfigurations()));
      this.ensureSelectableModel();
      this.ensureSelectableConfiguration();
    } catch (err) {
      this.error.set(this.describe(err));
    } finally {
      this.syncingCatalogue.set(false);
    }
  }

  /**
   * Keep the selection on something that can actually run.
   *
   * A model can disappear between sessions — unloaded in LM Studio, or swapped
   * for another build. Leaving the select pointing at it shows an empty control
   * with no explanation, and Run Evaluation then fails at the provider.
   */
  /**
   * Keep a configuration selected for the chosen model.
   *
   * Configurations are per-model, so switching models can leave the selection
   * pointing at one that belongs to a different model — which reads as "nothing
   * selected" and disables the run.
   */
  private ensureSelectableConfiguration(): void {
    const modelId = this.selectedModelId();
    const configs = this.configurations();
    if (!configs.length) return;

    const current = configs.find((c) => c.id === this.selectedConfigurationId());
    if (current && (!modelId || current.model_id === modelId)) return;

    const match = modelId ? configs.find((c) => c.model_id === modelId) : undefined;
    const chosen = match ?? configs[0];
    if (chosen?.id) this.applyConfiguration(chosen);
  }

  private ensureSelectableModel(): void {
    const runnable = this.runnableModels();
    if (!runnable.length) return;
    if (runnable.some((m) => m.id === this.selectedModelId())) return;
    this.selectedModelId.set(runnable[0].id);
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
    // `?? true` because rows written before this setting existed have no value,
    // and the safe reading of "unspecified" is the one that produces a usable
    // answer: reasoning suppressed.
    this.disableReasoning.set(config.disable_reasoning ?? true);
  }

  private draftConfiguration(
    name: string,
    options: { description?: string; isFavorite?: boolean } = {},
  ): SamplingConfiguration {
    return {
      name,
      description: options.description ?? null,
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
      disable_reasoning: this.disableReasoning(),
      extra_params: {},
      is_favorite: options.isFavorite ?? false,
    };
  }

  /** Persist the current knob positions so the exact condition can be replayed. */
  async saveConfiguration(
    name: string,
    options: { description?: string; isFavorite?: boolean } = {},
  ): Promise<void> {
    if (!this.selectedModelId()) {
      this.error.set('Select a model before saving a configuration.');
      return;
    }
    try {
      const saved = await firstValueFrom(
        this.api.createConfiguration(this.draftConfiguration(name, options)),
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

  /**
   * Load a generated window with a known correct answer.
   *
   * No longer reachable from the interface. It was the first control in the
   * source row, which made synthesised signals look like the normal way to
   * load data — and a run against synthesised EMG is a test of this platform,
   * not evidence about a model.
   *
   * Kept because that test is worth being able to run: call it from the
   * console, or hit /emg/synthetic directly, when checking that the pipeline
   * itself still resolves a known gesture correctly.
   */
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
        ground_truth_gesture: this.groundTruth(),
      }));
      this.matrix.set(result.window.samples);
      this.emgMode.set('manual');
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
  /**
   * Change what the dynamic block carries, and show the result immediately.
   *
   * The mode is a discrete choice with no intermediate states, so there is
   * nothing to stage and nothing to confirm — deferring it behind a button
   * would only create a window in which the panel and the prompt disagree.
   */
  async setDynamicContent(mode: DynamicContent): Promise<void> {
    if (this.dynamicContent() === mode) return;
    this.dynamicContent.set(mode);
    await this.refreshPreview();
  }

  /**
   * Commit the matrix row cap and re-render.
   *
   * Separate from the mode because a number field has intermediate states: it
   * fires on every keystroke, so "128" passes through 1 and 12 on the way. The
   * component holds a draft and calls this on blur, Enter or Apply.
   */
  async setMatrixMaxRows(rows: number | null): Promise<void> {
    this.matrixMaxRows.set(rows);
    await this.refreshPreview();
  }

  async refreshPreview(): Promise<void> {
    this.previewLoading.set(true);
    try {
      const preview = await firstValueFrom(this.api.previewPrompt({
        window: toWindowPayload(this.currentWindow()),
        handedness: this.handedness(),
        system_prompt_version_id: this.selectedSystemPromptId(),
        technical_context_version_id: this.selectedContextId(),
        emg_context_version_id: this.selectedEmgContextId(),
        dynamic_prompt_template_id: this.selectedTemplateId(),
        model_id: this.selectedModelId(),
        system_prompt_override: this.dirtySystemPrompt() ? this.systemPromptDraft() : null,
        technical_context_override: this.dirtyContext() ? this.technicalContextDraft() : null,
        emg_context_override: this.dirtyEmgContext() ? this.emgContextDraft() : null,
        dynamic_template_override: this.dirtyTemplate() ? this.dynamicTemplateDraft() : null,
        dynamic_content: this.dynamicContent(),
        matrix_max_rows: this.matrixMaxRows(),
        expected_serial_command: this.expectedCommand().trim() || null,
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

  dirtyEmgContext(): boolean {
    const active = this.emgContexts().find((p) => p.id === this.selectedEmgContextId());
    return !!active && active.content !== this.emgContextDraft();
  }

  dirtyTemplate(): boolean {
    const active = this.dynamicTemplates().find((p) => p.id === this.selectedTemplateId());
    return !!active && active.content !== this.dynamicTemplateDraft();
  }

  async saveTemplateVersion(name: string, version: string): Promise<void> {
    const saved = await firstValueFrom(this.api.createDynamicTemplate({
      name, version, content: this.dynamicTemplateDraft(), activate: true,
    }));
    this.dynamicTemplates.update(
      (list) => [saved, ...list.map((p) => ({ ...p, is_active: false }))],
    );
    this.selectedTemplateId.set(saved.id);
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

  async saveEmgContextVersion(name: string, version: string): Promise<void> {
    const saved = await firstValueFrom(this.api.createEmgContext({
      name, version, content: this.emgContextDraft(), activate: true,
    }));
    this.emgContexts.update(
      (list) => [saved, ...list.map((p) => ({ ...p, is_active: false }))],
    );
    this.selectedEmgContextId.set(saved.id);
  }

  async regenerateEmgContextFromDomain(): Promise<void> {
    const generated = await firstValueFrom(this.api.getGeneratedEmgContext());
    this.emgContextDraft.set(generated.content);
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
        invocation_mode: this.invocationMode(),
        window: toWindowPayload(this.currentWindow()),
        handedness: this.handedness(),
        system_prompt_version_id: this.selectedSystemPromptId(),
        technical_context_version_id: this.selectedContextId(),
        emg_context_version_id: this.selectedEmgContextId(),
        dynamic_prompt_template_id: this.selectedTemplateId(),
        system_prompt_override: this.dirtySystemPrompt() ? this.systemPromptDraft() : null,
        technical_context_override: this.dirtyContext() ? this.technicalContextDraft() : null,
        emg_context_override: this.dirtyEmgContext() ? this.emgContextDraft() : null,
        dynamic_template_override: this.dirtyTemplate() ? this.dynamicTemplateDraft() : null,
        dynamic_content: this.dynamicContent(),
        matrix_max_rows: this.matrixMaxRows(),
        expected_serial_command: this.expectedCommand().trim() || null,
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
      const body = err.error as
        { detail?: unknown; hint?: string; request_id?: string } | string | null;

      if (typeof body === 'string' && body.trim()) return `${err.status} ${body}`;

      if (typeof body === 'object' && body) {
        const parts: string[] = [`${err.status}`];
        if (typeof body.detail === 'string') parts.push(body.detail);
        else if (Array.isArray(body.detail)) {
          parts.push(body.detail.map((d) => JSON.stringify(d)).join('; '));
        } else parts.push(err.statusText || 'request failed');
        // The backend attaches a hint when it knows the likely cause — most
        // often a pending migration after an upgrade.
        if (body.hint) parts.push(`— ${body.hint}`);
        if (body.request_id) parts.push(`(request ${body.request_id})`);
        return parts.join(' ');
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
