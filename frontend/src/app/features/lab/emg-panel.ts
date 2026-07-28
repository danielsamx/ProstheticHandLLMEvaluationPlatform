import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  effect,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatTooltipModule } from '@angular/material/tooltip';

import { EmgStreamService } from '@core/services/emg-stream.service';
import { LabStore } from '@core/services/lab.store';
import { EmgMatrixPlot } from './emg-matrix-plot';

/**
 * The EMG stimulus: an N x 8 matrix of raw normalised samples.
 *
 * Three ways in — paste, synthesise, or stream live — because a matrix is not
 * something anyone types by hand. The derived feature table is shown read-only
 * beneath it: those numbers come from the signal, so letting them be edited
 * independently would allow a window whose summary contradicts its waveform.
 */
@Component({
  selector: 'ph-emg-panel',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    FormsModule, MatButtonModule, MatFormFieldModule, MatIconModule,
    MatInputModule, MatSelectModule, MatSlideToggleModule, MatTooltipModule,
    EmgMatrixPlot,
  ],
  template: `
    <div class="space-y-3">
      <!--
        Mode toggle and shape read-out share one row, split into two groups that
        are pushed to opposite ends. The distinction is what the user can act on:
        everything on the left changes the acquisition, everything on the right
        only reports what the current window contains. Interleaving them meant a
        reader had to check each item to know whether it was a control.

        The groups wrap independently, so on a narrow panel the read-out drops to
        its own line intact instead of splitting mid-way through the numbers.
      -->
      <div class="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5 text-[11px]">
        <!-- ── Controls ──────────────────────────────────────────────────── -->
        <div class="flex flex-wrap items-center gap-x-2.5 gap-y-1">
          <mat-slide-toggle class="dense-toggle shrink-0"
                            [ngModel]="store.liveMode()"
                            (ngModelChange)="toggleLive($event)">
            <span class="text-[11px] font-medium text-navy">
              {{ store.liveMode() ? 'Live' : 'Manual' }}
            </span>
          </mat-slide-toggle>

          @if (store.liveMode()) {
            <span class="lab-chip"
                  [class]="stream.state() === 'open' ? 'bg-navy text-white' : 'bg-amber text-navy'">
              {{ stream.state() }}
            </span>
            <span class="lab-mono text-[10px] text-ink-500">
              {{ stream.framesReceived() }}f · {{ stream.executionsTriggered() }}r
            </span>
            <mat-slide-toggle class="dense-toggle shrink-0"
                              [(ngModel)]="autoRun" (ngModelChange)="reconnect()">
              <span class="text-[10px] text-ink-600">Auto-run</span>
            </mat-slide-toggle>
          }
        </div>

        <!-- ── Read-out ──────────────────────────────────────────────────── -->
        <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span class="lab-chip bg-navy text-white lab-mono">{{ store.sampleCount() }} × 8</span>
          <span class="text-ink-500">
            {{ store.windowMs().toFixed(0) }} ms @ {{ store.sampleRateHz() }} Hz
          </span>
          <span class="hidden text-ink-500 xl:inline"
                matTooltip="Rows are time steps in ascending order; columns are CH1 to CH8. Values are raw converter output.">
            rows = time · cols = CH1…CH8 · raw
          </span>

          @if (store.groundTruth(); as truth) {
            <span class="lab-chip bg-amber text-navy"
                  matTooltip="Known correct answer — accuracy is scored automatically.">
              {{ truth }}
            </span>
          }
        </div>
      </div>

      <!-- ── Traces ────────────────────────────────────────────────────── -->
      <ph-emg-matrix-plot
        [samples]="store.matrix()"
        [labels]="store.channelLabels"
        [rms]="rmsValues()" />

      <!-- ── Sources ───────────────────────────────────────────────────── -->
      @if (!store.liveMode()) {
        <div class="flex flex-wrap items-center gap-2">
          <mat-form-field appearance="outline" class="dense-field !w-56">
            <mat-select placeholder="Load labelled synthetic window"
                        [ngModel]="null"
                        (ngModelChange)="$event && store.loadSynthetic($event)">
              @for (g of store.syntheticGestures(); track g) {
                <mat-option [value]="g">{{ g }}</mat-option>
              }
            </mat-select>
          </mat-form-field>

          <button mat-stroked-button class="!min-h-0 !py-0 !text-[11px]"
                  (click)="showPaste.set(!showPaste())">
            <mat-icon class="!h-4 !w-4 !text-[16px]">content_paste</mat-icon>
            {{ showPaste() ? 'Hide paste' : 'Paste matrix' }}
          </button>

          <button mat-stroked-button class="!min-h-0 !py-0 !text-[11px]" (click)="pickFile()">
            <mat-icon class="!h-4 !w-4 !text-[16px]">upload_file</mat-icon> Import CSV
          </button>

          <button mat-stroked-button class="!min-h-0 !py-0 !text-[11px]" (click)="copyCsv()">
            <mat-icon class="!h-4 !w-4 !text-[16px]">download</mat-icon>
            {{ copied() ? 'Copied' : 'Copy CSV' }}
          </button>

          <button mat-stroked-button class="!min-h-0 !py-0 !text-[11px]"
                  (click)="store.resetMatrix()">
            <mat-icon class="!h-4 !w-4 !text-[16px]">restart_alt</mat-icon> Clear
          </button>

          <input #fileInput type="file" accept=".csv,.tsv,.txt,.json" class="hidden"
                 (change)="onFile($event)" />
        </div>

        @if (showPaste()) {
          <div class="space-y-2 rounded-lg border border-ink-200 bg-ink-50 p-3">
            <textarea
              class="lab-mono h-28 w-full resize-none rounded border border-ink-200 bg-white p-2 text-[11px] outline-none focus:border-pink"
              spellcheck="false"
              placeholder="One row per time step, 8 raw values per row.&#10;CSV, TSV, whitespace or JSON. A header line (CH0…CH7 or CH1…CH8) is ignored.&#10;&#10;CH0,CH1,CH2,CH3,CH4,CH5,CH6,CH7&#10;-2,-2,-3,-3,0,2,0,0&#10;-2,2,0,4,4,2,-1,1"
              [(ngModel)]="pasteText"></textarea>

            <p class="text-[11px] text-ink-500">
              Values are loaded exactly as the file contains them. No scaling,
              no normalisation — the model is judged on what the hardware
              produced.
            </p>

            <div class="flex items-center justify-end">
              <button mat-flat-button color="primary" class="!min-h-0 !py-0 !text-[11px]"
                      [disabled]="!pasteText.trim()" (click)="applyPaste()">
                Load matrix
              </button>
            </div>

            @if (store.matrixError(); as message) {
              <div class="flex items-start gap-2 rounded border border-pink bg-pink/5 px-2 py-1.5 text-[11px] text-pink">
                <mat-icon class="!h-4 !w-4 !text-[16px]">error_outline</mat-icon>
                <span>{{ message }}</span>
              </div>
            }
          </div>
        }

        @for (warning of store.matrixWarnings(); track warning) {
          <div class="flex items-start gap-2 rounded border border-amber bg-amber/10 px-2 py-1.5 text-[11px] text-navy">
            <mat-icon class="!h-4 !w-4 !text-[16px]">info</mat-icon>
            <span>{{ warning }}</span>
          </div>
        }
      }

      <!-- ── Derived features (read-only) ──────────────────────────────── -->
      <div class="overflow-hidden rounded-lg border border-ink-200">
        <table class="w-full text-[11px]">
          <thead class="bg-ink-100 text-ink-600">
            <tr>
              <th class="px-2 py-1 text-left font-semibold">CH</th>
              <th class="px-2 py-1 text-right font-semibold">RMS</th>
              <th class="px-2 py-1 text-right font-semibold">MAV</th>
              <th class="px-2 py-1 text-right font-semibold">ZC</th>
              <th class="px-2 py-1 text-right font-semibold">SSC</th>
              <th class="px-2 py-1 text-right font-semibold">WL</th>
              <th class="px-2 py-1 text-right font-semibold">min</th>
              <th class="px-2 py-1 text-right font-semibold">max</th>
              <th class="px-2 py-1 text-left font-semibold">amplitude</th>
            </tr>
          </thead>
          <tbody class="lab-mono">
            @for (feature of store.features(); track feature.label; let i = $index) {
              <tr class="border-t border-ink-100" [class.bg-ink-50]="i % 2 === 1">
                <td class="px-2 py-1 font-semibold"
                    [style.color]="i < 4 ? '#D81B60' : (i < 7 ? '#001F3F' : '#B58900')"
                    [matTooltip]="siteFor(feature.label)">{{ feature.label }}</td>
                <td class="px-2 py-1 text-right">{{ num(feature.rms) }}</td>
                <td class="px-2 py-1 text-right">{{ num(feature.mav) }}</td>
                <td class="px-2 py-1 text-right">{{ feature.zc }}</td>
                <td class="px-2 py-1 text-right">{{ feature.ssc }}</td>
                <td class="px-2 py-1 text-right">{{ num(feature.wl) }}</td>
                <td class="px-2 py-1 text-right text-ink-500">{{ num(feature.min) }}</td>
                <td class="px-2 py-1 text-right text-ink-500">{{ num(feature.max) }}</td>
                <td class="px-2 py-1">
                  <!-- Relative to the loudest channel in this window: an
                       absolute scale is meaningless once the units are the
                       converter's own. -->
                  <div class="h-1.5 w-full overflow-hidden rounded bg-ink-100">
                    <div class="h-full transition-[width] duration-150"
                         [style.width.%]="relativeRms(feature.rms)"
                         [style.background]="i < 4 ? '#D81B60' : (i < 7 ? '#001F3F' : '#FFC107')"></div>
                  </div>
                </td>
              </tr>
            }
          </tbody>
        </table>
      </div>

      <!-- ── Aggregate interpretation ──────────────────────────────────── -->
      <div class="flex flex-wrap items-center justify-between gap-2 border-t border-ink-200 pt-2 text-[11px]">
        <div class="flex items-center gap-3 text-ink-600">
          <span>mean RMS <span class="lab-mono font-semibold text-navy">{{ num(store.meanRms()) }}</span></span>
          <span>flexor <span class="lab-mono text-pink">{{ num(store.flexorActivation()) }}</span></span>
          <span>extensor <span class="lab-mono text-navy">{{ num(store.extensorActivation()) }}</span></span>
          <span class="font-semibold"
                matTooltip="Flexor share of flexor + extensor. Scale-free, so it survives a change of gain — this is what decides open from close.">
            ratio <span class="lab-mono text-navy">{{ store.flexorRatio().toFixed(3) }}</span>
          </span>
        </div>

        <span class="lab-chip"
              [class]="interpretation().tone"
              [matTooltip]="interpretation().hint">
          {{ interpretation().label }}
        </span>
      </div>

      <!-- ── Window parameters ─────────────────────────────────────────── -->
      <div class="grid grid-cols-3 gap-2.5">
        <div>
          <label class="lab-label">Rows (samples)</label>
          <mat-form-field appearance="outline" class="dense-field">
            <input matInput type="number" min="4" max="8192"
                   [disabled]="store.liveMode()"
                   [ngModel]="store.sampleCount()"
                   (ngModelChange)="store.resizeMatrix(+$event)" />
          </mat-form-field>
        </div>
        <div>
          <label class="lab-label">Sample rate (Hz)</label>
          <mat-form-field appearance="outline" class="dense-field">
            <input matInput type="number" min="100" max="20000"
                   [ngModel]="store.sampleRateHz()"
                   (ngModelChange)="store.sampleRateHz.set(+$event)" />
          </mat-form-field>
        </div>
        <div>
          <label class="lab-label"
                 matTooltip="Pseudonymous identifier only. No personal data enters a prompt.">
            Subject ref
          </label>
          <mat-form-field appearance="outline" class="dense-field">
            <input matInput placeholder="S01"
                   [ngModel]="store.subjectRef()"
                   (ngModelChange)="store.subjectRef.set($event)" />
          </mat-form-field>
        </div>
      </div>
    </div>
  `,
})
export class EmgPanel {
  protected readonly store = inject(LabStore);
  protected readonly stream = inject(EmgStreamService);
  protected readonly Math = Math;

