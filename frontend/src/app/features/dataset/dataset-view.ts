import { ChangeDetectionStrategy, Component, computed, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { GestureSpec } from '@core/models/hand.model';
import { DatasetCaptureService } from '@core/services/dataset-capture.service';
import { LabStore } from '@core/services/lab.store';
import { LanguageService, TranslatePipe } from '@core/services/language.service';
import { MyoCaptureService } from '@core/services/myo-capture.service';

@Component({
  standalone: true, selector: 'ph-dataset-view', changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatIconModule, TranslatePipe],
  template: `
    <main class="h-full overflow-auto bg-ink-50 p-4 sm:p-6">
      <div class="mx-auto max-w-6xl">
        <div class="flex items-end justify-between gap-4">
          <div><h2 class="text-xl font-semibold text-navy">{{ 'Dataset capture' | tr }}</h2>
            <p class="mt-1 text-sm text-ink-500">HANDi EPN V3 · 8-channel labelled EMG windows</p></div>
          <div class="text-right text-xs text-ink-500"><strong class="text-navy">{{ dataset.captures().length }}</strong> {{ 'Captured' | tr }} · {{ dataset.totalRows() }} rows</div>
        </div>

        <div class="mt-5 grid gap-4 lg:grid-cols-[340px_1fr]">
          <section class="rounded border border-ink-200 bg-white p-4">
            <h3 class="text-sm font-semibold text-navy">{{ 'Session setup' | tr }}</h3>
            <label class="lab-label mt-4 block">{{ 'Session name' | tr }}</label>
            <input class="mt-1 w-full rounded border p-2 text-sm" [(ngModel)]="sessionName" />
            <label class="lab-label mt-3 block">{{ 'Subject reference' | tr }}</label>
            <input class="mt-1 w-full rounded border p-2 text-sm" [(ngModel)]="subjectRef" placeholder="P001" />
            <div class="mt-3 grid grid-cols-2 gap-3">
              <div><label class="lab-label block">{{ 'Gesture count' | tr }}</label><input type="number" min="1" [max]="gestures().length" class="mt-1 w-full rounded border p-2" [ngModel]="selectedNames().length" (ngModelChange)="setGestureCount($event)" /></div>
              <div><label class="lab-label block">{{ 'Samples per gesture' | tr }}</label><input type="number" min="1" max="100" class="mt-1 w-full rounded border p-2" [(ngModel)]="samplesPerGesture" /></div>
              <div><label class="lab-label block">{{ 'Rows per sample' | tr }}</label><input type="number" min="32" max="2000" step="16" class="mt-1 w-full rounded border p-2" [(ngModel)]="rowsPerSample" /></div>
              <div><label class="lab-label block">{{ 'Sample rate' | tr }} (Hz)</label><input type="number" min="50" max="2000" class="mt-1 w-full rounded border p-2" [(ngModel)]="sampleRateHz" /></div>
            </div>
            <div class="mt-4 flex gap-2">
              <button class="flex flex-1 items-center justify-center gap-2 rounded bg-navy px-3 py-2 text-xs text-white" (click)="connect()"><mat-icon class="!text-[17px]">sensors</mat-icon>{{ 'Connect Myo' | tr }}</button>
              <button class="grid h-9 w-9 place-items-center rounded border" (click)="myo.clear()" [title]="language.text('Clear')"><mat-icon>delete_sweep</mat-icon></button>
            </div>
            <p class="mt-3 text-xs text-ink-500">{{ 'Status' | tr }}: <strong>{{ myo.state() }}</strong> · {{ myo.samples().length }} {{ 'samples' | tr }}</p>
          </section>

          <section class="rounded border border-ink-200 bg-white">
            <div class="flex items-center justify-between border-b border-ink-200 p-4">
              <div><h3 class="text-sm font-semibold text-navy">{{ 'Gestures' | tr }}</h3><p class="text-[11px] text-ink-500">Physical poses defined by the HANDi EPN V3 manual and firmware</p></div>
              <button class="text-xs font-semibold text-navy underline" (click)="toggleAll()">{{ 'Select all' | tr }}</button>
            </div>
            <div class="grid gap-px bg-ink-200 sm:grid-cols-2">
              @for (gesture of gestures(); track gesture.command) {
                <label class="flex min-h-20 cursor-pointer items-center gap-3 bg-white p-3">
                  <input type="checkbox" [checked]="isSelected(gesture.name)" (change)="toggleGesture(gesture.name)" />
                  <span class="grid h-9 w-9 shrink-0 place-items-center rounded bg-ink-50 font-mono text-sm font-bold text-pink">{{ gesture.command }}</span>
                  <span class="min-w-0 flex-1"><strong class="block text-xs text-navy">{{ gesture.name.replaceAll('_', ' ') }}</strong><span class="line-clamp-2 text-[10px] text-ink-500">{{ gesture.description }}</span></span>
                  <span class="text-xs font-semibold" [class.text-navy]="count(gesture.name) >= samplesPerGesture" [class.text-pink]="count(gesture.name) < samplesPerGesture">{{ count(gesture.name) }}/{{ samplesPerGesture }}</span>
                </label>
              }
            </div>
          </section>
        </div>

        <section class="mt-4 flex flex-wrap items-center gap-3 rounded border border-ink-200 bg-white p-4">
          @if (currentGesture(); as gesture) {
            <div class="mr-auto"><span class="lab-label">{{ 'Current gesture' | tr }}</span><p class="text-lg font-semibold text-navy">{{ gesture.name.replaceAll('_', ' ') }} <span class="font-mono text-pink">({{ gesture.command }})</span></p></div>
            <button class="flex h-11 items-center gap-2 rounded bg-pink px-5 text-sm font-semibold text-white" [disabled]="!canCapture()" (click)="capture()"><mat-icon>fiber_manual_record</mat-icon>{{ 'Capture sample' | tr }}</button>
          } @else { <p class="mr-auto text-sm font-semibold text-navy">{{ 'Session complete' | tr }}</p> }
          <button class="flex h-10 items-center gap-2 rounded border px-3 text-xs" [disabled]="!dataset.captures().length" (click)="dataset.exportCsv()"><mat-icon>table_view</mat-icon>{{ 'Export CSV' | tr }}</button>
          <button class="flex h-10 items-center gap-2 rounded border px-3 text-xs" [disabled]="!dataset.captures().length" (click)="dataset.exportJson()"><mat-icon>data_object</mat-icon>{{ 'Export JSON' | tr }}</button>
          <button class="grid h-10 w-10 place-items-center text-pink" [disabled]="!dataset.captures().length" (click)="dataset.clear()" [title]="language.text('Clear session')"><mat-icon>delete</mat-icon></button>
          @if (message()) { <p class="w-full text-xs text-pink">{{ message() }}</p> }
        </section>
      </div>
    </main>`,
})
export class DatasetView {
  protected readonly store = inject(LabStore); protected readonly myo = inject(MyoCaptureService);
  protected readonly dataset = inject(DatasetCaptureService); protected readonly language = inject(LanguageService);
  protected sessionName = `HANDi-${new Date().toISOString().slice(0, 10)}`; protected subjectRef = '';
  protected samplesPerGesture = 10; protected rowsPerSample = 200; protected sampleRateHz = 200;
  protected readonly selectedNames = signal<string[]>([]); protected readonly message = signal('');
  protected readonly gestures = computed(() => (this.store.handSpec()?.gestures ?? []).filter(gesture => gesture.pose !== null));
  protected readonly currentGesture = computed(() => this.gestures().find(g => this.isSelected(g.name) && this.count(g.name) < this.samplesPerGesture) ?? null);
  protected readonly canCapture = computed(() => this.myo.state() === 'streaming' && this.myo.samples().length >= this.rowsPerSample && !!this.currentGesture());
  constructor() {
    effect(() => {
      const gestures = this.gestures();
      if (gestures.length && !this.selectedNames().length) this.selectedNames.set(gestures.map(gesture => gesture.name));
    }, { allowSignalWrites: true });
  }
  protected async connect(): Promise<void> { this.message.set(''); try { await this.myo.connect(); } catch (error) { this.message.set(error instanceof Error ? error.message : String(error)); } }
  protected isSelected(name: string): boolean { return this.selectedNames().includes(name); }
  protected toggleGesture(name: string): void { this.selectedNames.update(values => values.includes(name) ? values.filter(value => value !== name) : [...values, name]); }
  protected setGestureCount(value: number): void {
    const count = Math.max(1, Math.min(this.gestures().length, Math.trunc(Number(value) || 1)));
    this.selectedNames.set(this.gestures().slice(0, count).map(gesture => gesture.name));
  }
  protected toggleAll(): void { this.selectedNames.set(this.selectedNames().length === this.gestures().length ? [] : this.gestures().map(g => g.name)); }
  protected count(name: string): number { return this.dataset.countFor(name); }
  protected capture(): void {
    const gesture = this.currentGesture(); if (!gesture) return;
    if (this.myo.state() !== 'streaming') { this.message.set(this.language.text('Connect Myo before capturing.')); return; }
    const samples = this.myo.samples().slice(-this.rowsPerSample).map(row => [...row]);
    if (samples.length < this.rowsPerSample) { this.message.set(this.language.text('Wait until enough signal rows are available.')); return; }
    this.dataset.add({ session: this.sessionName, subject_ref: this.subjectRef, gesture: gesture.name, command: gesture.command, repetition: this.count(gesture.name) + 1, sample_rate_hz: this.sampleRateHz, samples });
    this.message.set(''); this.myo.clear();
  }
}
