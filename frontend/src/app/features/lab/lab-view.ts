import { ChangeDetectionStrategy, Component } from '@angular/core';

import { SimulatorPanel } from '@features/simulator/simulator-panel';
import { LabPanel } from './lab-panel';

/**
 * The working surface: parameters on the left, the hand on the right.
 *
 * Exactly 50/50 side by side from the medium breakpoint up; below that the
 * panels stack, because half a phone screen is too narrow for either the
 * parameter forms or a legible 3D viewport.
 */
@Component({
  selector: 'ph-lab-view',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [LabPanel, SimulatorPanel],
  template: `
    <div class="grid h-full min-h-0 grid-cols-1 grid-rows-[1fr_1fr] md:grid-cols-2 md:grid-rows-1">
      <section class="min-h-0 overflow-hidden border-b border-ink-200 md:border-b-0 md:border-r">
        <ph-lab-panel />
      </section>
      <section class="min-h-0 overflow-hidden">
        <ph-simulator-panel />
      </section>
    </div>
  `,
})
export class LabView {}