  /** Acquisition units span orders of magnitude; fixed decimals do not suit them. */
  protected num(value: number): string {
    if (!value) return '0';
    const magnitude = Math.abs(value);
    if (magnitude >= 100) return value.toFixed(0);
    if (magnitude >= 1) return value.toFixed(2);
    return value.toFixed(4);
  }

  /** Bar length relative to the loudest channel in this window. */
  protected relativeRms(value: number): number {
    const peak = Math.max(...this.store.features().map((f) => f.rms), 0);
    return peak ? Math.min(100, (value / peak) * 100) : 0;
  }

  /**
   * What the window looks like, stated the way the model is told to read it.
   *
   * Deliberately based on the flexor ratio rather than an absolute amplitude:
   * with raw converter output there is no absolute threshold that survives a
   * change of gain, electrode placement or subject.
   */
  protected interpretation(): { label: string; tone: string; hint: string } {
    const ratio = this.store.flexorRatio();
    const quiet = this.store.meanRms() < this.store.restFloor();

    if (quiet) {
      return {
        label: 'at rest',
        tone: 'bg-ink-100 text-ink-600',
        hint: "Amplitude is at the window's own floor. The correct response is "
            + "intent='no_action'.",
      };
    }
    if (ratio > 0.65) {
      return { label: 'flexor dominant · closing', tone: 'bg-pink text-white',
               hint: 'Volar group leads. Expect a closing gesture.' };
    }
    if (ratio < 0.35) {
      return { label: 'extensor dominant · opening', tone: 'bg-navy text-white',
               hint: 'Dorsal group leads. Expect an opening gesture.' };
    }
    return { label: 'co-contraction', tone: 'bg-amber text-navy',
             hint: 'Both groups active at similar levels — usually a deliberate stop.' };
  }

