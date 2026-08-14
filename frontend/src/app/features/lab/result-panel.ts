import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

import { Execution, ExecutionMetrics } from '@core/models/llm.model';
import { LabStore } from '@core/services/lab.store';
import { ApiService } from '@core/api/api.service';
import { TranslatePipe } from '@core/services/language.service';

//
// Seven gates, in the order the backend runs them. `schema` checks the object
// has the declared shape; `consistency` checks the serial_command agrees with
// the intent, gesture and commands stated beside it. Both exist only because
// the response states its decision twice — which is the point: a model that
// contradicts itself is invisible under a single-representation contract.
//
// The order matters on screen as much as in the pipeline: the first red gate
// is where the model actually broke down, and the ones after it were never
// reached rather than passed.
//
const STAGES = ['parse', 'schema', 'protocol', 'consistency', 'range', 'kinematic', 'safety'];

/** Outcome of the most recent execution: metrics, validation trace, raw JSON. */
@Component({
  selector: 'ph-result-panel',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, MatTooltipModule, FormsModule, TranslatePipe],
  template: `
    @if (store.lastResult(); as execution) {
      <div class="space-y-3">
        @if (execution.custom_parameters['invocation_mode'] === 'tool_calling') {
          <div class="flex items-center justify-between rounded border border-navy bg-ink-50 px-3 py-2 text-xs">
            <span class="flex items-center gap-2 font-semibold text-navy"><mat-icon class="!h-4 !w-4 !text-[16px]">build</mat-icon>Tool call received</span>
            <span class="lab-mono text-pink">{{ execution.custom_parameters['tool_name'] }}</span>
          </div>
        }
        <div class="flex items-center justify-between gap-3 text-[10px] text-ink-500">
          <span class="lab-mono font-semibold text-navy">
            Attempt {{ attemptNumber(execution) }} of 3
          </span>
          @if (execution.custom_parameters['feedback_parent_execution']) {
            <span class="truncate">
              Corrected from {{ execution.custom_parameters['feedback_parent_execution'] }}
            </span>
          }
        </div>
        <!-- Headline -->
        <div class="flex items-center justify-between rounded border px-3 py-2"
             [class]="execution.validation_passed
               ? 'border-navy bg-ink-50'
               : 'border-pink bg-pink/5'">
          <div class="flex items-center gap-2">
            <mat-icon [class]="execution.validation_passed ? 'text-navy' : 'text-pink'">
              {{ execution.validation_passed ? 'check_circle' : 'cancel' }}
            </mat-icon>
            <div class="leading-tight">
              <div class="text-xs font-semibold">
                {{ execution.validation_passed ? 'Command accepted' : 'Execution failed' }}
              </div>
              <div class="lab-mono text-[10px] text-ink-500">
                {{ execution.status }}
                @if (execution.validation_result?.failed_stage; as stage) {
                  &middot; rejected at {{ stage }}
                }
              </div>
            </div>
          </div>

          @if (execution.movement?.serial_command; as serial) {
            <span class="lab-mono rounded bg-ink-100 px-2 py-1 text-xs text-pink"
                  matTooltip="Exact ASCII line for the Bluetooth SPP link">{{ serial }}</span>
          }
        </div>

        <!--
          Provider failures produce no validation result at all, so without this
          the panel could only say "failed" and never why. The hint, when the
          backend recognised the cause, is the actionable part.
        -->
        @if (providerErrors().length) {
          @for (error of providerErrors(); track error.message) {
            <div class="rounded border border-pink bg-pink/5 p-3">
              <div class="mb-1 flex items-center gap-2">
                <mat-icon class="!h-4 !w-4 !text-[16px] text-pink">cloud_off</mat-icon>
                <span class="text-xs font-semibold text-pink">
                  {{ error.error_type }}
                  @if (error.provider_status_code) {
                    <span class="lab-mono font-normal">({{ error.provider_status_code }})</span>
                  }
                </span>
              </div>

              @if (hintFor(error); as hint) {
                <p class="mb-2 text-[11px] leading-relaxed text-navy">{{ hint }}</p>
              }

              <details>
                <summary class="cursor-pointer text-[11px] text-ink-500">
                  Message from the runtime
                </summary>
                <pre class="lab-mono mt-1 max-h-32 overflow-auto rounded bg-white p-2 text-[10px] leading-relaxed text-ink-600">{{ error.message }}</pre>
              </details>

              @if (error.context['estimated_prompt_tokens']; as tokens) {
                <p class="mt-1 text-[10px] text-ink-500">
                  Prompt sent: ~{{ tokens }} tokens
                  ({{ error.context['prompt_chars'] }} characters)
                </p>
              }
            </div>
          }
        }

        <!-- Validation pipeline trace -->
        <div>
          <div class="lab-label mb-1">Validation pipeline</div>
          <div class="flex items-center gap-1">
            @for (stage of stages; track stage) {
              <div class="flex flex-1 flex-col items-center gap-1">
                <div class="h-1.5 w-full rounded" [class]="stageColour(stage)"></div>
                <span class="text-[9px] uppercase tracking-wide"
                      [class]="stageReached(stage) ? 'text-ink-500' : 'text-ink-400'">
                  {{ stage }}
                </span>
              </div>
            }
          </div>
        </div>

        <!-- Issues -->
        @if (issues().length) {
          <div class="space-y-1">
            @for (issue of issues(); track issue.code + issue.message) {
              <div class="rounded border px-2 py-1.5 text-[11px]"
                   [class]="issue.severity === 'error'
                     ? 'border-pink bg-pink/5'
                     : 'border-amber bg-amber/10'">
                <div class="flex items-center gap-2">
                  <span class="lab-mono text-[10px]"
                        [class]="issue.severity === 'error' ? 'text-pink' : 'text-amber'">
                    {{ issue.stage }}/{{ issue.code }}
                  </span>
                </div>
                <div class="text-ink-700">{{ issue.message }}</div>
              </div>
            }
          </div>
        }

        <!--
          The outcome, nine cards, six to a row.

          Grouped by what they answer rather than by where the number came
          from: the first row is whether the model was *right*, the second is
          what it cost. Cost figures are the easy ones to read and were sitting
          first, which put the least important row at the top.

          Colour separates the two groups, so which half you are looking at is
          answered before any number is read.
        -->
        @if (execution.metrics; as metrics) {
          <div class="grid grid-cols-3 gap-1.5 sm:grid-cols-4 lg:grid-cols-6">
            @for (card of metricCards(execution, metrics); track card.label) {
              <div class="flex items-center gap-1.5 rounded-md px-2 py-1.5"
                   [class]="card.tone"
                   [matTooltip]="card.hint">
                <mat-icon class="!h-4 !w-4 shrink-0 !text-[16px] opacity-70">
                  {{ card.icon }}
                </mat-icon>
                <div class="min-w-0 leading-none">
                  <div class="lab-mono truncate text-[12px] font-semibold">
                    {{ card.value }}<span class="text-[9px] font-normal opacity-70">{{ card.unit }}</span>
                  </div>
                  <div class="mt-0.5 truncate text-[9px] uppercase tracking-wider opacity-70">
                    {{ card.label }}
                  </div>
                </div>
              </div>
            }
          </div>
        }

        <!-- Determinism across repetitions -->
        @if (store.determinism(); as determinism) {
          <div class="rounded border border-navy bg-ink-50 px-3 py-2 text-[11px]">
            <span class="lab-label">Determinism</span>
            <div class="text-ink-700">
              {{ determinism.distinct_responses }} distinct response(s);
              modal agreement
              <span class="lab-mono text-pink">
                {{ determinism.determinism_rate !== null
                    ? (determinism.determinism_rate * 100).toFixed(0) + '%' : '—' }}
              </span>
            </div>
          </div>
        }

        <!-- Human feedback covers every model decision, including rejected commands and no_action. -->
        @if (execution.parsed_response) {
          <section class="rounded border border-amber bg-amber/10 p-3">
            <div class="flex items-center justify-between gap-3">
              <div><span class="lab-label">Gesture classification feedback</span>
                <p class="text-[11px] text-ink-600">Rate the prediction even when the model requested no movement.</p></div>
              <div class="flex gap-2">
                <button class="rounded bg-navy px-3 py-2 text-xs text-white" (click)="sendFeedback(execution, true)">{{ 'Correct' | tr }}</button>
                <button class="rounded bg-pink px-3 py-2 text-xs text-white" (click)="openFeedback(execution)">{{ 'Incorrect' | tr }}</button>
              </div>
            </div>
            @if (feedbackOpen()) {
              <div class="mt-3 grid gap-2 sm:grid-cols-2">
                <input class="rounded border p-2 text-xs" placeholder="Expected gesture" [(ngModel)]="expectedGesture" />
                <input class="rounded border p-2 text-xs" placeholder="Observed gesture" [(ngModel)]="observedGesture" />
                <textarea class="rounded border p-2 text-xs sm:col-span-2" placeholder="What went wrong" [(ngModel)]="feedbackNotes"></textarea>
                <label class="flex items-center gap-2 text-xs"><input type="checkbox" [(ngModel)]="autoRetry" /> Generate a corrected attempt</label>
                <button class="rounded bg-pink px-3 py-2 text-xs text-white" (click)="sendFeedback(execution, false)">Save feedback</button>
              </div>
            }
            @if (feedbackMessage()) { <p class="mt-2 text-xs font-semibold text-navy">{{ feedbackMessage() }}</p> }
          </section>
        }

        <!-- Raw model output -->
        <details class="rounded border border-ink-200 bg-ink-50">
          <summary class="cursor-pointer px-3 py-2 text-[11px] text-ink-500">
            Raw model response
          </summary>
          <pre class="lab-mono max-h-48 overflow-auto border-t border-ink-200 p-3 text-[10px] leading-relaxed text-ink-700">{{ execution.raw_response }}</pre>
        </details>
      </div>
    } @else {
      <div class="flex h-32 items-center justify-center rounded border border-dashed border-ink-200 text-[11px] text-ink-500">
        No execution yet. Configure the model, set the EMG window and run an evaluation.
      </div>
    }
  `,
})
export class ResultPanel {
  protected readonly store = inject(LabStore);
  private readonly api = inject(ApiService);
  protected readonly stages = STAGES;
  protected readonly feedbackOpen = signal(false);
  protected readonly feedbackMessage = signal('');
  protected expectedGesture = ''; protected observedGesture = ''; protected feedbackNotes = ''; protected autoRetry = true;

