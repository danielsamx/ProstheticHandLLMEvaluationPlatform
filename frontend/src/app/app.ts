import { Component, ChangeDetectionStrategy, OnInit, inject, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { LabStore } from '@core/services/lab.store';
import { SimulatorBridgeService } from '@core/services/simulator-bridge.service';

@Component({
  selector: 'ph-root',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, MatTooltipModule, RouterLink, RouterLinkActive, RouterOutlet],
  template: `
    <div class="flex h-screen w-screen flex-col bg-white text-navy">
      <!--
        TopBar.
        Height steps with the viewport so the logo can grow without crowding
        the status chips: 64px on phones, 76px on tablets, 88px on desktop.
        The bar is a grid rather than a flex row so the brand block cannot be
        squeezed by the chips when they wrap.
      -->
      <header
        class="grid h-16 shrink-0 grid-cols-[auto_1fr] items-center gap-3
               bg-navy px-3 text-white sm:h-[76px] sm:gap-4 sm:px-5 lg:h-22 lg:px-6"
      >
        <!-- Brand -->
        <div class="flex min-w-0 items-center gap-3 sm:gap-4">
          @if (logoAvailable()) {
            <!--
              The asset is a 250x96 raster with a white background, not a
              transparent mark, so it sits in a white plate rather than directly
              on the navy where its own background would show as a grey block.

              width/height carry the intrinsic pixels so the browser reserves
              the correct box and never guesses the ratio; only the height is
              constrained, leaving w-auto to preserve 250:96 exactly. At the
              desktop step the plate renders it at 1:1, so no upscaling occurs
              and the original resolution is what reaches the screen.
            -->
            <img
              src="assets/logo.png"
              alt="Escuela Politécnica Nacional · Facultad de Ingeniería de Sistemas"
              width="250"
              height="96"
              decoding="async"
              class="h-10 w-auto shrink-0 rounded-md bg-transparent shadow-sm
                     sm:h-14 sm:p-2 lg:h-16"
              (error)="logoAvailable.set(false)"
            />
          }

          <span class="hidden h-10 w-px bg-white/20 sm:block lg:h-12"></span>

          <div class="min-w-0 leading-tight">
            <h1 class="truncate text-sm font-semibold tracking-tight sm:text-base lg:text-lg">
              <span class="sm:hidden">Prosthetic Hand LLM Lab</span>
              <span class="hidden sm:inline">Prosthetic Hand LLM Evaluation Platform</span>
            </h1>
            <p class="hidden truncate text-[10px] uppercase tracking-widest text-white/60 sm:block lg:text-[11px]">
              HANDi EPN V3 · EMG matrix → validated control commands
            </p>
          </div>
        </div>

        <!--
          Navigation and status share the right-hand column. The links carry
          icons so they survive the narrow breakpoint, where the labels drop.
        -->
        <div class="flex flex-wrap items-center justify-end gap-1.5 text-[11px] sm:gap-2">
          <nav class="mr-1 flex overflow-hidden rounded-full bg-white/10">
            @for (link of navigation; track link.path) {
              <a [routerLink]="link.path"
                 routerLinkActive="!bg-white !text-navy"
                 class="flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-semibold text-white/80 transition-colors hover:text-white"
                 [matTooltip]="link.tooltip">
                <mat-icon class="!h-4 !w-4 !text-[16px]">{{ link.icon }}</mat-icon>
                <span class="hidden lg:inline">{{ link.label }}</span>
              </a>
            }
          </nav>

          <span class="hidden h-5 w-px bg-white/20 sm:block"></span>

          @if (store.handSpec(); as spec) {
            <span class="lab-chip hidden bg-white/10 text-white lg:inline-flex"
                  matTooltip="Independently commanded degrees of freedom">
              {{ spec.driven_dof }} DOF
            </span>
            <span class="lab-chip hidden bg-white/10 text-white xl:inline-flex"
                  matTooltip="Rotary potentiometers on the physical hand">
              {{ spec.potentiometer_count }} POT
            </span>
            <span class="lab-chip hidden bg-white/10 text-white xl:inline-flex"
                  matTooltip="Fingertip force sensors">
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
              <span class="hidden sm:inline">LM Studio</span>
            </span>
          }

          <span class="lab-chip"
                [class]="bridge.state() === 'open' ? 'bg-amber text-navy' : 'bg-white/10 text-white'"
                matTooltip="Simulator movement feed">
            <mat-icon class="!h-3.5 !w-3.5 !text-[13px]">sensors</mat-icon>
            <span class="hidden md:inline">{{ bridge.state() }}</span>
          </span>
        </div>
      </header>

      <main class="min-h-0 flex-1">
        <router-outlet />
      </main>
    </div>
  `,
})
export class App implements OnInit {
  protected readonly store = inject(LabStore);
  protected readonly bridge = inject(SimulatorBridgeService);

  /** A broken-image glyph in the header reads worse than no logo at all. */
  protected readonly logoAvailable = signal(true);

  protected readonly navigation = [
    {
      path: '/lab',
      label: 'Laboratory',
      icon: 'science',
      tooltip: 'Configure and run one experiment',
    },
    {
      path: '/dashboard',
      label: 'Dashboard',
      icon: 'insights',
      tooltip: 'The accumulated experimental record',
    },
  ];

  ngOnInit(): void {
    void this.store.bootstrap();
  }
}
