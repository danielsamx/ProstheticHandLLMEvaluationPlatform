import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { DatePipe } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

import { LabStore } from '@core/services/lab.store';
import { Execution, SamplingConfiguration } from '@core/models/llm.model';

/**
 * Reusable configuration history plus the execution log.
 *
 * Replaying a stored movement re-renders a pose that already passed validation,
 * so the history can never reintroduce an unsafe command.
 */
@Component({
  selector: 'ph-history-panel',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, MatButtonModule, MatIconModule, MatTooltipModule],
  template: `
    <div class="space-y-4">
      <!-- Saved configurations -->
      <div>
        <div class="lab-label mb-1.5">Saved configurations</div>
        @if (store.configurations().length) {
          <div class="space-y-1">
            @for (config of store.configurations(); track config.id) {
              <button
                class="flex w-full items-center justify-between rounded border px-2 py-1.5 text-left transition-colors"
                [class]="config.id === store.selectedConfigurationId()
                  ? 'border-pink bg-pink/5'
                  : 'border-ink-200 bg-ink-50 hover:border-ink-400'"
                (click)="store.applyConfiguration(config)"
              >
                <div class="min-w-0 flex-1">
                  <div class="truncate text-[11px] font-medium">{{ config.name }}</div>
                  <div class="lab-mono text-[10px] text-ink-500">
                    T={{ config.temperature }} &middot; top_p={{ config.top_p }}
                    @if (config.seed !== null) { &middot; seed={{ config.seed }} }
                    &middot; {{ config.response_format }}
                  </div>
                </div>
                <span class="lab-mono text-[10px] text-ink-500">
                  {{ config.use_count ?? 0 }}&times;
                </span>
              </button>
            }
          </div>
        } @else {
          <p class="text-[11px] text-ink-500">
            No saved configurations yet. Use the bookmark button to store the current setup.
          </p>
        }
      </div>

      <!-- Execution log -->
      <div>
        <div class="mb-1.5 flex items-center justify-between">
          <span class="lab-label">Execution history</span>
          <button mat-stroked-button class="!min-h-0 !py-0 !text-[10px]"
                  (click)="store.refreshHistory()">
            <mat-icon class="!h-3.5 !w-3.5 !text-[14px]">refresh</mat-icon> Refresh
          </button>
        </div>

        @if (store.history().length) {
          <div class="max-h-64 space-y-1 overflow-y-auto">
            @for (execution of store.history(); track execution.id) {
              <div class="flex items-center gap-2 rounded border border-ink-200 bg-ink-50 px-2 py-1.5">
                <span class="h-2 w-2 shrink-0 rounded-full"
                      [class]="execution.validation_passed ? 'bg-navy' : 'bg-pink'"></span>

                <div class="min-w-0 flex-1">
                  <div class="truncate lab-mono text-[10px] text-ink-700">
                    {{ execution.litellm_model ?? 'unknown model' }}
                  </div>
                  <div class="lab-mono text-[9px] text-ink-500">
                    {{ execution.created_at | date: 'HH:mm:ss' }}
                    &middot; {{ execution.latency_ms ?? '—' }}ms
                    @if (execution.movement?.serial_command; as serial) {
                      &middot; <span class="text-pink">{{ serial }}</span>
                    } @else if (execution.validation_result?.failed_stage; as stage) {
                      &middot; <span class="text-pink">{{ stage }}</span>
                    }
                  </div>
                </div>

                <button class="shrink-0 text-ink-500 hover:text-pink"
                        [disabled]="!execution.movement"
                        matTooltip="Replay this validated movement in the simulator"
                        (click)="store.replay(execution)">
                  <mat-icon class="!h-4 !w-4 !text-[16px]">replay</mat-icon>
                </button>
              </div>
            }
          </div>
        } @else {
          <p class="text-[11px] text-ink-500">No executions recorded yet.</p>
        }
      </div>
    </div>
  `,
})
export class HistoryPanel {
  protected readonly store = inject(LabStore);
  protected trackConfig = (_: number, config: SamplingConfiguration) => config.id;
  protected trackExecution = (_: number, execution: Execution) => execution.id;
}
