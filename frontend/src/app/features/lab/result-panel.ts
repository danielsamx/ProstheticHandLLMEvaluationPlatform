import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

import { LabStore } from '@core/services/lab.store';

const STAGES = ['parse', 'schema', 'protocol', 'consistency', 'range', 'kinematic', 'safety'];

/** Outcome of the most recent execution: metrics, validation trace, raw JSON. */
@Component({
  selector: 'ph-result-panel',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, MatTooltipModule],
  template: `
    @if (store.lastResult(); as execution) {
      <div class="space-y-3">
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

        <!-- Metrics -->
        @if (execution.metrics; as metrics) {
          <div class="grid grid-cols-4 gap-2">
            <div class="rounded border border-ink-200 bg-ink-50 p-2">
              <div class="lab-label">Latency</div>
              <div class="lab-mono text-sm text-pink">
                {{ execution.latency_ms ?? '—' }}<span class="text-[10px] text-ink-500">ms</span>
              </div>
            </div>
            <div class="rounded border border-ink-200 bg-ink-50 p-2">
              <div class="lab-label">Tokens</div>
              <div class="lab-mono text-sm">
                {{ execution.total_tokens ?? '—' }}
                <span class="text-[10px] text-ink-500">
                  ({{ execution.prompt_tokens ?? 0 }}/{{ execution.completion_tokens ?? 0 }})
                </span>
              </div>
            </div>
            <div class="rounded border border-ink-200 bg-ink-50 p-2">
              <div class="lab-label">Cost</div>
              <div class="lab-mono text-sm">
                @if (execution.cost_usd > 0) {
                  \${{ execution.cost_usd.toFixed(6) }}
                } @else {
                  <span class="text-navy">local</span>
                }
              </div>
            </div>
            <div class="rounded border border-ink-200 bg-ink-50 p-2">
              <div class="lab-label">Throughput</div>
              <div class="lab-mono text-sm">
                {{ execution.tokens_per_second?.toFixed(1) ?? '—' }}
                <span class="text-[10px] text-ink-500">t/s</span>
              </div>
            </div>

            <div class="rounded border border-ink-200 bg-ink-50 p-2">
              <div class="lab-label">Intent</div>
              <div class="lab-mono text-xs">{{ metrics.intent ?? '—' }}</div>
            </div>
            <div class="rounded border border-ink-200 bg-ink-50 p-2">
              <div class="lab-label">Pattern</div>
              <div class="lab-mono text-xs">{{ metrics.detected_pattern ?? '—' }}</div>
            </div>
            <div class="rounded border border-ink-200 bg-ink-50 p-2">
              <div class="lab-label">Confidence</div>
              <div class="lab-mono text-xs">
                {{ metrics.model_confidence !== null ? (metrics.model_confidence * 100).toFixed(0) + '%' : '—' }}
              </div>
            </div>
            <div class="rounded border border-ink-200 bg-ink-50 p-2"
                 matTooltip="Scored only when the EMG window carries a ground-truth label.">
              <div class="lab-label">Accuracy</div>
              <div class="lab-mono text-xs">
                @if (metrics.gesture_correct === null) { <span class="text-ink-500">unlabelled</span> }
                @else if (metrics.gesture_correct) { <span class="text-navy">correct</span> }
                @else { <span class="text-pink">wrong</span> }
              </div>
            </div>
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
  protected readonly stages = STAGES;

  protected readonly issues = computed(
    () => this.store.lastResult()?.validation_result?.issues ?? [],
  );

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