  protected autoRun = true;
  protected pasteText = '';
  protected readonly showPaste = signal(false);
  private readonly fileInput = viewChild<ElementRef<HTMLInputElement>>('fileInput');
  protected readonly copied = signal(false);

  constructor() {
    // Mirror live windows into the panel so the researcher always sees the
    // signal the model is actually being shown.
    effect(() => {
      const window = this.stream.lastWindow();
      if (window && this.store.liveMode()) this.store.ingestLiveWindow(window);
    });
  }

  protected rmsValues(): number[] {
    return this.store.features().map((f) => f.rms);
  }

  protected siteFor(label: string): string {
    return this.store.matrixFormat()?.sites[label] ?? label;
  }

  protected toggleLive(enabled: boolean): void {
    this.store.setLiveMode(enabled);
    if (enabled) this.reconnect();
    else this.stream.disconnect();
  }

  protected reconnect(): void {
    if (!this.store.liveMode()) return;
    this.stream.connect(crypto.randomUUID(), {
      samplingConfigurationId: this.store.selectedConfigurationId(),
      handedness: this.store.handedness(),
      autoRun: this.autoRun,
      subjectRef: this.store.subjectRef() || null,
      limitProfile: this.store.limitProfile(),
    });
  }

  protected async applyPaste(): Promise<void> {
    const ok = await this.store.loadMatrixFromText(this.pasteText);
    if (ok) {
      this.pasteText = '';
      this.showPaste.set(false);
    }
  }

  protected pickFile(): void {
    // Bound to this component's own input rather than the first one in the
    // document, which would break the moment a second file field is added.
    this.fileInput()?.nativeElement.click();
  }

  protected async onFile(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    try {
      await this.store.loadMatrixFromText(await file.text());
    } catch (error) {
      this.store.matrixError.set(
        `Could not read ${file.name}: ${(error as Error).message}`,
      );
    } finally {
      // Cleared so selecting the same file twice fires `change` again.
      input.value = '';
    }
  }

  protected async copyCsv(): Promise<void> {
    await navigator.clipboard.writeText(this.store.matrixAsCsv());
    this.copied.set(true);
    setTimeout(() => this.copied.set(false), 1500);
  }
}
