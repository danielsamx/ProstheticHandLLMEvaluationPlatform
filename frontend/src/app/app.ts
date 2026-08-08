import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { AuthService } from '@core/services/auth.service';
import { LabStore } from '@core/services/lab.store';
import { SimulatorBridgeService } from '@core/services/simulator-bridge.service';
import { LanguageService, TranslatePipe } from '@core/services/language.service';

@Component({
  selector: 'ph-root',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, MatTooltipModule, RouterLink, RouterLinkActive, RouterOutlet, TranslatePipe],
  template: `
    <div class="flex h-screen w-screen flex-col bg-white text-navy">
      <header class="shrink-0 border-b border-ink-200 bg-white">
        <div class="flex h-[72px] items-center gap-4 px-3 sm:px-5 lg:px-7">
          @if (logoAvailable()) {
            <img
              src="assets/logo-laboratorio-alan-turing.png"
              alt="Escuela Politécnica Nacional y Laboratorio de Inteligencia y Visión Artificial Alan Turing"
              width="1098"
              height="234"
              decoding="async"
              class="h-11 w-auto max-w-[58%] shrink-0 object-contain object-left sm:h-13 lg:h-14"
              (error)="logoAvailable.set(false)"
            />
          }
          <span class="hidden h-10 w-px bg-ink-200 lg:block"></span>
          <div class="hidden min-w-0 leading-tight lg:block">
            <h1 class="truncate text-sm font-semibold text-navy">{{ 'Prosthetic hand evaluation platform' | tr }}</h1>
            <p class="mt-1 truncate text-[11px] text-ink-500">HANDi EPN V3 · {{ 'EMG to commands validated by language models' | tr }}</p>
          </div>
          <div class="ml-auto flex shrink-0 items-center gap-1 text-navy">
            <button type="button" class="mr-1 h-8 min-w-10 border-r border-ink-200 pr-2 text-xs font-bold" (click)="language.toggle()" [matTooltip]="language.current() === 'en' ? 'Cambiar a español' : 'Switch to English'">
              {{ language.current() === 'en' ? 'ES' : 'EN' }}
            </button>
            @if (auth.user(); as user) {
              <div class="mr-2 hidden text-right xl:block">
                <p class="max-w-48 truncate text-xs font-semibold">{{ user.full_name }}</p>
                <p class="text-[10px] uppercase text-ink-500">{{ user.role }}</p>
              </div>
            }
            @if (auth.isAdmin()) {
              <a routerLink="/users" class="grid h-9 w-9 place-items-center" [matTooltip]="'Manage users' | tr"><mat-icon>manage_accounts</mat-icon></a>
            }
            @if (auth.authenticated()) {
              <button type="button" class="grid h-9 w-9 place-items-center" [matTooltip]="'Sign out' | tr" (click)="logout()"><mat-icon>logout</mat-icon></button>
            } @else {
              <a routerLink="/login" class="grid h-9 w-9 place-items-center" [matTooltip]="'Sign in' | tr"><mat-icon>login</mat-icon></a>
            }
          </div>
        </div>

        <div class="flex h-11 items-stretch bg-navy px-2 text-white sm:px-5 lg:px-7">
          <nav class="flex min-w-0 flex-1 items-stretch overflow-x-auto">
            @for (link of navigation; track link.path) {
              <a [routerLink]="link.path" routerLinkActive="!border-amber !text-white"
                 class="flex shrink-0 items-center gap-2 border-b-[3px] border-transparent px-3 text-[11px] font-semibold text-white/70 transition-colors hover:text-white sm:px-4"
                 [matTooltip]="language.text(link.tooltip)">
                <mat-icon class="!h-4 !w-4 !text-[16px]">{{ link.icon }}</mat-icon>
                <span class="hidden sm:inline">{{ link.label | tr }}</span>
              </a>
            }
          </nav>
          <div class="ml-2 flex shrink-0 items-center gap-3 border-l border-white/15 pl-3 text-[10px] text-white/75">
            @if (store.lmStudio(); as lm) {
              <span class="flex items-center gap-1.5" [matTooltip]="lm.reachable ? lm.models.length + ' modelo(s) disponibles' : 'LM Studio sin conexión'">
                <span class="h-2 w-2 rounded-full" [class.bg-emerald-400]="lm.reachable" [class.bg-pink]="!lm.reachable"></span>
                <span class="hidden lg:inline">LM Studio</span>
              </span>
            }
            <span class="flex items-center gap-1.5" matTooltip="Conexión con el simulador">
              <span class="h-2 w-2 rounded-full" [class.bg-emerald-400]="bridge.state() === 'open'" [class.bg-white]="bridge.state() !== 'open'"></span>
              <span class="hidden lg:inline">{{ 'Simulator' | tr }}</span>
            </span>
          </div>
        </div>
      </header>
      <main class="min-h-0 flex-1"><router-outlet /></main>
    </div>
  `,
})
export class App implements OnInit {
  protected readonly store = inject(LabStore);
  protected readonly bridge = inject(SimulatorBridgeService);
  protected readonly auth = inject(AuthService);
  protected readonly language = inject(LanguageService);
  private readonly router = inject(Router);
  protected readonly logoAvailable = signal(true);

  protected readonly navigation = [
    { path: '/lab', label: 'Laboratory', icon: 'science', tooltip: 'Configure and run an evaluation' },
    { path: '/myo', label: 'Live Myo', icon: 'sensors', tooltip: 'Capture and preprocess Myo signals in real time' },
    { path: '/dataset', label: 'Dataset', icon: 'dataset', tooltip: 'Build a labelled HANDi EMG dataset' },
    { path: '/dashboard', label: 'Results', icon: 'insights', tooltip: 'Accumulated evaluation record' },
    { path: '/logs', label: 'Movements', icon: 'swap_horiz', tooltip: 'Commands sent to the simulator or prosthesis' },
  ];

  ngOnInit(): void {
    void this.auth.restore().finally(() => this.store.bootstrap());
  }

  protected logout(): void {
    this.auth.logout();
    void this.router.navigateByUrl('/login');
  }
}
