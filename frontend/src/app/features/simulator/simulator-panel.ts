import {
  AfterViewInit,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  OnDestroy,
  computed,
  effect,
  inject,
  viewChild,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

import { Handedness } from '@core/models/hand.model';
import { LabStore } from '@core/services/lab.store';
import { SimulatorBridgeService } from '@core/services/simulator-bridge.service';
import { HandScene } from './hand-scene';

/**
 * Right half of the screen: the 3D simulator.
 *
 * The hand's POSE has no manual controls — it is a read-out of what the model
 * commanded and the validator approved. The CAMERA is fully user-controlled:
 * drag to orbit, scroll to zoom, right-drag to pan.
 */
@Component({
  selector: 'ph-simulator-panel',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatButtonModule, MatIconModule, MatTooltipModule],
  template: `
    <div class="relative h-full w-full overflow-hidden bg-gradient-to-b from-ink-50 to-white">
      <!-- Viewport: OrbitControls binds its listeners to this element -->
      <div #viewport class="absolute inset-0 cursor-grab active:cursor-grabbing"></div>

      <!-- ── Header ─────────────────────────────────────────────────────── -->
      <div class="pointer-events-none absolute left-0 right-0 top-0 flex items-start justify-between p-4">
        <div>
          <div class="lab-label">3D Simulator</div>
          <div class="text-sm font-semibold text-navy">
            HANDi EPN V3 · {{ store.handedness() === 'right' ? 'Right' : 'Left' }} hand
          </div>
          <div class="lab-mono text-[10px] text-ink-500">profile {{ store.limitProfile() }}</div>
        </div>

        <!-- ── Hand toggle + camera reset ───────────────────────────────── -->
        <div class="pointer-events-auto flex items-center gap-2">
          <div class="flex overflow-hidden rounded-full border border-ink-200 bg-white shadow-panel">
            @for (option of sides; track option.value) {
              <button
                class="px-3 py-1.5 text-[11px] font-semibold transition-colors"
                [class]="store.handedness() === option.value
                  ? 'bg-navy text-white'
                  : 'bg-white text-ink-500 hover:bg-ink-50'"
                [matTooltip]="'Switch the simulated prosthesis to the ' + option.label.toLowerCase() + ' hand'"
                (click)="setHand(option.value)"
              >
                <mat-icon class="!mr-1 !h-3.5 !w-3.5 !align-[-2px] !text-[14px]">
                  {{ option.icon }}
                </mat-icon>
                {{ option.label }}
              </button>
            }
          </div>

          <button
            class="rounded-full border border-ink-200 bg-white p-1.5 text-ink-500 shadow-panel hover:text-pink"
            matTooltip="Reset the camera"
            (click)="scene.resetCamera()"
          >
            <mat-icon class="!h-4 !w-4 !text-[16px]">center_focus_strong</mat-icon>
          </button>
        </div>
      </div>

      <!-- ── Interaction hint ───────────────────────────────────────────── -->
      <div class="pointer-events-none absolute bottom-[210px] left-1/2 -translate-x-1/2">
        <span class="lab-chip bg-white/85 text-ink-400 backdrop-blur">
          drag to rotate · scroll to zoom · right-drag to pan
        </span>
      </div>

      <!-- ── Rejection banner: the hand stays still, and says why ───────── -->
      @if (bridge.lastRejection(); as rejection) {
        <div class="absolute left-1/2 top-20 w-[82%] -translate-x-1/2 rounded-lg border border-pink bg-white/95 p-3 shadow-panel backdrop-blur">
          <div class="flex items-start gap-2">
            <mat-icon class="!h-5 !w-5 !text-[20px] text-pink">block</mat-icon>
            <div>
              <div class="text-xs font-semibold text-pink">
                Movement rejected at the {{ rejection.failed_stage ?? 'validation' }} stage
              </div>
              <div class="text-[11px] text-ink-600">{{ rejection.reason }}</div>
              <div class="mt-1 text-[10px] text-ink-500">
                The hand was not moved. The execution is recorded as failed.
              </div>
            </div>
          </div>
        </div>
      }

      <!-- ── Actuator read-out ──────────────────────────────────────────── -->
      <div class="absolute bottom-4 left-4 right-4">
        <div class="lab-card p-3">
          <div class="mb-2 flex items-center justify-between">
            <span class="lab-label">Actuator state</span>
            @if (movement(); as frame) {
              <div class="flex items-center gap-2">
                <span class="lab-mono rounded bg-navy px-2 py-0.5 text-[11px] text-white">
                  {{ frame.serial_command ?? '—' }}
                </span>
                <span class="lab-mono text-[10px] text-ink-500">
                  {{ frame.source }} · {{ frame.duration_ms }}ms
                </span>
              </div>
            }
          </div>

          <div class="grid grid-cols-6 gap-2">
            @for (actuator of actuators(); track actuator.letter) {
              <div class="rounded border border-ink-200 bg-ink-50 p-2">
                <div class="flex items-baseline justify-between">
                  <span class="lab-mono text-xs font-bold text-pink">{{ actuator.letter }}</span>
                  <span class="lab-mono text-[10px] text-ink-600">{{ actuator.position }}</span>
                </div>
                <div class="mt-1 text-[9px] uppercase tracking-wide text-ink-500">
                  {{ actuator.label }}
                </div>
                <div class="mt-1 h-1.5 overflow-hidden rounded bg-ink-200">
                  <div class="h-full bg-pink transition-[width] duration-300"
                       [style.width.%]="actuator.normalised * 100"></div>
                </div>
                <div class="mt-0.5 text-[9px] text-ink-400">max {{ actuator.max }}</div>
              </div>
            }
          </div>

          <div class="mt-2 flex items-center justify-between text-[10px] text-ink-500">
            <span>Pose comes only from validated LLM output — the camera is yours, the hand is not.</span>
            <button class="flex items-center gap-1 font-semibold text-ink-500 hover:text-pink"
                    matTooltip="Return the hand to the neutral open pose (end-of-session requirement)."
                    (click)="scene.resetToRest()">
              <mat-icon class="!h-3.5 !w-3.5 !text-[14px]">back_hand</mat-icon>
              Return to rest
            </button>
          </div>
        </div>
      </div>

      <!-- ── FPS ────────────────────────────────────────────────────────── -->
      <div class="pointer-events-none absolute bottom-[210px] right-4">
        <span class="lab-mono text-[10px] text-ink-300">{{ scene.stats().fps }} fps</span>
      </div>
    </div>
  `,
})
export class SimulatorPanel implements AfterViewInit, OnDestroy {
  protected readonly store = inject(LabStore);
  protected readonly bridge = inject(SimulatorBridgeService);
  protected readonly scene = new HandScene();

