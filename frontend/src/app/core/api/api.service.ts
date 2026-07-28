import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, firstValueFrom } from 'rxjs';

import { environment } from '@env/environment';
import { EmgMatrixFormat, EmgWindow, MatrixParseResponse } from '../models/emg.model';
import { HandSpec, Handedness, LimitProfileId } from '../models/hand.model';
import {
  DynamicContent,
  Execution,
  ExecutionStats,
  LabPreset,
  LlmModel,
  LmStudioProbe,
  PromptPreview,
  PromptVersion,
  Provider,
  RunExecutionResult,
  SamplingConfiguration,
} from '../models/llm.model';

/** `/health` also reports whether the schema matches the models. */
export interface HealthReport {
  reachable: boolean;
  status?: string;
  version?: string;
  env?: string;
  schema?: { ok: boolean | null; revision: string | null; detail: string | null };
}

export interface RunExecutionPayload {
  sampling_configuration_id: string;
  window: EmgWindow;
  handedness: Handedness;
  system_prompt_version_id?: string | null;
  technical_context_version_id?: string | null;
  emg_context_version_id?: string | null;
  dynamic_prompt_template_id?: string | null;
  system_prompt_override?: string | null;
  technical_context_override?: string | null;
  emg_context_override?: string | null;
  dynamic_template_override?: string | null;
  /** What the dynamic block carries. An experimental variable, not a view. */
  dynamic_content?: DynamicContent;
  /** Cap on printed matrix rows; null sends the whole window. */
  matrix_max_rows?: number | null;
  /** The answer key. Stored and compared, never placed in a prompt. */
  expected_serial_command?: string | null;
  limit_profile?: LimitProfileId | null;
  experiment_id?: string | null;
  experiment_type?: string;
  subject_ref?: string | null;
  subject_notes?: string | null;
  extra_parameters?: Record<string, unknown>;
  merge_context_into_system?: boolean;
  repetitions?: number;
}

