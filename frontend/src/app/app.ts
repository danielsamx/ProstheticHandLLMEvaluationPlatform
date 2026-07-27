import { Component, ChangeDetectionStrategy, OnInit, inject, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

import { LabStore } from '@core/services/lab.store';
import { SimulatorBridgeService } from '@core/services/simulator-bridge.service';
import { LabPanel } from '@features/lab/lab-panel';
import { SimulatorPanel } from '@features/simulator/simulator-panel';

@Component({
  selector: 'ph-root',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, MatTooltipModule, LabPanel, SimulatorPanel],
  template: `
    <div class="flex h-screen w-screen flex-col bg-white text-navy">
      <!-- ── Top bar ─────────────────────────────────────────────────────── -->
      <header class="flex h-14 shrink-0 items-center justify-between bg-navy px-4 text-white">
        <div class="flex items-center gap-3">
          <!--
            The asset is a raster with a white background, not a transparent
            mark, so it sits in a white pill rather than directly on the navy
            bar where its own background would show as a grey rectangle.
          -->
          @if (logoAvailable()) {
            <!--
              width/height carry the file's intrinsic 250x96, so the browser
              reserves the correct box and the aspect ratio is never guessed.
              The earlier 120x28 was a different ratio and squashed the mark.
              The h-9 w-auto pair scales it down without distortion.
            -->
            <img src="assets/logo.webp"
                 alt="Escuela Politécnica Nacional · Facultad de Ingeniería de Sistemas"
                 class="h-9 w-auto rounded bg-white px-2 py-1"
                 width="250" height="96"
                 (error)="logoAvailable.set(false)" />

            <span class="h-7 w-px bg-white/20"></span>
          }

          <mat-icon class="text-amber">precision_manufacturing</mat-icon>
          <div class="leading-tight">
            <h1 class="text-sm font-semibold tracking-tight">
              Prosthetic Hand LLM Evaluation Platform
            </h1>
            <p class="text-[10px] uppercase tracking-widest text-white/60">
              HANDi EPN V3 · EMG matrix → validated control commands
            </p>
          </div>
        </div>

        <div class="flex items-center gap-3 text-[11px]">
          @if (store.handSpec(); as spec) {
            <span class="lab-chip bg-white/10 text-white"
                  matTooltip="Independently commanded degrees of freedom">
              {{ spec.driven_dof }} DOF
            </span>
            <span class="lab-chip bg-white/10 text-white"
                  matTooltip="Rotary potentiometers on the physical hand">
              {{ spec.potentiometer_count }} POT
            </span>
            <span class="lab-chip bg-white/10 text-white" matTooltip="Fingertip force sensors">
              {{ spec.fsr_count }} FSR
            </span>
          }

          @if (store.lmStudio(); as lm) {
            <span class="lab-chip"
                  [class]="lm.reachable ? 'bg-amber text-navy' : 'bg-pink text-white'"
                  [matTooltip]="lm.reachable
                    ? lm.models.length + ' model(s) loaded at ' + lm.api_base
                    : 'LM Studio unreachable at ' + lm.api_base">
              <mat-icon class="!h-3.5 !w-3.5 !text-[13px]">
                {{ lm.reachable ? 'dns' : 'cloud_off' }}
              </mat-icon>
              LM Studio
            </span>
          }

          <span class="lab-chip"
                [class]="bridge.state() === 'open' ? 'bg-amber text-navy' : 'bg-white/10 text-white'"
                matTooltip="Simulator movement feed">
            <mat-icon class="!h-3.5 !w-3.5 !text-[13px]">sensors</mat-icon>
            {{ bridge.state() }}
          </span>
        </div>
      </header>

      <!-- ── Exact 50 / 50 split ─────────────────────────────────────────── -->
      <main class="grid min-h-0 flex-1 grid-cols-2">
        <section class="min-h-0 overflow-hidden border-r border-ink-200">
          <ph-lab-panel />
        </section>
        <section class="min-h-0 overflow-hidden">
          <ph-simulator-panel />
        </section>
      </main>
    </div>
  `,
})
export class App implements OnInit {
  protected readonly store = inject(LabStore);
  protected readonly bridge = inject(SimulatorBridgeService);

  /** A broken-image glyph in the header reads worse than no logo at all. */
  protected readonly logoAvailable = signal(true);

  ngOnInit(): void {
    void this.store.bootstrap();
  }
}
