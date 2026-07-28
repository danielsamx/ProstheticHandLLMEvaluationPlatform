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
import { CameraView, HandScene } from './hand-scene';

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

      <!--
        A blank 3D panel is the least debuggable failure in the application: it
        looks the same whether WebGL is missing, the canvas has zero size, or the
        specification never arrived. Say which it is.
      -->
      @if (!scene.ready()) {
        <div class="absolute inset-0 flex items-center justify-center p-6">
          <div class="max-w-md rounded-lg border border-amber bg-white/95 p-4 shadow-panel backdrop-blur">
            <div class="mb-2 flex items-center gap-2">
              <mat-icon class="!h-5 !w-5 !text-[20px] text-amber">visibility_off</mat-icon>
              <span class="text-sm font-semibold text-navy">The hand is not being rendered</span>
            </div>

            <p class="mb-3 text-[12px] leading-relaxed text-ink-600">{{ blockingReason() }}</p>

            <dl class="divide-y divide-ink-100 overflow-hidden rounded border border-ink-200 text-[11px]">
              @for (row of diagnosticRows(); track row.label) {
                <div class="flex items-center justify-between px-2.5 py-1.5">
                  <dt class="text-ink-500">{{ row.label }}</dt>
                  <dd class="lab-mono font-medium"
                      [class]="row.ok ? 'text-navy' : 'text-pink'">{{ row.value }}</dd>
                </div>
              }
            </dl>
          </div>
        </div>
      }

      <!-- ── Header ─────────────────────────────────────────────────────── -->
      <div class="pointer-events-none absolute left-0 right-0 top-0 flex items-start justify-between p-4">
        <div>
          <div class="lab-label">3D Simulator</div>
          <div class="text-sm font-semibold text-navy">
            HANDi EPN V3 · {{ store.handedness() === 'right' ? 'Right' : 'Left' }} hand
          </div>
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

          <!--
            Camera presets. A single "reset" button forced the user to orbit
            manually every time they wanted the palm or the back of the hand,
            which are the two views that actually matter when reading a grasp.
          -->
          <div class="flex overflow-hidden rounded-full border border-ink-200 bg-white shadow-panel">
            @for (view of views; track view.value) {
              <button
                class="px-2.5 py-1.5 text-[11px] font-semibold transition-colors"
                [class]="scene.activeView() === view.value
                  ? 'bg-ink-100 text-pink'
                  : 'bg-white text-ink-500 hover:bg-ink-50 hover:text-pink'"
                [matTooltip]="view.tooltip"
                (click)="scene.moveCameraTo(view.value)"
              >
                <mat-icon class="!h-4 !w-4 !text-[16px]">{{ view.icon }}</mat-icon>
              </button>
            }
          </div>
        </div>
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

          <div class="mt-2 flex items-center text-[10px] text-ink-500">
            <span>drag to rotate · scroll to zoom · right-drag to pan.</span>
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

  protected readonly views: { value: CameraView; icon: string; tooltip: string }[] = [
    { value: 'default', icon: 'center_focus_strong', tooltip: 'Default three-quarter view' },
    { value: 'palm', icon: 'front_hand', tooltip: 'Palm view — read the grasp' },
    { value: 'back', icon: 'back_hand', tooltip: 'Back of the hand — read knuckle flexion' },
    { value: 'side', icon: 'swipe_right', tooltip: 'Side view — read finger curl' },
    { value: 'top', icon: 'expand_less', tooltip: 'Top-down view' },
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

  /** The single most likely cause, stated plainly. */
  protected blockingReason(): string {
    const d = this.scene.diagnostics();
    if (!d.webglAvailable) {
      return d.lastError ?? 'WebGL is unavailable in this browser.';
    }
    if (d.contextLost) {
      return d.lastError ?? 'The WebGL context was lost; reload the page.';
    }
    if (d.lastError) return d.lastError;
    if (!d.canvasWidth || !d.canvasHeight) {
      return 'The viewport has no size yet. If this persists, the panel is being '
           + 'laid out at zero height — try widening the window.';
    }
    if (!d.meshCount) {
      return 'The scene contains no geometry. The rig failed to build; check the '
           + 'browser console for an error from the simulator.';
    }
    if (!d.specLoaded) {
      return 'The hardware specification has not loaded, so the joints cannot be '
           + 'bound. Check that the backend is reachable.';
    }
    return 'The viewport is not ready yet.';
  }

  protected diagnosticRows(): { label: string; value: string; ok: boolean }[] {
    const d = this.scene.diagnostics();
    return [
      { label: 'WebGL', value: d.webglAvailable ? 'available' : 'unavailable',
        ok: d.webglAvailable },
      { label: 'Context', value: d.contextLost ? 'lost' : 'active', ok: !d.contextLost },
      { label: 'Canvas', value: `${d.canvasWidth} × ${d.canvasHeight}`,
        ok: d.canvasWidth > 0 && d.canvasHeight > 0 },
      { label: 'Meshes in scene', value: String(d.meshCount), ok: d.meshCount > 0 },
      { label: 'Hand specification', value: d.specLoaded ? 'loaded' : 'missing',
        ok: d.specLoaded },
      { label: 'Joints bound', value: String(d.jointsBound), ok: d.jointsBound > 0 },
    ];
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
