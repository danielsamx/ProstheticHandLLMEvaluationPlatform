import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSliderModule } from '@angular/material/slider';
import { MatTooltipModule } from '@angular/material/tooltip';

import { LabStore } from '@core/services/lab.store';

/**
 * Provider / model / decoding controls.
 *
 * Capability flags from the catalogue drive the UI: a knob a runtime cannot
 * honour is disabled rather than silently ignored, so the researcher is never
 * misled about which variables are actually under their control.
 */
@Component({
  selector: 'ph-model-config',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    FormsModule, MatButtonModule, MatFormFieldModule, MatIconModule,
    MatInputModule, MatSelectModule, MatSliderModule, MatTooltipModule,
  ],
  template: `
    <div class="space-y-4">
      <!--
        Provider, model and the import action share one row. They are a single
        decision — "which model am I running" — and splitting the refresh into a
        separate block made it read like an unrelated maintenance task.
      -->
      <div class="grid grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_auto_auto] items-end gap-2">
        <div>
          <label class="lab-label">Provider</label>
          <mat-form-field appearance="outline" class="dense-field">
            <mat-select
              [ngModel]="store.selectedProviderId()"
              (ngModelChange)="store.selectedProviderId.set($event)"
            >
              @for (p of store.providers(); track p.id) {
                <mat-option [value]="p.id">{{ p.display_name }}</mat-option>
              }
            </mat-select>
          </mat-form-field>
        </div>

        <div>
          <label class="lab-label">Model</label>
          <mat-form-field appearance="outline" class="dense-field">
            <mat-select
              [ngModel]="store.selectedModelId()"
              (ngModelChange)="store.selectedModelId.set($event)"
            >
              <!--
                Only models the runtime currently has loaded. A catalogue entry
                is not proof a model can run, and offering one that cannot fails
                at inference with an error that looks like a connectivity fault.
              -->
              @for (m of store.runnableModels(); track m.id) {
                <mat-option [value]="m.id">{{ m.display_name }}</mat-option>
              } @empty {
                <mat-option [disabled]="true">No model loaded in LM Studio</mat-option>
              }
            </mat-select>
          </mat-form-field>
        </div>

        <button mat-stroked-button class="!mb-0.5 !h-[34px] !px-3 !text-[11px]"
                matTooltip="Re-read the model list from the running LM Studio server"
                [disabled]="store.syncingCatalogue()"
                (click)="store.syncLmStudioModels()">
          <mat-icon class="!h-4 !w-4 !text-[16px]">
            {{ store.syncingCatalogue() ? 'hourglass_empty' : 'sync' }}
          </mat-icon>
          <span class="hidden lg:inline">Refresh</span>
        </button>

        <!--
          Thinking suppression, as a button rather than a labelled row.

          It belongs beside the model because it is a property of *how this model
          is asked*, not a decoding parameter: it changes which channel the
          answer arrives on, and a reasoning model given a hard classification
          can spend its whole budget deliberating and return nothing usable.

          Filled navy when suppressed, amber outline when not. Amber is the
          state that produces the confusing result, so it is the one that has to
          catch the eye — a researcher should never have to remember which way
          they left this.
        -->
        <button mat-stroked-button
                class="!mb-0.5 !h-[34px] !min-w-0 !px-2.5 !text-[11px]"
                [class]="store.disableReasoning()
                  ? '!bg-navy !text-white !border-navy'
                  : '!border-amber !text-navy'"
                [matTooltip]="store.disableReasoning()
                  ? 'Thinking suppressed: enable_thinking=false and reasoning_effort=none are sent, so the answer arrives on the content channel. Click to allow reasoning.'
                  : 'Reasoning allowed. A reasoning model may spend its whole token budget thinking and answer on its reasoning channel instead — or return nothing. Click to suppress.'"
                (click)="store.disableReasoning.set(!store.disableReasoning())">
          <mat-icon class="!h-4 !w-4 !text-[16px]">
            {{ store.disableReasoning() ? 'psychology_alt' : 'psychology' }}
          </mat-icon>
          <span class="hidden xl:inline">
            {{ store.disableReasoning() ? 'No thinking' : 'Thinking' }}
          </span>
        </button>
      </div>

      @if (!store.runnableModels().length) {
        <div class="flex items-start gap-2 rounded border border-amber bg-amber/10 px-3 py-2 text-[11px] text-navy">
          <mat-icon class="!h-4 !w-4 !text-[16px]">inventory_2</mat-icon>
          <span>
            Load a model in LM Studio and start its server, then press
            <strong>Refresh</strong>.
          </span>
        </div>
      }

      <div class="flex items-center justify-between gap-4 border-y border-ink-200 py-3">
        <div>
          <div class="lab-label">Model invocation</div>
          <p class="mt-0.5 text-[10px] text-ink-500">
            Tool calls are parsed as requests and still pass all seven safety validation stages.
          </p>
        </div>
        <div class="flex shrink-0 overflow-hidden rounded border border-navy text-xs font-semibold">
          <button type="button" class="px-3 py-2" [class.bg-navy]="store.invocationMode() === 'structured_output'" [class.text-white]="store.invocationMode() === 'structured_output'" (click)="store.invocationMode.set('structured_output')">
            Structured output
          </button>
          <button type="button" class="border-l border-navy px-3 py-2" [class.bg-navy]="store.invocationMode() === 'tool_calling'" [class.text-white]="store.invocationMode() === 'tool_calling'" (click)="store.invocationMode.set('tool_calling')">
            Tool calling
          </button>
        </div>
      </div>

      <!--
        The eight sampling parameters, four to a row.

        They belong together: every one of them is an input to the same
        decision, and splitting them across three grids implied a grouping that
        does not exist. Bottom alignment holds the controls to a common baseline
        despite a slider and a text field having different natural heights, so
        the two rows read as a grid rather than as staggered pairs.

        Four columns only from the md breakpoint up. Below that the sliders
        would be too narrow to position with any precision, and a slider you
        cannot aim is worse than one that takes a second row.
      -->
      <div class="grid grid-cols-2 items-end gap-x-3 gap-y-2 md:grid-cols-4">
        <div>
          <div class="flex items-baseline justify-between">
            <label class="lab-label">Temperature</label>
            <!--
              The warning used to be a line of text below the slider. In a
              four-column grid that line would stretch the whole row, so it
              became the colour of the read-out plus a tooltip: still visible
              at a glance, no longer costing a row of height when it fires.
            -->
            <span class="lab-mono text-xs"
                  [class]="store.temperature() > 0 ? 'text-amber' : 'text-pink'"
                  [matTooltip]="store.temperature() > 0
                    ? 'Non-zero temperature makes repeated runs non-deterministic.'
                    : 'Greedy decoding: repeated runs should be identical.'">
              {{ store.temperature().toFixed(2) }}
            </span>
          </div>
          <mat-slider [min]="0" [max]="2" [step]="0.01" class="w-full">
            <input matSliderThumb
                   [ngModel]="store.temperature()"
                   (ngModelChange)="store.temperature.set($event)" />
          </mat-slider>
        </div>

        <div>
          <div class="flex items-baseline justify-between">
            <label class="lab-label">Top-P</label>
            <span class="lab-mono text-xs text-pink">{{ store.topP().toFixed(2) }}</span>
          </div>
          <mat-slider [min]="0.01" [max]="1" [step]="0.01" class="w-full">
            <input matSliderThumb
                   [ngModel]="store.topP()"
                   (ngModelChange)="store.topP.set($event)" />
          </mat-slider>
        </div>

        <div>
          <label class="lab-label" [matTooltip]="topKTooltip()">Top-K</label>
          <mat-form-field appearance="outline" class="dense-field">
            <input matInput type="number" min="1" max="500" placeholder="off"
                   [disabled]="!(store.selectedModel()?.supports_top_k ?? false)"
                   [ngModel]="store.topK()"
                   (ngModelChange)="store.topK.set($event === null || $event === '' ? null : +$event)" />
          </mat-form-field>
        </div>

        <div>
          <label class="lab-label"
                 matTooltip="Shares the context window with the prompt. A complete JSON response runs to about 200 tokens; below that it truncates mid-object and is recorded as a parse failure.">
            Max Tokens
          </label>
          <mat-form-field appearance="outline" class="dense-field">
            <input matInput type="number" min="1"
                   [ngModel]="store.maxTokens()"
                   (ngModelChange)="store.maxTokens.set(+$event)" />
          </mat-form-field>
        </div>

        <div>
          <label class="lab-label" matTooltip="Fixing the seed is what makes a run replayable.">
            Seed
          </label>
          <mat-form-field appearance="outline" class="dense-field">
            <input matInput type="number" placeholder="random"
                   [disabled]="!(store.selectedModel()?.supports_seed ?? false)"
                   [ngModel]="store.seed()"
                   (ngModelChange)="store.seed.set($event === null || $event === '' ? null : +$event)" />
          </mat-form-field>
        </div>

        <div>
          <label class="lab-label">Freq. Penalty</label>
          <mat-form-field appearance="outline" class="dense-field">
            <input matInput type="number" min="-2" max="2" step="0.1"
                   [disabled]="!(store.selectedModel()?.supports_penalties ?? true)"
                   [ngModel]="store.frequencyPenalty()"
                   (ngModelChange)="store.frequencyPenalty.set(+$event)" />
          </mat-form-field>
        </div>

        <div>
          <label class="lab-label">Presence Penalty</label>
          <mat-form-field appearance="outline" class="dense-field">
            <input matInput type="number" min="-2" max="2" step="0.1"
                   [disabled]="!(store.selectedModel()?.supports_penalties ?? true)"
                   [ngModel]="store.presencePenalty()"
                   (ngModelChange)="store.presencePenalty.set(+$event)" />
          </mat-form-field>
        </div>

        <div>
          <label class="lab-label">Response Format</label>
          <mat-form-field appearance="outline" class="dense-field">
            <mat-select [ngModel]="store.responseFormat()"
                        (ngModelChange)="store.responseFormat.set($event)"
                        [disabled]="store.invocationMode() === 'tool_calling'">
              <mat-option value="text">text</mat-option>
              <mat-option value="json_object">json_object</mat-option>
              <mat-option value="json_schema"
                          [disabled]="!(store.selectedModel()?.supports_json_schema ?? false)">
                json_schema
              </mat-option>
            </mat-select>
          </mat-form-field>
        </div>
      </div>

      <!--
        Hand, limit profile and repetitions were controls without a decision
        behind them: this hand is right-handed, TABLE_5_V3 is the profile the
        firmware implements, and a single run is what the button means. Pinning
        them removes three ways to make a comparison accidentally incomparable.
        They remain parameters on the API for when a second unit exists.
      -->
    </div>
  `,
})
export class ModelConfig {
  protected readonly store = inject(LabStore);

  protected topKTooltip(): string {
    return this.store.selectedModel()?.supports_top_k
      ? 'Nucleus cut-off by rank.'
      : 'This model does not expose top_k; the parameter would be dropped.';
  }
}