  private readonly viewport = viewChild.required<ElementRef<HTMLDivElement>>('viewport');

  protected readonly sides: { value: Handedness; label: string; icon: string }[] = [
    { value: 'left', label: 'Left', icon: 'back_hand' },
    { value: 'right', label: 'Right', icon: 'front_hand' },
  ];

  protected readonly movement = computed(() => this.bridge.lastMovement());

  /** Per-actuator read-out, merged with the active limit profile. */
  protected readonly actuators = computed(() => {
    const spec = this.store.handSpec();
    const frame = this.bridge.lastMovement();
    const profile = spec?.limit_profiles.find((p) => p.id === this.store.limitProfile());

    return (spec?.actuators ?? []).map((actuator) => ({
      letter: actuator.letter,
      label: actuator.label.replace('_', ' '),
      position: frame?.actuator_positions?.[actuator.letter] ?? 0,
      normalised: frame?.actuator_normalised?.[actuator.letter] ?? 0,
      max: profile?.limits[actuator.letter]?.[1] ?? 0,
    }));
  });

  constructor() {
    // Render every validated frame the bridge delivers.
    effect(() => {
      const frame = this.bridge.lastMovement();
      if (frame) this.scene.applyPose(frame.joint_angles, frame.duration_ms);
    });

    // Keep the rig in sync with the selected hand.
    effect(() => this.scene.setHandedness(this.store.handedness()));

    // Rebind joint limits whenever the specification arrives or changes.
    effect(() => {
      const spec = this.store.handSpec();
      if (spec) this.scene.applySpec(spec);
    });
  }

  protected setHand(side: Handedness): void {
    this.store.handedness.set(side);
  }

  ngAfterViewInit(): void {
    this.scene.init(
      this.viewport().nativeElement,
      this.store.handSpec(),
      this.store.handedness(),
    );
  }

  ngOnDestroy(): void {
    this.scene.dispose();
  }
}
