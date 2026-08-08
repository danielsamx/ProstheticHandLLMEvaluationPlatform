import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { RouterLink } from '@angular/router';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatTooltipModule } from '@angular/material/tooltip';

import { LabStore } from '@core/services/lab.store';
import { SaveDialog, SaveDialogData, SaveSummaryRow } from '@shared/save-dialog';
import { firstValueFrom } from 'rxjs';
import { EmgPanel } from './emg-panel';
import { ModelConfig } from './model-config';
import { PromptBlocks } from './prompt-blocks';
import { ResultPanel } from './result-panel';
import { TranslatePipe } from '@core/services/language.service';

/** Left half of the screen: the model evaluation laboratory. */
@Component({
  selector: 'ph-lab-panel',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    MatButtonModule, MatExpansionModule, MatIconModule, MatProgressBarModule,
    MatTooltipModule, RouterLink, EmgPanel, ModelConfig, PromptBlocks, ResultPanel, TranslatePipe,
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
                {{ '1. EMG signal · 8 channels' | tr }}
              </mat-panel-title>
            </mat-expansion-panel-header>
            <ph-emg-panel />
          </mat-expansion-panel>

          <mat-expansion-panel expanded>
            <mat-expansion-panel-header>
              <mat-panel-title class="!text-xs !font-semibold">
                <mat-icon class="!mr-2 !h-4 !w-4 !text-[16px] text-pink">monitor_heart</mat-icon>
                {{ '2. Model and parameters' | tr }}
              </mat-panel-title>
            </mat-expansion-panel-header>
            <ph-model-config />
          </mat-expansion-panel>

          <mat-expansion-panel>
            <mat-expansion-panel-header>
              <mat-panel-title class="!text-xs !font-semibold">
                <mat-icon class="!mr-2 !h-4 !w-4 !text-[16px] text-pink">article</mat-icon>
                {{ '3. Evaluation prompt' | tr }}
              </mat-panel-title>
            </mat-expansion-panel-header>
            <ph-prompt-blocks />
          </mat-expansion-panel>

          <mat-expansion-panel expanded>
            <mat-expansion-panel-header>
              <mat-panel-title class="!text-xs !font-semibold">
                <mat-icon class="!mr-2 !h-4 !w-4 !text-[16px] text-pink">fact_check</mat-icon>
                {{ '4. Result' | tr }}
              </mat-panel-title>
            </mat-expansion-panel-header>
            <ph-result-panel />
          </mat-expansion-panel>

        </mat-accordion>
      </div>

      <!-- ── Run bar ─────────────────────────────────────────────────────── -->
      <footer class="shrink-0 border-t border-ink-200 bg-ink-50 p-3">
        @if (store.blockingReason(); as reason) {
          <div class="mb-2 flex items-start gap-2 rounded border border-amber bg-amber/10 px-3 py-2 text-[11px] text-navy">
            <mat-icon class="!h-4 !w-4 !text-[16px]">info</mat-icon>
            <span>{{ reason }}</span>
          </div>
        }

        <div class="flex items-center gap-3">
          <button
            mat-flat-button
            color="primary"
            class="!h-11 !flex-1 !text-sm !font-semibold"
            [disabled]="!store.canRun()"
            [matTooltip]="store.blockingReason() ?? 'Run one independent evaluation'"
            (click)="store.runEvaluation()"
          >
            <mat-icon>play_arrow</mat-icon>
            {{ (store.running() ? 'Running…' : 'Run evaluation') | tr }}
            @if (store.repetitions() > 1) {
              <span class="ml-1 text-[11px] opacity-80">&times;{{ store.repetitions() }}</span>
            }
          </button>

          <button mat-stroked-button class="!h-11 !px-4"
                  matTooltip="Save this model and its parameters for reuse"
                  [disabled]="!store.selectedModelId()"
                  (click)="saveConfiguration()">
            <mat-icon>bookmark_add</mat-icon>
            <span class="ml-1 hidden text-[12px] font-semibold lg:inline">{{ 'Save configuration' | tr }}</span>
          </button>
        </div>

        <div class="mt-2 flex items-center justify-between text-[10px] text-ink-500">
          <span>
            Each run is an independent experiment, with no conversation or previous memory.
          </span>
          <a routerLink="/dashboard"
             class="flex items-center gap-1 font-semibold text-ink-500 hover:text-pink">
            <mat-icon class="!h-3.5 !w-3.5 !text-[14px]">insights</mat-icon>
            {{ 'View results' | tr }}
          </a>
        </div>
      </footer>
    </div>
  `,
})
export class LabPanel {
  protected readonly store = inject(LabStore);
  private readonly dialog = inject(MatDialog);

  /**
   * Save the current setup under a name.
   *
   * The dialog lists the parameters it is about to capture. A saved
   * configuration the researcher cannot verify is one they will not trust when
   * they come back to replay a comparison — which defeats the point of saving
   * it at all.
   */
  protected async saveConfiguration(): Promise<void> {
    const model = this.store.selectedModel();

    const result = await firstValueFrom(
      this.dialog
        .open(SaveDialog, {
          width: '440px',
          autoFocus: 'input',
          data: {
            title: 'Save this configuration',
            hint: 'Apply the same saved setup to every model in a comparison — '
                + 'that is what keeps the comparison controlled.',
            name: model
              ? `${model.display_name} · T=${this.store.temperature()}`
              : 'New configuration',
            offerFavorite: true,
            confirmLabel: 'Save configuration',
            summary: this.configurationSummary(),
          } satisfies SaveDialogData,
        })
        .afterClosed(),
    );

    if (result) {
      await this.store.saveConfiguration(result.name, {
        description: result.description,
        isFavorite: result.isFavorite,
      });
    }
  }

  private configurationSummary(): SaveSummaryRow[] {
    const model = this.store.selectedModel();
    const rows: SaveSummaryRow[] = [
      { label: 'Model', value: model?.display_name ?? '—' },
      { label: 'Temperature', value: this.store.temperature().toFixed(2) },
      { label: 'Top-P', value: this.store.topP().toFixed(2) },
      { label: 'Max tokens', value: String(this.store.maxTokens()) },
      { label: 'Seed', value: this.store.seed() === null ? 'random' : String(this.store.seed()) },
      { label: 'Response format', value: this.store.responseFormat() },
    ];
    if (this.store.topK() !== null) {
      rows.splice(3, 0, { label: 'Top-K', value: String(this.store.topK()) });
    }
    if (this.store.frequencyPenalty() !== 0 || this.store.presencePenalty() !== 0) {
      rows.push({
        label: 'Penalties',
        value: `freq ${this.store.frequencyPenalty()} · pres ${this.store.presencePenalty()}`,
      });
    }
    return rows;
  }
}