  protected attemptNumber(execution: Execution): number {
    const value = Number(execution.custom_parameters['feedback_attempt'] ?? 1);
    return Number.isFinite(value) && value >= 1 ? value : 1;
  }

  protected openFeedback(execution: Execution): void {
    this.expectedGesture = execution.expected_serial_command ?? '';
    this.observedGesture = String(execution.parsed_response?.['gesture'] ?? execution.parsed_response?.['intent'] ?? '');
    this.feedbackOpen.set(true);
  }

  protected async sendFeedback(execution: Execution, correct: boolean): Promise<void> {
    try {
      const result = await firstValueFrom(this.api.submitGestureFeedback(execution.id, {
        is_correct: correct, expected_gesture: this.expectedGesture || null,
        observed_gesture: this.observedGesture || null, notes: this.feedbackNotes || null,
        source: 'human',
        sensor_snapshot: { mechanical_telemetry: this.store.currentMechanicalTelemetry() },
        auto_retry: !correct && this.autoRetry, max_attempts: 3,
      }));
      if (result.correction_execution_id) {
        const correction = await firstValueFrom(
          this.api.getExecution(result.correction_execution_id),
        );
        this.store.lastResult.set(correction);
        this.store.history.update((items) =>
          [correction, ...items.filter((item) => item.id !== correction.id)].slice(0, 100),
        );
        this.feedbackMessage.set('Corrected attempt loaded. Review the new prediction.');
        this.expectedGesture = '';
        this.observedGesture = '';
        this.feedbackNotes = '';
      } else {
        this.feedbackMessage.set('Feedback saved.');
      }
      this.feedbackOpen.set(false);
    } catch (error: any) { this.feedbackMessage.set(error?.error?.detail ?? 'Unable to save feedback.'); }
  }

