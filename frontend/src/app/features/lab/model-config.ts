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
      <!-- Provider / model -->
      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="lab-label">LLM Provider</label>
          <mat-form-field appearance="outline" class="dense-field">
            <mat-select
              [ngModel]="store.selectedProviderId()"
              (ngModelChange)="store.selectedProviderId.set($event)"
            >
              @for (p of store.providers(); track p.id) {
                <mat-option [value]="p.id">
                  {{ p.display_name }}
                  @if (p.is_local) { <span class="text-[10px] text-navy">&nbsp;local</span> }
                </mat-option>
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
              @for (m of store.modelsForProvider(); track m.id) {
                <mat-option [value]="m.id">{{ m.display_name }}</mat-option>
              } @empty {
                <mat-option [disabled]="true">No models in the catalogue</mat-option>
              }
            </mat-select>
          </mat-form-field>
        </div>
      </div>

      @if (!store.models().length) {
        <div class="flex items-start gap-2 rounded border border-amber bg-amber/10 px-3 py-2 text-[11px] text-navy">
          <mat-icon class="!h-4 !w-4 !text-[16px]">inventory_2</mat-icon>
          <span>
            The model catalogue is empty. If the backend just restarted, reload
            the page; otherwise load a model in LM Studio and use
            <strong>Import loaded models</strong> below.
          </span>
        </div>
      }

      @if (store.lmStudio(); as lm) {
        <div class="flex items-center justify-between rounded border border-ink-200 bg-ink-50 px-3 py-2 text-[11px]">
          <span class="text-ink-500">
            LM Studio at <span class="lab-mono">{{ lm.api_base }}</span> &mdash;
            @if (lm.reachable) {
              <span class="text-navy">{{ lm.models.length }} model(s) loaded</span>
            } @else {
              <span class="text-pink">unreachable</span>
            }
          </span>
          <button mat-stroked-button class="!min-h-0 !py-0 !text-[11px]"
                  (click)="store.syncLmStudioModels()">
            <mat-icon class="!h-4 !w-4 !text-[16px]">sync</mat-icon>
            Import loaded models
          </button>
        </div>
      }

      <!-- Decoding parameters -->
      <div class="grid grid-cols-2 gap-x-4 gap-y-3">
        <div>
          <div class="flex items-baseline justify-between">
            <label class="lab-label">Temperature</label>
            <span class="lab-mono text-xs text-pink">{{ store.temperature().toFixed(2) }}</span>
          </div>
          <mat-slider [min]="0" [max]="2" [step]="0.01" class="w-full">
            <input matSliderThumb
                   [ngModel]="store.temperature()"
                   (ngModelChange)="store.temperature.set($event)" />
          </mat-slider>
          @if (store.temperature() > 0) {
            <p class="text-[10px] text-amber">
              Non-zero temperature makes repeated runs non-deterministic.
            </p>
          }
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
            <input matInput type="number" min="1" max="500" placeholder="disabled"
                   [disabled]="!(store.selectedModel()?.supports_top_k ?? false)"
                   [ngModel]="store.topK()"
                   (ngModelChange)="store.topK.set($event === null || $event === '' ? null : +$event)" />
          </mat-form-field>
        </div>

        <div>
          <label class="lab-label">Max Tokens</label>
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
          <label class="lab-label">Frequency Penalty</label>
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
                        (ngModelChange)="store.responseFormat.set($event)">
              <mat-option value="text">text (free-form)</mat-option>
              <mat-option value="json_object">json_object</mat-option>
              <mat-option value="json_schema"
                          [disabled]="!(store.selectedModel()?.supports_json_schema ?? false)">
                json_schema (strict)
              </mat-option>
            </mat-select>
          </mat-form-field>
        </div>
      </div>

      <!-- Experimental conditions -->
      <div class="grid grid-cols-3 gap-3 border-t border-ink-200 pt-3">
        <div>
          <label class="lab-label">Hand</label>
          <mat-form-field appearance="outline" class="dense-field">
            <mat-select [ngModel]="store.handedness()"
                        (ngModelChange)="store.handedness.set($event)">
              <mat-option value="right">Right</mat-option>
              <mat-option value="left">Left</mat-option>
            </mat-select>
          </mat-form-field>
        </div>

        <div>
          <label class="lab-label"
                 matTooltip="The manual documents two different travel envelopes; pin the one this run assumes.">
            Limit profile
          </label>
          <mat-form-field appearance="outline" class="dense-field">
            <mat-select [ngModel]="store.limitProfile()"
                        (ngModelChange)="store.limitProfile.set($event)">
              @for (p of store.handSpec()?.limit_profiles ?? []; track p.id) {
                <mat-option [value]="p.id">{{ p.id }}</mat-option>
              }
            </mat-select>
          </mat-form-field>
        </div>

        <div>
          <label class="lab-label" matTooltip="Repeat the identical run to measure determinism.">
            Repetitions
          </label>
          <mat-form-field appearance="outline" class="dense-field">
            <input matInput type="number" min="1" max="50"
                   [ngModel]="store.repetitions()"
                   (ngModelChange)="store.repetitions.set(+$event)" />
          </mat-form-field>
        </div>
      </div>
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
