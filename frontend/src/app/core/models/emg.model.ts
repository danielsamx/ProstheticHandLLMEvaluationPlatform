export type EmgSourceMode = 'manual' | 'live' | 'dataset' | 'synthetic';

/** Time-domain descriptors derived by the backend from the sample matrix. */
export interface EmgChannelFeatures {
  label: string;
  rms: number;
  mav: number;
  zc: number;
  ssc: number;
  wl: number;
  min: number;
  max: number;
  variance: number;
}

/**
 * One analysis window.
 *
 * `samples` is the stimulus: N rows (time steps) x 8 columns (CH1..CH8),
 * amplitudes normalised to [-1.0, 1.0]. `sample_count`, `window_ms` and
 * `features` are computed server-side and present on responses only — the
 * backend strips them on input, so a fetched window can be posted straight back.
 */
export interface EmgWindow {
  samples: number[][];
  source_mode: EmgSourceMode;
  sample_rate_hz: number;
  captured_at?: string;
  ground_truth_gesture?: string | null;
  notes?: string | null;

  readonly sample_count?: number;
  readonly window_ms?: number;
  readonly features?: EmgChannelFeatures[];
}

export interface EmgMatrixFormat {
  channel_count: number;
  channels: string[];
  sites: Record<string, string>;
  layout: string;
  amplitude_min: number;
  amplitude_max: number;
  min_rows: number;
  max_rows: number;
}

export type NormalisationMode = 'none' | 'full_scale' | 'peak';

/** What the backend did to the amplitudes, and whether comparison is safe. */
export interface MatrixParseResponse {
  window: EmgWindow;
  normalisation: NormalisationMode;
  observed_peak: number;
  divisor: number;
  inferred_full_scale: boolean;
  warnings: string[];
}

export const EMG_CHANNEL_COUNT = 8;

/** Strip server-computed fields before submitting a window. */
export function toWindowPayload(window: EmgWindow): EmgWindow {
  return {
    samples: window.samples,
    source_mode: window.source_mode,
    sample_rate_hz: window.sample_rate_hz,
    ground_truth_gesture: window.ground_truth_gesture ?? null,
    notes: window.notes ?? null,
  };
}

/** Client-side descriptors, so the panel can preview a pasted matrix offline. */
export function computeFeatures(samples: number[][], labels: string[]): EmgChannelFeatures[] {
  const rows = samples.length;
  return labels.map((label, column) => {
    if (!rows) {
      return { label, rms: 0, mav: 0, zc: 0, ssc: 0, wl: 0, min: 0, max: 0, variance: 0 };
    }
    const signal = samples.map((row) => row[column] ?? 0);

    let sumSquares = 0;
    let sumAbs = 0;
    let min = Infinity;
    let max = -Infinity;
    for (const value of signal) {
      sumSquares += value * value;
      sumAbs += Math.abs(value);
      if (value < min) min = value;
      if (value > max) max = value;
    }

    // 0.01 deadband, matching the backend: without it, noise around zero
    // inflates both counts by an order of magnitude.
    let zc = 0;
    let wl = 0;
    for (let i = 1; i < rows; i++) {
      const previous = signal[i - 1];
      const current = signal[i];
      if (previous * current < 0 && Math.abs(previous - current) >= 0.01) zc++;
      wl += Math.abs(current - previous);
    }

    let ssc = 0;
    for (let i = 1; i < rows - 1; i++) {
      const a = signal[i - 1];
      const b = signal[i];
      const c = signal[i + 1];
      if ((b - a) * (b - c) > 0 && (Math.abs(b - a) >= 0.01 || Math.abs(b - c) >= 0.01)) ssc++;
    }

    const mean = sumAbs === 0 ? 0 : signal.reduce((s, v) => s + v, 0) / rows;
    const variance = rows > 1
      ? signal.reduce((s, v) => s + (v - mean) ** 2, 0) / (rows - 1)
      : 0;

    return {
      label,
      rms: Math.sqrt(sumSquares / rows),
      mav: sumAbs / rows,
      zc,
      ssc,
      wl: rows > 1 ? wl / (rows - 1) : 0,
      min: min === Infinity ? 0 : min,
      max: max === -Infinity ? 0 : max,
      variance,
    };
  });
}
