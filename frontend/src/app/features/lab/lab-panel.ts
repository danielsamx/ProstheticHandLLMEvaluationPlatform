import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatTooltipModule } from '@angular/material/tooltip';

import { LabStore } from '@core/services/lab.store';
import { HistoryPanel } from '@features/history/history-panel';
import { EmgPanel } from './emg-panel';
import { ModelConfig } from './model-config';
import { PromptBlocks } from './prompt-blocks';
import { ResultPanel } from './result-panel';

/** Left half of the screen: the model evaluation laboratory. */
@Component({
  selector: 'ph-lab-panel',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    MatButtonModule, MatExpansionModule, MatIconModule, MatProgressBarModule,
    MatTooltipModule, EmgPanel, HistoryPanel, ModelConfig, PromptBlocks, ResultPanel,
  ],
  template: `
    <div class="flex h-full flex-col">
      @if (store.running()) {
        <mat-progress-bar mode="indeterminate" class="!h-0.5"></mat-progress-bar>
      }

      <div class="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
        @if (store.error(); as message) {
          <div class="flex items-start gap-2 rounded border border-pink bg-pink/5 px-3 py-2 text-[11px]">
            <mat-icon class="!h-4 !w-4 !text-[16px] text-pink">error_outline</mat-icon>
            <span class="flex-1 text-pink">{{ message }}</span>
            <button class="text-pink" (click)="store.error.set(null)">
              <mat-icon class="!h-4 !w-4 !text-[16px]">close</mat-icon>
            </button>
          </div>
        }

        <mat-accordion multi>
          <mat-expansion-panel expanded>
            <mat-expansion-panel-header>
              <mat-panel-title class="!text-xs !font-semibold">
                <mat-icon class="!mr-2 !h-4 !w-4 !text-[16px] text-pink">tune</mat-icon>
                Model &amp; decoding
              </mat-panel-title>
            </mat-expansion-panel-header>
            <ph-model-config />
          </mat-expansion-panel>

          <mat-expansion-panel expanded>
            <mat-expansion-panel-header>
              <mat-panel-title class="!text-xs !font-semibold">
                <mat-icon class="!mr-2 !h-4 !w-4 !text-[16px] text-pink">monitor_heart</mat-icon>
                EMG input &middot; 8 channels
              </mat-panel-title>
            </mat-expansion-panel-header>
            <ph-emg-panel />
          </mat-expansion-panel>

          <mat-expansion-panel>
            <mat-expansion-panel-header>
              <mat-panel-title class="!text-xs !font-semibold">
                <mat-icon class="!mr-2 !h-4 !w-4 !text-[16px] text-pink">article</mat-icon>
                Prompt blocks
              </mat-panel-title>
            </mat-expansion-panel-header>
            <ph-prompt-blocks />
          </mat-expansion-panel>

          <mat-expansion-panel expanded>
            <mat-expansion-panel-header>
              <mat-panel-title class="!text-xs !font-semibold">
                <mat-icon class="!mr-2 !h-4 !w-4 !text-[16px] text-pink">fact_check</mat-icon>
                Result
              </mat-panel-title>
            </mat-expansion-panel-header>
            <ph-result-panel />
          </mat-expansion-panel>

          <mat-expansion-panel>
            <mat-expansion-panel-header>
              <mat-panel-title class="!text-xs !font-semibold">
                <mat-icon class="!mr-2 !h-4 !w-4 !text-[16px] text-pink">history</mat-icon>
                Configurations &amp; execution history
              </mat-panel-title>
            </mat-expansion-panel-header>
            <ph-history-panel />
          </mat-expansion-panel>
        </mat-accordion>
      </div>

      <!-- ── Run bar ─────────────────────────────────────────────────────── -->
      <footer class="shrink-0 border-t border-ink-200 bg-ink-50 p-3">
        <div class="flex items-center gap-3">
          <button
            mat-flat-button
            color="primary"
            class="!h-11 !flex-1 !text-sm !font-semibold"
            [disabled]="!store.canRun()"
            (click)="store.runEvaluation()"
          >
            <mat-icon>play_arrow</mat-icon>
            {{ store.running() ? 'Running…' : 'Run Evaluation' }}
            @if (store.repetitions() > 1) {
              <span class="ml-1 text-[11px] opacity-80">&times;{{ store.repetitions() }}</span>
            }
          </button>

          <button mat-stroked-button class="!h-10"
                  matTooltip="Save the current model and decoding parameters for reuse."
                  [disabled]="!store.selectedModelId()"
                  (click)="saveConfiguration()">
            <mat-icon>bookmark_add</mat-icon>
          </button>
        </div>

        <div class="mt-2 flex items-center justify-between text-[10px] text-ink-500">
          <span>
            Each run is an independent experiment &mdash; no conversation, no memory.
          </span>
          @if (store.successRate(); as rate) {
            <span class="lab-mono">
              session pass rate {{ (rate * 100).toFixed(0) }}%
            </span>
          }
        </div>
      </footer>
    </div>
  `,
})
export class LabPanel {
  protected readonly store = inject(LabStore);

  protected async saveConfiguration(): Promise<void> {
    const model = this.store.selectedModel();
    const suggestion = model
      ? `${model.display_name} @ T=${this.store.temperature()}`
      : 'New configuration';
    const name = prompt('Name this configuration:', suggestion);
    if (name) await this.store.saveConfiguration(name);
  }
}
