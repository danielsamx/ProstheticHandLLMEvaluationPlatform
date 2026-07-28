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
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatTooltipModule } from '@angular/material/tooltip';

import { EmgStreamService } from '@core/services/emg-stream.service';
import { LabStore } from '@core/services/lab.store';
import { EmgMatrixPlot } from './emg-matrix-plot';

/**
 * The EMG stimulus: an N x 8 matrix of raw converter output.
 *
 * Three ways in — import a file, paste rows, or stream live — because a matrix
 * is not something anyone types by hand. All three carry real acquisition; the
 * synthetic generator was removed from this row because a run against
 * synthesised signals tests the platform rather than the model, and sitting
 * first it read as the normal way to load data.
 *
 * The traces below are a read-out, not an editor. They are drawn from the
 * matrix, so allowing them to be edited would permit a window whose picture
 * disagrees with its numbers.
 */
@Component({
  selector: 'ph-emg-panel',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    FormsModule, MatButtonModule, MatButtonToggleModule, MatFormFieldModule,
    MatIconModule, MatInputModule, MatSlideToggleModule,
    MatTooltipModule,
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

      <!--
        What the model is shown, and what it is judged against.

        These two belong on the same line because they are the two halves of
        one experimental setup: the input condition and the answer key. A run
        is only a measurement when both are decided.
      -->
      <div class="flex flex-wrap items-end justify-between gap-x-3 gap-y-2">
        <div style="display: flex; flex-direction: column;">
          <label class="lab-label">Dynamic prompt</label>
          <mat-button-toggle-group class="dense-toggle-group"
                                  [ngModel]="store.dynamicContent()"
                                  (ngModelChange)="store.setDynamicContent($event)"
                                  style="height: 38px; min-height: 38px; display: inline-flex; flex-direction: row; flex-wrap: nowrap; width: auto; align-items: center; border-radius: 6px; overflow: hidden;"
                                  hideSingleSelectionIndicator>
            <mat-button-toggle value="matrix"
                              matTooltip="The raw N × 8 sample matrix only..."
                              [matTooltipPosition]="'above'"
                              style="height: 38px; min-height: 38px; display: inline-flex; flex: 0 0 auto; align-items: center; justify-content: center; padding: 0 16px; border: none; border-radius: 0; font-size: 13px;">
              <span style="line-height: 38px; display: flex; align-items: center; height: 100%; font-size: 13px;">Matrix</span>
            </mat-button-toggle>
            <mat-button-toggle value="features"
                              matTooltip="The derived per-channel descriptors only..."
                              [matTooltipPosition]="'above'"
                              style="height: 38px; min-height: 38px; display: inline-flex; flex: 0 0 auto; align-items: center; justify-content: center; padding: 0 16px; border: none; border-radius: 0; font-size: 13px;">
              <span style="line-height: 38px; display: flex; align-items: center; height: 100%; font-size: 13px;">Features</span>
            </mat-button-toggle>
            <mat-button-toggle value="both"
                              matTooltip="Matrix first, then the descriptors..."
                              [matTooltipPosition]="'above'"
                              style="height: 38px; min-height: 38px; display: inline-flex; flex: 0 0 auto; align-items: center; justify-content: center; padding: 0 16px; border: none; border-radius: 0; font-size: 13px;">
              <span style="line-height: 38px; display: flex; align-items: center; height: 100%; font-size: 13px;">Both</span>
            </mat-button-toggle>
          </mat-button-toggle-group>
        </div>

        <div class="min-w-[170px] flex-1">
          <label class="lab-label"
                 matTooltip="The command this window should produce. Stored with the run and compared against the model's answer. It is never placed in the prompt.">
            Expected serial command
          </label>
          <mat-form-field appearance="outline" class="dense-field w-full">
            <input matInput placeholder="e.g. C  or  A320,B180"
                   class="lab-mono"
                   [ngModel]="store.expectedCommand()"
                   (ngModelChange)="store.expectedCommand.set($event)" />
          </mat-form-field>
        </div>

        <!--
          The row budget only appears when the matrix is actually being sent and
          the window is long enough for the choice to matter. Showing it always
          would put a knob on screen that most runs never need to touch.
        -->
        @if (store.dynamicContent() !== 'features'
            && (store.sampleCount() > 64 || store.matrixMaxRows() !== null)) {
          <div>
            <label class="lab-label"
                   matTooltip="Blank sends every row. A cap decimates across the whole window rather than truncating it, so the excerpt still spans the movement.">
              Rows sent
            </label>
            <!--
              A number input fires on every keystroke, so binding it straight to
              the run would mean typing "128" briefly requested 1 row and then
              12. Hence a draft.

              But a draft that only commits on a button press is its own trap:
              type 32, press Run, and the run silently uses the old value. So it
              also commits on blur and on Enter. The button stays because it is
              discoverable and gives the change an explicit moment — it is no
              longer the *only* way to apply it.
            -->
            <div class="flex items-center gap-1">
              <mat-form-field appearance="outline" class="dense-field !w-24">
                <input matInput type="number" min="1" [max]="store.sampleCount()"
                       [placeholder]="store.sampleCount() + ' (all)'"
                       [ngModel]="rowsDraft()"
                       (ngModelChange)="rowsDraft.set($event === null || $event === '' ? null : +$event)"
                       (blur)="applyRows()"
                       (keyup.enter)="applyRows()" />
              </mat-form-field>
              <button mat-flat-button color="primary"
                      class="!mb-0.5 !h-[34px] !min-w-0 !px-2.5 !text-[11px]"
                      [disabled]="!rowsChanged()"
                      [matTooltip]="rowsChanged()
                        ? 'Apply this row count and re-render the preview'
                        : 'Already applied'"
                      (click)="applyRows()">
                Apply
              </button>
            </div>
          </div>
        }
      </div>

      <!--
        What is actually in effect, stated by the server rather than re-derived
        here. If the panel computed this itself it could disagree with the
        prompt that gets sent, which is precisely the confusion this line exists
        to end.
      -->
      @if (store.promptPreview(); as preview) {
        <div class="flex items-center gap-1.5 text-[11px]"
             [class]="preview.matrix_rows_sent < store.sampleCount()
               ? 'text-amber' : 'text-ink-500'">
          <mat-icon class="!h-3.5 !w-3.5 !text-[13px]">
            {{ preview.dynamic_content === 'features' ? 'functions' : 'table_rows' }}
          </mat-icon>
          @if (preview.dynamic_content === 'features') {
            The prompt carries the derived descriptors only — no matrix rows.
          } @else if (preview.matrix_rows_sent >= store.sampleCount()) {
            The prompt carries all {{ store.sampleCount() }} rows.
          } @else {
            The prompt carries {{ preview.matrix_rows_sent }} of
            {{ store.sampleCount() }} rows, evenly spaced across the window.
          }
        </div>
      }

      <!-- ── Traces ────────────────────────────────────────────────────── -->
      <ph-emg-matrix-plot
        [samples]="store.matrix()"
        [labels]="store.channelLabels"
        [rms]="rmsValues()" />

      <!--
        ── Sources ─────────────────────────────────────────────────────────

        Four actions, each taking a quarter of the row. A grid rather than a
        flex row because the buttons carry labels of very different lengths,
        and left to themselves they sized to their text — which made the row
        read as an arbitrary ranking of importance rather than four equal ways
        in.

        The synthetic-window picker is gone. It loaded generated signals with a
        known answer, which is useful for testing the platform but is not real
        acquisition, and sitting first in this row it read as the primary way to
        load data. Runs against synthesised EMG are not evidence about the
        model. The generator is still there behind /emg/synthetic for anyone
        checking the pipeline itself.
      -->
      @if (!store.liveMode()) {
        <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <button mat-stroked-button class="!min-h-0 !py-0 !text-[11px]"
                  matTooltip="Paste rows directly: CSV, TSV, whitespace or JSON."
                  (click)="showPaste.set(!showPaste())">
            <mat-icon class="!h-4 !w-4 !text-[16px]">content_paste</mat-icon>
            {{ showPaste() ? 'Hide paste' : 'Paste matrix' }}
          </button>

          <button mat-stroked-button class="!min-h-0 !py-0 !text-[11px]"
                  matTooltip="Load an acquisition file. A CH0…CH7 or CH1…CH8 header is detected and skipped."
                  (click)="pickFile()">
            <mat-icon class="!h-4 !w-4 !text-[16px]">upload_file</mat-icon> Import CSV
          </button>

          <button mat-stroked-button class="!min-h-0 !py-0 !text-[11px]"
                  matTooltip="Copy the current window as CSV."
                  (click)="copyCsv()">
            <mat-icon class="!h-4 !w-4 !text-[16px]">download</mat-icon>
            {{ copied() ? 'Copied' : 'Copy CSV' }}
          </button>

          <button mat-stroked-button class="!min-h-0 !py-0 !text-[11px]"
                  matTooltip="Discard the loaded window."
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

  /**
   * Draft row cap, committed by Apply rather than on every keystroke.
   *
   * Seeded from the store so the field opens showing what is actually in
   * effect, and compared against it so the button can say whether there is
   * anything to apply.
   */
  protected readonly rowsDraft = signal<number | null>(this.store.matrixMaxRows());

  protected rowsChanged(): boolean {
    return this.rowsDraft() !== this.store.matrixMaxRows();
  }

  protected applyRows(): void {
    const value = this.rowsDraft();
    // A cap at or above the window length is not a cap. Storing it as null
    // keeps one meaning for "everything" instead of two that behave alike but
    // record differently.
    const capped = value === null || value >= this.store.sampleCount() ? null : Math.max(1, value);
    this.rowsDraft.set(capped);
    void this.store.setMatrixMaxRows(capped);
  }

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
