import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Router } from '@angular/router';

import { Execution } from '@core/models/llm.model';
import { DashboardStore } from '@core/services/dashboard.store';
import { LabStore } from '@core/services/lab.store';

/**
 * The reading surface: the accumulated experimental record, full width.
 *
 * Everything here is derived from what has already run. There is nothing to
 * configure, which is why it earns the whole viewport — an execution row has
 * fifteen columns worth saying, and half a screen forced most of them out.
 */
@Component({
  selector: 'ph-dashboard-view',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    DatePipe, FormsModule, MatButtonModule, MatFormFieldModule, MatIconModule,
    MatInputModule, MatSelectModule, MatTooltipModule,
  ],
  template: `
    <div class="h-full overflow-y-auto bg-ink-50">
      <div class="mx-auto max-w-[1800px] space-y-4 p-4 lg:p-6">

        <!-- ── Header ──────────────────────────────────────────────────── -->
        <div class="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 class="text-lg font-semibold text-navy">Experiment record</h2>
            <p class="text-[12px] text-ink-500">
              Every execution ever run, with the conditions that produced it.
            </p>
          </div>

          <div class="flex flex-wrap items-center gap-2">
            <mat-form-field appearance="outline" class="dense-field !w-40">
              <mat-select [ngModel]="store.window()" (ngModelChange)="store.setWindow($event)">
                <mat-option [value]="0">All time</mat-option>
                <mat-option [value]="1">Last 24 hours</mat-option>
                <mat-option [value]="7">Last 7 days</mat-option>
                <mat-option [value]="30">Last 30 days</mat-option>
              </mat-select>
            </mat-form-field>

            <button mat-stroked-button class="!h-[34px] !text-[11px]"
                    [disabled]="store.loading()" (click)="store.refresh()">
              <mat-icon class="!h-4 !w-4 !text-[16px]">refresh</mat-icon> Refresh
            </button>

            <button mat-flat-button color="primary" class="!h-[34px] !text-[11px]"
                    [disabled]="!store.executions().length" (click)="exportCsv()">
              <mat-icon class="!h-4 !w-4 !text-[16px]">download</mat-icon> Export CSV
            </button>
          </div>
        </div>

        <!-- ── Headline numbers ────────────────────────────────────────── -->
        @if (store.stats(); as stats) {
          <div class="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            @for (card of cards(stats); track card.label) {
              <div class="lab-card p-3">
                <div class="lab-label">{{ card.label }}</div>
                <div class="lab-mono mt-0.5 text-xl font-semibold"
                     [style.color]="card.colour">{{ card.value }}</div>
                @if (card.note) {
                  <div class="text-[10px] text-ink-500">{{ card.note }}</div>
                }
              </div>
            }
          </div>

          <!-- ── Per model ─────────────────────────────────────────────── -->
          <div class="lab-card overflow-hidden">
            <div class="flex items-center justify-between border-b border-ink-200 px-4 py-2.5">
              <span class="text-sm font-semibold text-navy">By model</span>
              @if (!stats.comparable) {
                <!--
                  The honest caveat. Rows produced under different frozen
                  contexts are not a like-for-like comparison, and presenting
                  them as a ranking would imply something the data cannot carry.
                -->
                <span class="lab-chip bg-amber text-navy"
                      matTooltip="These executions did not all share one frozen prompt context, so differences cannot be attributed to the model.">
                  <mat-icon class="!h-3.5 !w-3.5 !text-[13px]">warning_amber</mat-icon>
                  mixed conditions — not a fair comparison
                </span>
              }
            </div>

            <table class="w-full text-[12px]">
              <thead class="bg-ink-50 text-ink-600">
                <tr>
                  <th class="px-4 py-2 text-left font-semibold">Model</th>
                  <th class="px-3 py-2 text-right font-semibold">Runs</th>
                  <th class="px-3 py-2 text-right font-semibold">Pass rate</th>
                  <th class="px-3 py-2 text-left font-semibold">&nbsp;</th>
                  <th class="px-3 py-2 text-right font-semibold">Mean latency</th>
                  <th class="px-3 py-2 text-right font-semibold">Tokens</th>
                  <th class="px-3 py-2 text-right font-semibold">Cost</th>
                  <th class="px-3 py-2 text-right font-semibold">Last run</th>
                </tr>
              </thead>
              <tbody>
                @for (row of stats.by_model; track row.litellm_model) {
                  <tr class="border-t border-ink-100 hover:bg-ink-50">
                    <td class="lab-mono px-4 py-2 text-navy">{{ row.litellm_model }}</td>
                    <td class="lab-mono px-3 py-2 text-right">{{ row.executions }}</td>
                    <td class="lab-mono px-3 py-2 text-right font-semibold"
                        [style.color]="row.pass_rate >= 0.8 ? '#001F3F' : '#D81B60'">
                      {{ (row.pass_rate * 100).toFixed(0) }}%
                    </td>
                    <td class="w-40 px-3 py-2">
                      <div class="h-1.5 overflow-hidden rounded bg-ink-100">
                        <div class="h-full"
                             [style.width.%]="row.pass_rate * 100"
                             [style.background]="row.pass_rate >= 0.8 ? '#001F3F' : '#D81B60'"></div>
                      </div>
                    </td>
                    <td class="lab-mono px-3 py-2 text-right">
                      {{ row.mean_latency_ms ? row.mean_latency_ms + ' ms' : '—' }}
                    </td>
                    <td class="lab-mono px-3 py-2 text-right">{{ row.total_tokens }}</td>
                    <td class="lab-mono px-3 py-2 text-right">
                      {{ row.total_cost_usd > 0 ? ('$' + row.total_cost_usd.toFixed(4)) : 'local' }}
                    </td>
                    <td class="lab-mono px-3 py-2 text-right text-ink-500">
                      {{ row.last_run_at | date: 'dd MMM HH:mm' }}
                    </td>
                  </tr>
                } @empty {
                  <tr><td colspan="8" class="px-4 py-6 text-center text-ink-500">
                    No executions in this period.
                  </td></tr>
                }
              </tbody>
            </table>
          </div>

          <!-- ── How they fail ─────────────────────────────────────────── -->
          @if (stats.top_failure_codes.length) {
            <div class="lab-card p-4">
              <div class="mb-1 text-sm font-semibold text-navy">Most common rejections</div>
              <p class="mb-3 text-[11px] text-ink-500">
                How a model fails is more actionable than how often. Each code
                names the rule that rejected the response.
              </p>
              <div class="flex flex-wrap gap-2">
                @for (failure of stats.top_failure_codes; track failure['code']) {
                  <span class="lab-chip bg-pink/10 text-pink lab-mono">
                    {{ failure['code'] }} · {{ failure['count'] }}
                  </span>
                }
              </div>
            </div>
          }
        }

        <!-- ── Executions ──────────────────────────────────────────────── -->
        <div class="lab-card overflow-hidden">
          <div class="flex flex-wrap items-center justify-between gap-2 border-b border-ink-200 px-4 py-2.5">
            <span class="text-sm font-semibold text-navy">Executions</span>
            <div class="flex items-center gap-2">
              <mat-form-field appearance="outline" class="dense-field !w-44">
                <mat-select [ngModel]="store.statusFilter()"
                            (ngModelChange)="store.statusFilter.set($event)">
                  <mat-option [value]="null">All outcomes</mat-option>
                  <mat-option value="passed">Validated</mat-option>
                  <mat-option value="failed">Rejected</mat-option>
                  <mat-option value="error">Provider error</mat-option>
                </mat-select>
              </mat-form-field>
              <mat-form-field appearance="outline" class="dense-field !w-56">
                <input matInput placeholder="Filter by model"
                       [ngModel]="store.modelFilter()"
                       (ngModelChange)="store.modelFilter.set($event)" />
              </mat-form-field>
              <span class="lab-mono text-[11px] text-ink-500">
                {{ store.filtered().length }} shown
              </span>
            </div>
          </div>

          <div class="overflow-x-auto">
            <table class="w-full text-[12px]">
              <thead class="bg-ink-50 text-ink-600">
                <tr>
                  <th class="px-3 py-2 text-left font-semibold">When</th>
                  <th class="px-3 py-2 text-left font-semibold">Model</th>
                  <th class="px-3 py-2 text-left font-semibold">Outcome</th>
                  <th class="px-3 py-2 text-left font-semibold">Command</th>
                  <th class="px-3 py-2 text-left font-semibold">Pattern</th>
                  <th class="px-3 py-2 text-center font-semibold">Clean</th>
                  <th class="px-3 py-2 text-right font-semibold">T</th>
                  <th class="px-3 py-2 text-right font-semibold">Latency</th>
                  <th class="px-3 py-2 text-right font-semibold">Tokens</th>
                  <th class="px-3 py-2 text-right font-semibold">&nbsp;</th>
                </tr>
              </thead>
              <tbody>
                @for (execution of store.filtered(); track execution.id) {
                  <tr class="border-t border-ink-100 hover:bg-ink-50">
                    <td class="lab-mono px-3 py-1.5 text-ink-500">
                      {{ execution.created_at | date: 'dd MMM HH:mm:ss' }}
                    </td>
                    <td class="lab-mono px-3 py-1.5 text-navy">
                      {{ execution.litellm_model ?? '—' }}
                    </td>
                    <td class="px-3 py-1.5">
                      <span class="lab-chip" [class]="outcome(execution).tone">
                        {{ outcome(execution).label }}
                      </span>
                    </td>
                    <td class="lab-mono px-3 py-1.5 text-pink">
                      {{ execution.movement?.serial_command ?? '—' }}
                    </td>
                    <td class="lab-mono px-3 py-1.5 text-ink-600">
                      {{ execution.metrics?.detected_pattern ?? '—' }}
                    </td>
                    <td class="px-3 py-1.5 text-center"
                        matTooltip="The reply was bare JSON, with no fence or prose around it">
                      @if (execution.metrics?.is_bare_json) {
                        <mat-icon class="!h-4 !w-4 !text-[16px] text-navy">check</mat-icon>
                      } @else if (execution.metrics) {
                        <mat-icon class="!h-4 !w-4 !text-[16px] text-amber">build</mat-icon>
                      } @else { <span class="text-ink-300">—</span> }
                    </td>
                    <td class="lab-mono px-3 py-1.5 text-right text-ink-500">
                      {{ execution.temperature ?? '—' }}
                    </td>
                    <td class="lab-mono px-3 py-1.5 text-right">
                      {{ execution.latency_ms ? execution.latency_ms + ' ms' : '—' }}
                    </td>
                    <td class="lab-mono px-3 py-1.5 text-right text-ink-500">
                      {{ execution.total_tokens ?? '—' }}
                    </td>
                    <td class="px-3 py-1.5 text-right">
                      <button class="text-ink-400 hover:text-pink"
                              [disabled]="!execution.movement"
                              matTooltip="Replay this validated movement in the simulator"
                              (click)="replay(execution)">
                        <mat-icon class="!h-4 !w-4 !text-[16px]">replay</mat-icon>
                      </button>
                    </td>
                  </tr>
                } @empty {
                  <tr><td colspan="10" class="px-4 py-8 text-center text-ink-500">
                    @if (store.loading()) { Loading… } @else { Nothing matches these filters. }
                  </td></tr>
                }
              </tbody>
            </table>
          </div>
        </div>

        <!-- ── Saved configurations ────────────────────────────────────── -->
        <div class="lab-card overflow-hidden">
          <div class="border-b border-ink-200 px-4 py-2.5">
            <span class="text-sm font-semibold text-navy">Saved configurations</span>
            <p class="text-[11px] text-ink-500">
              Apply the same one to every model in a comparison — that is what
              keeps the comparison controlled.
            </p>
          </div>
          <div class="grid gap-2 p-3 md:grid-cols-2 xl:grid-cols-3">
            @for (config of lab.configurations(); track config.id) {
              <button
                class="rounded border p-3 text-left transition-colors"
                [class]="config.id === lab.selectedConfigurationId()
                  ? 'border-pink bg-pink/5' : 'border-ink-200 bg-white hover:border-ink-400'"
                (click)="applyAndOpenLab(config)"
              >
                <div class="flex items-center justify-between">
                  <span class="truncate text-[12px] font-semibold text-navy">{{ config.name }}</span>
                  <span class="lab-mono text-[10px] text-ink-400">{{ config.use_count ?? 0 }}×</span>
                </div>
                <div class="lab-mono mt-1 text-[10px] text-ink-500">
                  T={{ config.temperature }} · top_p={{ config.top_p }}
                  @if (config.seed !== null) { · seed={{ config.seed }} }
                  · {{ config.response_format }}
                </div>
                @if (config.description) {
                  <div class="mt-1 line-clamp-2 text-[10px] text-ink-500">{{ config.description }}</div>
                }
              </button>
            } @empty {
              <p class="p-3 text-[12px] text-ink-500">
                None yet. Save one from the laboratory's run bar.
              </p>
            }
          </div>
        </div>
      </div>
    </div>
  `,
})
export class DashboardView implements OnInit {
  protected readonly store = inject(DashboardStore);
  protected readonly lab = inject(LabStore);
  private readonly router = inject(Router);