  /**
   * The nine outcome figures, ordered by what they answer.
   *
   * Correctness first, cost second. The cost numbers are the easiest to read
   * and were occupying the top row, which put the least consequential group
   * where the eye lands first. For a device that moves a hand, "was it right"
   * and "did it lie about being right" outrank "how many tokens".
   *
   * Navy for the correctness group, amber for cost, pink where a value is a
   * finding rather than a reading — a wrong answer, or a repaired reply.
   */
  protected metricCards(
    execution: Execution,
    metrics: ExecutionMetrics,
  ): { label: string; value: string; unit?: string; icon: string; tone: string; hint: string }[] {
    const navy = 'bg-navy/5 text-navy';
    const amber = 'bg-amber/15 text-navy';
    const pink = 'bg-pink/10 text-pink';

    const accuracy =
      metrics.command_matches_expected ?? metrics.gesture_correct;

    return [
      {
        label: 'Command',
        value: execution.movement?.serial_command
          ?? execution.validation_result?.normalised_serial
          ?? (metrics.refused_to_act ? 'no command' : '—'),
        icon: metrics.refused_to_act ? 'pause_circle' : 'terminal',
        tone: metrics.refused_to_act ? amber : execution.validation_passed ? navy : pink,
        hint: metrics.refused_to_act
          ? 'The model declined to act, so nothing was transmitted and the hand '
            + 'did not move. A valid outcome, not a failure.'
          : 'What would be sent to the prosthesis. Empty when validation rejected the response.',
      },
      {
        label: 'Accuracy',
        value: accuracy === null || accuracy === undefined
          ? 'unlabelled' : accuracy ? 'correct' : 'wrong',
        icon: accuracy ? 'check_circle' : accuracy === false ? 'cancel' : 'help_outline',
        tone: accuracy === null || accuracy === undefined ? navy : accuracy ? navy : pink,
        hint: 'Against your expected command, or the window\'s ground-truth label. '
            + 'Unlabelled runs were never a test of correctness.',
      },
      {
        label: 'Intent',
        value: metrics.intent ?? '—',
        icon: 'psychology_alt',
        tone: navy,
        hint: 'What the model said it was doing, as distinct from what it sent.',
      },
      {
        label: 'Pattern',
        value: metrics.detected_pattern ?? '—',
        icon: 'gesture',
        tone: navy,
        hint: 'The movement the model believed it saw. Used to group results.',
      },
      {
        label: 'Confidence',
        value: metrics.model_confidence === null
          ? '—' : metrics.model_confidence.toFixed(2),
        unit: metrics.calibration_error === null
          ? '' : ` err ${metrics.calibration_error.toFixed(2)}`,
        icon: 'speed',
        tone: navy,
        hint: 'What the model claimed about itself, and how far that claim was '
            + 'from the truth. A model wrong at 0.9 and one wrong at 0.3 fail '
            + 'equally on accuracy and very differently here.',
      },
      {
        label: 'Clean reply',
        value: metrics.is_bare_json ? 'yes' : 'repaired',
        icon: metrics.is_bare_json ? 'done_all' : 'build',
        tone: metrics.is_bare_json ? navy : pink,
        hint: 'The reply was bare JSON, with no fence or prose around it. The '
            + 'sharpest single measure of instruction adherence.',
      },
      {
        label: 'Latency',
        value: String(execution.latency_ms ?? '—'),
        unit: 'ms',
        icon: 'timer',
        tone: amber,
        hint: 'Wall time for the whole call. On a local model most of it is '
            + 'prompt processing, not generation.',
      },
      {
        label: 'Tokens',
        value: String(execution.total_tokens ?? '—'),
        unit: ` ${execution.prompt_tokens ?? 0}/${execution.completion_tokens ?? 0}`,
        icon: 'data_usage',
        tone: amber,
        hint: 'Total, then prompt / completion.',
      },
      {
        label: 'Throughput',
        value: execution.tokens_per_second?.toFixed(1) ?? '—',
        unit: ' t/s',
        icon: 'bolt',
        tone: amber,
        hint: execution.cost_usd > 0
          ? `Generation speed. Cost $${execution.cost_usd.toFixed(6)}.`
          : 'Generation speed. Local inference, so no per-token cost.',
      },
    ];
  }

  protected readonly issues = computed(
    () => this.store.lastResult()?.validation_result?.issues ?? [],
  );

  /** Failures that happened before the model ever answered. */
  protected readonly providerErrors = computed(
    () => (this.store.lastResult()?.errors ?? [])
      .filter((e) => e.category === 'provider' || e.category === 'internal'),
  );

  protected hintFor(error: { context: Record<string, unknown> }): string | null {
    const hint = error.context['hint'];
    return typeof hint === 'string' && hint ? hint : null;
  }

  protected stageReached(stage: string): boolean {
    return !!this.store.lastResult()?.validation_result?.stages_completed.includes(stage);
  }

  protected stageColour(stage: string): string {
    const result = this.store.lastResult()?.validation_result;
    if (!result) return 'bg-ink-200';
    if (result.failed_stage === stage) return 'bg-pink';
    return this.stageReached(stage) ? 'bg-navy' : 'bg-ink-200';
  }
}
