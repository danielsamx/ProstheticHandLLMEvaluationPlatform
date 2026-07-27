import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

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
  template: `
    <div class="space-y-px">
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

          <span class="lab-mono w-11 shrink-0 text-right text-[10px] text-ink-500">
            {{ trace.rms.toFixed(3) }}
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
  /** Per-channel RMS, shown beside each trace. */
  readonly rms = input<number[]>([]);

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

  protected readonly traces = computed(() => {
    const matrix = this.samples();
    const labels = this.labels();
    const rmsValues = this.rms();
    const rows = matrix.length;

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
        const value = Math.max(-1, Math.min(1, matrix[i][column] ?? 0));
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