  ngOnInit(): void {
    void this.store.refresh();
  }

  protected cards(stats: {
    executions: number; pass_rate: number | null; distinct_models: number;
    mean_latency_ms: number | null; p95_latency_ms: number | null;
    total_tokens: number; total_cost_usd: number; provider_errors: number;
  }): { label: string; value: string; note?: string; colour: string }[] {
    return [
      { label: 'Executions', value: String(stats.executions), colour: '#001F3F' },
      {
        label: 'Pass rate',
        value: stats.pass_rate === null ? '—' : `${(stats.pass_rate * 100).toFixed(0)}%`,
        note: 'cleared all seven stages',
        colour: (stats.pass_rate ?? 0) >= 0.8 ? '#001F3F' : '#D81B60',
      },
      { label: 'Models', value: String(stats.distinct_models), colour: '#001F3F' },
      {
        label: 'Mean latency',
        value: stats.mean_latency_ms ? `${stats.mean_latency_ms} ms` : '—',
        note: stats.p95_latency_ms ? `p95 ${stats.p95_latency_ms} ms` : undefined,
        colour: '#001F3F',
      },
      { label: 'Tokens', value: stats.total_tokens.toLocaleString(), colour: '#001F3F' },
      {
        label: 'Provider errors',
        value: String(stats.provider_errors),
        note: 'never reached validation',
        colour: stats.provider_errors ? '#D81B60' : '#001F3F',
      },
    ];
  }

  protected outcome(execution: Execution): { label: string; tone: string } {
    if (execution.status === 'provider_error' || execution.status === 'timeout') {
      return { label: 'provider error', tone: 'bg-amber text-navy' };
    }
    if (execution.validation_passed) return { label: 'validated', tone: 'bg-navy text-white' };
    const stage = execution.validation_result?.failed_stage;
    return { label: stage ? `rejected · ${stage}` : 'rejected', tone: 'bg-pink text-white' };
  }

  protected async replay(execution: Execution): Promise<void> {
    await this.lab.replay(execution);
    // Replaying is only meaningful next to the simulator.
    await this.router.navigate(['/lab']);
  }

  protected async applyAndOpenLab(config: Parameters<LabStore['applyConfiguration']>[0]): Promise<void> {
    this.lab.applyConfiguration(config);
    await this.router.navigate(['/lab']);
  }

  protected exportCsv(): void {
    void this.store.exportCsv();
  }
}
