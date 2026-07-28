import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { MatTooltipModule } from '@angular/material/tooltip';

/**
 * Eight stacked EMG traces drawn as inline SVG.
 *
 * SVG rather than canvas: the window is at most a few hundred points per
 * channel, the paths are cheap, and staying declarative means the plot updates
 * from the signal graph with no imperative redraw code to keep in sync.
 */
@Component({
  selector: 'ph-emg-matrix-plot',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatTooltipModule],
  template: `
    <div class="space-y-px">
      <div class="mb-1 flex items-center justify-between text-[10px] text-ink-400">
        <span>traces scaled to the window peak for display only</span>
        <span class="lab-mono">±{{ formatRms(displayScale()) }}</span>
      </div>

      @for (trace of traces(); track trace.label) {
        <div class="flex items-center gap-2">
          <span class="lab-mono w-8 shrink-0 text-[10px] font-semibold"
                [style.color]="trace.colour">{{ trace.label }}</span>

          <svg class="h-8 flex-1 rounded bg-ink-50"
               [attr.viewBox]="'0 0 ' + width + ' ' + height"
               preserveAspectRatio="none">
            <!-- zero line -->
            <line [attr.x1]="0" [attr.y1]="height / 2"
                  [attr.x2]="width" [attr.y2]="height / 2"
                  stroke="#D6DEE6" stroke-width="1" vector-effect="non-scaling-stroke" />
            <path [attr.d]="trace.path" fill="none"
                  [attr.stroke]="trace.colour" stroke-width="1"
                  vector-effect="non-scaling-stroke" />
          </svg>

          <span class="lab-mono w-12 shrink-0 text-right text-[10px] text-ink-500"
                matTooltip="RMS in acquisition units">
            {{ formatRms(trace.rms) }}
          </span>
        </div>
      }
    </div>
  `,
})
export class EmgMatrixPlot {
  /** N x 8 matrix of normalised samples. */
  readonly samples = input.required<number[][]>();
  readonly labels = input.required<string[]>();
  /** Per-channel RMS, shown beside each trace. In acquisition units. */
  readonly rms = input<number[]>([]);

  /** Raw counts and fractional values need different precision. */
  protected formatRms(value: number): string {
    if (value === 0) return '0';
    if (value >= 100) return value.toFixed(0);
    if (value >= 1) return value.toFixed(1);
    return value.toFixed(3);
  }

  protected readonly width = 600;
  protected readonly height = 32;

  /**
   * CH1-CH4 are the volar/flexor group, CH5-CH7 the dorsal/extensor group and
   * CH8 is brachioradialis. The three-way colour split makes the flexor vs
   * extensor balance — the thing that actually decides open from close —
   * readable at a glance.
   */
  private colourFor(index: number): string {
    if (index < 4) return '#D81B60';
    if (index < 7) return '#001F3F';
    return '#FFC107';
  }

  /**
   * Display scale: the largest magnitude anywhere in the window.
   *
   * The data is raw converter output and is never rescaled — but a plot has a
   * fixed height, so it needs *some* mapping from value to pixel. Deriving it
   * from the window's own peak means a trace fills the axis regardless of the
   * acquisition gain. Using a shared peak rather than a per-channel one keeps
   * the relative amplitude between channels visible, which is the thing the
   * researcher is actually reading.
   *
   * This affects pixels only. Nothing downstream sees it.
   */
  protected readonly displayScale = computed(() => {
    let peak = 0;
    for (const row of this.samples()) {
      for (const value of row) {
        const magnitude = Math.abs(value);
        if (magnitude > peak) peak = magnitude;
      }
    }
    return peak || 1;
  });

  protected readonly traces = computed(() => {
    const matrix = this.samples();
    const labels = this.labels();
    const rmsValues = this.rms();
    const rows = matrix.length;
    const scale = this.displayScale();

    return labels.map((label, column) => {
      if (rows < 2) {
        return {
          label,
          colour: this.colourFor(column),
          rms: rmsValues[column] ?? 0,
          path: `M0 ${this.height / 2} L${this.width} ${this.height / 2}`,
        };
      }

      // Decimate to at most one point per horizontal pixel: beyond that the
      // extra vertices cost DOM weight without adding anything visible.
      const stride = Math.max(1, Math.ceil(rows / this.width));
      const points: string[] = [];
      for (let i = 0; i < rows; i += stride) {
        const x = (i / (rows - 1)) * this.width;
        // Normalised for drawing only, by the window's own peak.
        const value = Math.max(-1, Math.min(1, (matrix[i][column] ?? 0) / scale));
        const y = this.height / 2 - value * (this.height / 2 - 1);
        points.push(`${points.length === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(2)}`);
      }

      return {
        label,
        colour: this.colourFor(column),
        rms: rmsValues[column] ?? 0,
        path: points.join(' '),
      };
    });
  });
}
