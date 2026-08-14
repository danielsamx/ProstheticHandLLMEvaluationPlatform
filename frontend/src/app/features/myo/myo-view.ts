import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '@env/environment';
import { EmgWindow } from '@core/models/emg.model';
import { LabStore } from '@core/services/lab.store';
import { LanguageService, TranslatePipe } from '@core/services/language.service';
import { MyoCaptureService } from '@core/services/myo-capture.service';

@Component({ standalone: true, selector: 'ph-myo-view', imports: [FormsModule, RouterLink, TranslatePipe], changeDetection: ChangeDetectionStrategy.OnPush,
template: `<main class="h-full overflow-auto bg-ink-50 p-6"><div class="mx-auto max-w-4xl">
  <div class="flex items-end justify-between gap-4"><div><h2 class="text-xl font-semibold text-navy">{{ 'Live Myo acquisition' | tr }}</h2>
    <p class="mt-1 text-sm text-ink-500">8-channel EMG streaming and preprocessing</p></div>
    <a routerLink="/dataset" class="rounded border border-navy px-3 py-2 text-xs font-semibold text-navy">{{ 'Dataset capture' | tr }}</a></div>
  <div class="mt-5 grid gap-4 md:grid-cols-2">
    <section class="rounded border border-ink-200 bg-white p-4">
      <p class="text-sm">{{ 'Status' | tr }}: <strong>{{ myo.state() }}</strong> · {{ myo.samples().length }} {{ 'samples' | tr }}</p>
      <div class="mt-4 flex gap-2"><button class="rounded bg-navy px-3 py-2 text-white" (click)="connect()">{{ 'Connect Myo' | tr }}</button>
      <button class="rounded border px-3 py-2" (click)="myo.clear()">{{ 'Clear' | tr }}</button></div>
      @if (myo.error()) { <p class="mt-3 text-sm text-pink">{{ myo.error() }}</p> }
    </section>
    <section class="rounded border border-ink-200 bg-white p-4">
      <label class="lab-label">{{ 'Mains frequency' | tr }}</label><select class="mt-1 w-full rounded border p-2" [(ngModel)]="notch"><option [ngValue]="50">50 Hz</option><option [ngValue]="60">60 Hz</option></select>
      <label class="lab-label mt-3 block">{{ 'Normalisation' | tr }}</label><select class="mt-1 w-full rounded border p-2" [(ngModel)]="normalisation"><option value="max_abs">{{ 'Maximum absolute' | tr }}</option><option value="zscore">Z-score</option><option value="none">{{ 'None' | tr }}</option></select>
      <label class="mt-3 flex items-center gap-2 text-sm"><input type="checkbox" [(ngModel)]="rectify" /> {{ 'Rectify signal' | tr }}</label>
      <button class="mt-4 w-full rounded bg-navy px-3 py-2 text-white" [disabled]="myo.samples().length < 32 || busy()" (click)="prepare()">{{ 'Preprocess and send to laboratory' | tr }}</button>
    </section>
  </div>
  <p class="mt-4 text-xs text-ink-500">Raw data is preserved. The laboratory receives a copy with DC removal, a notch filter, a 20–90 Hz band-pass filter, and the selected normalisation.</p>
</div></main>` })
export class MyoView {
  protected readonly myo = inject(MyoCaptureService); private readonly http = inject(HttpClient);
  private readonly store = inject(LabStore); private readonly router = inject(Router); protected readonly language = inject(LanguageService);
  protected notch = 50; protected normalisation = 'max_abs'; protected rectify = false; protected readonly busy = signal(false);
  protected async connect(): Promise<void> { await this.myo.connect(); }
  protected async prepare(): Promise<void> {
    this.busy.set(true);
    try {
      const result = await firstValueFrom(this.http.post<{ processed_window: EmgWindow }>(`${environment.apiBase}/myo/preprocess`, {
        samples: this.myo.samples(), sample_rate_hz: 200, notch_hz: this.notch, normalisation: this.normalisation,
        rectify: this.rectify, remove_dc: true, bandpass_low_hz: 20, bandpass_high_hz: 90, channel_order: [0,1,2,3,4,5,6,7],
      }));
      this.store.sampleRateHz.set(200); this.store.setMatrix(result.processed_window.samples, 'live'); await this.router.navigateByUrl('/lab');
    } finally { this.busy.set(false); }
  }
}