/** Thin typed wrapper over the backend. No business logic lives here. */
@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBase;

  /**
   * Liveness probe against the API root.
   *
   * Deliberately not one of the data endpoints: this answers "is anything
   * there at all", which is a different question from "did this query work".
   */
  async ping(): Promise<HealthReport> {
    const root = this.base.replace(/\/api\/v1\/?$/, '');
    try {
      const body = await firstValueFrom(this.http.get<HealthReport>(`${root}/health`));
      return { ...body, reachable: true };
    } catch {
      return { reachable: false };
    }
  }

  // ── Hardware specification ────────────────────────────────────────────────
  getHandSpec(): Observable<HandSpec> {
    return this.http.get<HandSpec>(`${this.base}/hand/spec`);
  }

  getOutputSchema(): Observable<Record<string, unknown>> {
    return this.http.get<Record<string, unknown>>(`${this.base}/hand/output-schema`);
  }

  // ── Providers & models ────────────────────────────────────────────────────
  listProviders(): Observable<Provider[]> {
    return this.http.get<Provider[]>(`${this.base}/providers`);
  }

  listModels(providerId?: string): Observable<LlmModel[]> {
    let params = new HttpParams();
    if (providerId) params = params.set('provider_id', providerId);
    return this.http.get<LlmModel[]>(`${this.base}/providers/models`, { params });
  }

  probeLmStudio(apiBase?: string): Observable<LmStudioProbe> {
    let params = new HttpParams();
    if (apiBase) params = params.set('api_base', apiBase);
    return this.http.get<LmStudioProbe>(`${this.base}/providers/lm-studio/probe`, { params });
  }

  syncLmStudio(apiBase?: string): Observable<{ imported: LlmModel[]; already_known: string[] }> {
    let params = new HttpParams();
    if (apiBase) params = params.set('api_base', apiBase);
    return this.http.post<{ imported: LlmModel[]; already_known: string[] }>(
      `${this.base}/providers/lm-studio/sync`, {}, { params },
    );
  }

  // ── Sampling configurations & presets ─────────────────────────────────────
  listConfigurations(): Observable<SamplingConfiguration[]> {
    return this.http.get<SamplingConfiguration[]>(`${this.base}/configurations`);
  }

  createConfiguration(payload: SamplingConfiguration): Observable<SamplingConfiguration> {
    return this.http.post<SamplingConfiguration>(`${this.base}/configurations`, payload);
  }

  updateConfiguration(id: string, payload: SamplingConfiguration): Observable<SamplingConfiguration> {
    return this.http.put<SamplingConfiguration>(`${this.base}/configurations/${id}`, payload);
  }

  deleteConfiguration(id: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/configurations/${id}`);
  }

  listPresets(): Observable<LabPreset[]> {
    return this.http.get<LabPreset[]>(`${this.base}/presets`);
  }

  // ── Prompt artefacts ──────────────────────────────────────────────────────
  listSystemPrompts(): Observable<PromptVersion[]> {
    return this.http.get<PromptVersion[]>(`${this.base}/prompts/system`);
  }

  createSystemPrompt(body: {
    name: string; version: string; content: string; description?: string; activate: boolean;
  }): Observable<PromptVersion> {
    return this.http.post<PromptVersion>(`${this.base}/prompts/system`, body);
  }

  listTechnicalContexts(): Observable<PromptVersion[]> {
    return this.http.get<PromptVersion[]>(`${this.base}/prompts/technical-context`);
  }

  createTechnicalContext(body: {
    name: string; version: string; content: string; description?: string;
    activate: boolean; limit_profile: LimitProfileId; includes_json_schema: boolean;
  }): Observable<PromptVersion> {
    return this.http.post<PromptVersion>(`${this.base}/prompts/technical-context`, body);
  }

  getGeneratedContext(limitProfile: LimitProfileId): Observable<{
    limit_profile: string; content: string; content_sha256: string; char_count: number;
  }> {
    const params = new HttpParams().set('limit_profile', limitProfile);
    return this.http.get<{
      limit_profile: string; content: string; content_sha256: string; char_count: number;
    }>(`${this.base}/prompts/technical-context/generated`, { params });
  }

  listEmgContexts(): Observable<PromptVersion[]> {
    return this.http.get<PromptVersion[]>(`${this.base}/prompts/emg-context`);
  }

  getGeneratedEmgContext(): Observable<{
    content: string; content_sha256: string; char_count: number;
  }> {
    return this.http.get<{
      content: string; content_sha256: string; char_count: number;
    }>(`${this.base}/prompts/emg-context/generated`);
  }

  createEmgContext(body: {
    name: string; version: string; content: string; description?: string; activate: boolean;
  }): Observable<PromptVersion> {
    return this.http.post<PromptVersion>(`${this.base}/prompts/emg-context`, body);
  }

  listDynamicTemplates(): Observable<PromptVersion[]> {
    return this.http.get<PromptVersion[]>(`${this.base}/prompts/dynamic-templates`);
  }

  createDynamicTemplate(body: {
    name: string; version: string; content: string; description?: string; activate: boolean;
  }): Observable<PromptVersion> {
    return this.http.post<PromptVersion>(`${this.base}/prompts/dynamic-templates`, body);
  }

  previewPrompt(body: Record<string, unknown>): Observable<PromptPreview> {
    return this.http.post<PromptPreview>(`${this.base}/prompts/preview`, body);
  }

  // ── EMG ───────────────────────────────────────────────────────────────────
  emgFormat(): Observable<EmgMatrixFormat> {
    return this.http.get<EmgMatrixFormat>(`${this.base}/emg/format`);
  }

  blankWindow(samples = 64): Observable<EmgWindow> {
    const params = new HttpParams().set('samples', samples);
    return this.http.get<EmgWindow>(`${this.base}/emg/blank`, { params });
  }

  syntheticGestures(): Observable<string[]> {
    return this.http.get<string[]>(`${this.base}/emg/synthetic/gestures`);
  }

  synthesise(gesture: string, noise = 0.12, samples = 200, seed?: number): Observable<EmgWindow> {
    let params = new HttpParams()
      .set('gesture', gesture)
      .set('noise', noise)
      .set('samples', samples);
    if (seed !== undefined) params = params.set('seed', seed);
    return this.http.get<EmgWindow>(`${this.base}/emg/synthetic`, { params });
  }

  /** Parse a pasted CSV / TSV / JSON matrix server-side. */
  parseMatrix(body: {
    text: string;
    sample_rate_hz: number;
    ground_truth_gesture?: string | null;
  }): Observable<MatrixParseResponse> {
    return this.http.post<MatrixParseResponse>(`${this.base}/emg/parse`, body);
  }

  // ── Executions ────────────────────────────────────────────────────────────
  runExecution(payload: RunExecutionPayload): Observable<RunExecutionResult> {
    return this.http.post<RunExecutionResult>(`${this.base}/executions/run`, payload);
  }

  executionStats(since?: string): Observable<ExecutionStats> {
    let params = new HttpParams();
    if (since) params = params.set('since', since);
    return this.http.get<ExecutionStats>(`${this.base}/executions/stats`, { params });
  }

  /** Streamed straight from the API so the file matches it byte for byte. */
  exportExecutionsCsv(body: { since?: string; project_id?: string }): Observable<Blob> {
    return this.http.post(`${this.base}/export/executions.csv`, body, {
      responseType: 'blob',
    });
  }

  listExecutions(limit = 50): Observable<Execution[]> {
    const params = new HttpParams().set('limit', limit);
    return this.http.get<Execution[]>(`${this.base}/executions`, { params });
  }

  getExecution(id: string): Observable<Execution> {
    return this.http.get<Execution>(`${this.base}/executions/${id}`);
  }

  replayMovement(id: string): Observable<{ replayed: boolean }> {
    return this.http.post<{ replayed: boolean }>(
      `${this.base}/executions/${id}/replay-movement`, {},
    );
  }
}
