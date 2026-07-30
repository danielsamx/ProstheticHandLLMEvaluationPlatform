import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, computed, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

import { MovementLogEntry } from '@core/models/llm.model';
import { MovementStore } from '@core/services/movement.store';

/**
 * Every command that moved the hand.
 *
 * Distinct from the execution history, which records what models *answered*.
 * This records what was *transmitted* — and the two are not the same list. A
 * pose that resolved is not a pose that was delivered: the prosthesis link can
 * be closed, or drop mid-session. It also carries commands no model produced —
 * manual tests and replays — which move the hand exactly as a model's answer
 * does, and would otherwise be movements with no record explaining them.
 *
 * The first question after any unexpected movement is "did the hand actually
 * receive this, and who sent it?". This view is the only place that answers it.
 */
@Component({
  selector: 'ph-movement-log-view',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, MatButtonModule, MatIconModule, MatTooltipModule],
  template: `
    <div class="h-full overflow-y-auto bg-ink-50">
      <div class="mx-auto max-w-[1800px] space-y-4 p-4 lg:p-6">

        <!-- ── Header ──────────────────────────────────────────────────── -->
        <div class="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 class="text-lg font-semibold text-navy">Movement log</h2>
            <p class="text-[12px] text-ink-500">
              Every command transmitted to the simulator or the prosthesis, and
              what each destination did with it.
            </p>
          </div>

          <div class="flex flex-wrap items-center gap-1.5">
            <!--
              Filter by origin, because the three kinds answer different
              questions. A model run is evidence; a manual test is a check on the
              plumbing; a replay is neither, and counting it as either would be
              wrong.
            -->
            @for (option of sources; track option.value) {
              <button
                class="rounded-full border px-3 py-1.5 text-[11px] font-semibold transition-colors"
                [class]="store.sourceFilter() === option.value
                  ? 'border-navy bg-navy text-white'
                  : 'border-ink-200 bg-white text-ink-500 hover:text-navy'"
                [matTooltip]="option.tooltip"
                (click)="store.setSourceFilter(option.value)"
              >
                {{ option.label }}
              </button>
            }

            <button mat-stroked-button class="!ml-1 !h-[34px] !text-[11px]"
                    [disabled]="store.loadingLog()"
                    (click)="store.refreshLog()">
              <mat-icon class="!h-4 !w-4 !text-[16px]">refresh</mat-icon> Refresh
            </button>
          </div>
        </div>

        <!-- ── Headline counts ─────────────────────────────────────────── -->
        <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
          @for (card of cards(); track card.label) {
            <div class="flex items-center gap-2 rounded-md px-3 py-2" [class]="card.tone">
              <mat-icon class="!h-4 !w-4 shrink-0 !text-[16px] opacity-70">
                {{ card.icon }}
              </mat-icon>
              <div class="min-w-0 leading-none">
                <div class="lab-mono text-[14px] font-semibold">{{ card.value }}</div>
                <div class="mt-0.5 truncate text-[9px] uppercase tracking-wider opacity-70">
                  {{ card.label }}
                </div>
              </div>
            </div>
          }
        </div>

        @if (store.error(); as message) {
          <div class="flex items-start gap-2 rounded-lg border border-pink bg-pink/5 px-4 py-3">
            <mat-icon class="!h-5 !w-5 !text-[20px] text-pink">error_outline</mat-icon>
            <div class="min-w-0">
              <div class="text-sm font-semibold text-pink">Could not load the log</div>
              <div class="lab-mono mt-0.5 break-words text-[11px] text-ink-600">{{ message }}</div>
            </div>
          </div>
        }

        <!-- ── The log ─────────────────────────────────────────────────── -->
        <div class="lab-card overflow-hidden">
          <div class="overflow-x-auto">
            <table class="w-full text-[12px]">
              <thead class="bg-ink-50 text-ink-600">
                <tr>
                  <th class="px-3 py-2 text-left font-semibold">When</th>
                  <th class="px-3 py-2 text-left font-semibold">Command</th>
                  <th class="px-3 py-2 text-left font-semibold">Origin</th>
                  <th class="px-3 py-2 text-center font-semibold">Simulator</th>
                  <th class="px-3 py-2 text-center font-semibold">Prosthesis</th>
                  <th class="px-3 py-2 text-left font-semibold">Actuators</th>
                  <th class="px-3 py-2 text-right font-semibold">Duration</th>
                  <th class="px-3 py-2 text-left font-semibold">Hand</th>
                </tr>
              </thead>
              <tbody>
                @for (entry of store.log(); track entry.id) {
                  <tr class="border-t border-ink-100 hover:bg-ink-50">
                    <td class="lab-mono px-3 py-1.5 text-ink-500">
                      {{ entry.created_at | date: 'dd MMM HH:mm:ss' }}
                    </td>
                    <td class="lab-mono px-3 py-1.5 font-semibold text-pink">
                      {{ entry.serial_command }}
                    </td>
                    <td class="px-3 py-1.5">
                      <span class="lab-chip" [class]="originTone(entry)"
                            [matTooltip]="originTooltip(entry)">
                        {{ entry.source }}
                      </span>
                    </td>

                    <!--
                      Two independent columns, not one "delivered" flag. The
                      simulator renders from the backend and the hardware is
                      driven from the browser, so either can arrive while the
                      other does not — and that asymmetry is exactly what someone
                      reading this log is trying to diagnose.
                    -->
                    <td class="px-3 py-1.5 text-center">
                      @if (entry.sent_to_simulator) {
                        <mat-icon class="!h-4 !w-4 !text-[16px] text-navy"
                                  matTooltip="Rendered">check_circle</mat-icon>
                      } @else {
                        <mat-icon class="!h-4 !w-4 !text-[16px] text-ink-300"
                                  matTooltip="No simulator was attached">remove_circle_outline</mat-icon>
                      }
                    </td>
                    <td class="px-3 py-1.5 text-center">
                      @if (entry.sent_to_prosthesis) {
                        <mat-icon class="!h-4 !w-4 !text-[16px] text-navy"
                                  [matTooltip]="'Transmitted over ' + entry.transport">
                          bluetooth_connected
                        </mat-icon>
                      } @else if (entry.delivery_error) {
                        <mat-icon class="!h-4 !w-4 !text-[16px] text-pink"
                                  [matTooltip]="entry.delivery_error">error_outline</mat-icon>
                      } @else {
                        <mat-icon class="!h-4 !w-4 !text-[16px] text-ink-300"
                                  matTooltip="No hardware link was open">link_off</mat-icon>
                      }
                    </td>

                    <td class="lab-mono px-3 py-1.5 text-[11px] text-ink-600">
                      {{ actuators(entry) }}
                    </td>
                    <td class="lab-mono px-3 py-1.5 text-right text-ink-500">
                      {{ entry.duration_ms ? entry.duration_ms + ' ms' : '—' }}
                    </td>
                    <td class="px-3 py-1.5 text-ink-500">{{ entry.handedness }}</td>
                  </tr>
                } @empty {
                  <tr><td colspan="8" class="px-4 py-8 text-center text-ink-500">
                    @if (store.loadingLog()) {
                      Loading…
                    } @else if (store.sourceFilter()) {
                      No {{ store.sourceFilter() }} commands recorded.
                    } @else {
                      Nothing has moved the hand yet. Run an evaluation, or type a
                      command into the simulator's test field.
                    }
                  </td></tr>
                }
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  `,
})
export class MovementLogView implements OnInit {
  protected readonly store = inject(MovementStore);

