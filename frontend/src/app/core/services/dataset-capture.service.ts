import { Injectable, computed, signal } from '@angular/core';

export interface DatasetCapture {
  id: string; session: string; subject_ref: string; gesture: string; command: string;
  repetition: number; captured_at: string; sample_rate_hz: number; samples: number[][];
}

@Injectable({ providedIn: 'root' })
export class DatasetCaptureService {
  readonly captures = signal<DatasetCapture[]>([]);
  readonly totalRows = computed(() => this.captures().reduce((sum, capture) => sum + capture.samples.length, 0));
  add(capture: Omit<DatasetCapture, 'id' | 'captured_at'>): void {
    this.captures.update(rows => [...rows, { ...capture, id: crypto.randomUUID(), captured_at: new Date().toISOString() }]);
  }
  clear(): void { this.captures.set([]); }
  countFor(gesture: string): number { return this.captures().filter(row => row.gesture === gesture).length; }
  exportJson(): void { this.download(JSON.stringify({ format: 'phlab-handi-emg-v1', captures: this.captures() }, null, 2), 'json', 'application/json'); }
  exportCsv(): void {
    const header = ['session','subject_ref','gesture','command','repetition','captured_at','sample_rate_hz','sample_index','CH1','CH2','CH3','CH4','CH5','CH6','CH7','CH8'];
    const rows = this.captures().flatMap(c => c.samples.map((sample, index) => [c.session,c.subject_ref,c.gesture,c.command,c.repetition,c.captured_at,c.sample_rate_hz,index,...sample]));
    const csv = [header, ...rows].map(row => row.map(value => `"${String(value).replaceAll('"', '""')}"`).join(',')).join('\n');
    this.download(csv, 'csv', 'text/csv');
  }
  private download(content: string, extension: string, type: string): void {
    const url = URL.createObjectURL(new Blob([content], { type })); const anchor = document.createElement('a');
    anchor.href = url; anchor.download = `handi-emg-${new Date().toISOString().slice(0, 10)}.${extension}`; anchor.click(); URL.revokeObjectURL(url);
  }
}