  protected readonly sources = [
    { value: null, label: 'All', tooltip: 'Every command that moved the hand.' },
    {
      value: 'execution',
      label: 'Model',
      tooltip: 'Commands a model produced and validation approved. This is the evidence.',
    },
    {
      value: 'manual',
      label: 'Manual',
      tooltip: 'Commands typed to test the link or the mechanics. Not evidence about a model.',
    },
    {
      value: 'replay',
      label: 'Replay',
      tooltip: 'A stored movement re-sent. It moved the hand again, so it is logged again.',
    },
  ];

  /**
   * Counts over what is loaded, and labelled as such.
   *
   * Deliberately not presented as totals: this is the most recent page of the
   * log, and calling a page's count a total is how a dashboard starts lying.
   */
  protected readonly cards = computed(() => {
    const entries = this.store.log();
    const navy = 'bg-navy/5 text-navy';
    const amber = 'bg-amber/15 text-navy';

    return [
      {
        label: 'Loaded',
        value: String(entries.length),
        icon: 'list_alt',
        tone: navy,
      },
      {
        label: 'Reached simulator',
        value: String(entries.filter((e) => e.sent_to_simulator).length),
        icon: 'view_in_ar',
        tone: navy,
      },
      {
        label: 'Reached hardware',
        value: String(entries.filter((e) => e.sent_to_prosthesis).length),
        icon: 'bluetooth_connected',
        tone: amber,
      },
      {
        label: 'Delivery failures',
        value: String(entries.filter((e) => e.delivery_error).length),
        icon: 'error_outline',
        tone: entries.some((e) => e.delivery_error) ? 'bg-pink/10 text-pink' : navy,
      },
    ];
  });

  protected originTone(entry: MovementLogEntry): string {
    if (entry.source === 'execution') return 'bg-navy text-white';
    if (entry.source === 'manual') return 'bg-amber text-navy';
    return 'bg-ink-100 text-ink-600';
  }

  protected originTooltip(entry: MovementLogEntry): string {
    const who = entry.triggered_by_email ? ` by ${entry.triggered_by_email}` : '';
    switch (entry.source) {
      case 'execution':
        return `A model's answer, after all seven validation stages${who}.`;
      case 'manual':
        return `Typed to test the link or the mechanics${who}. Not evidence about a model.`;
      default:
        return `A stored movement re-sent${who}.`;
    }
  }

  /** `A320 B240` — compact enough for a table cell. */
  protected actuators(entry: MovementLogEntry): string {
    const positions = Object.entries(entry.actuator_positions ?? {});
    if (!positions.length) return '—';
    return positions.map(([letter, value]) => `${letter}${value}`).join(' ');
  }

  ngOnInit(): void {
    void this.store.refreshLog();
  }
}
