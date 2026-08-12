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

        <!--
          The failure that was invisible.

          The store caught every error into a signal that nothing ever read, so
          a 500 from the API looked exactly like a database with no rows in it:
          an empty table saying "nothing matches these filters". A view that
          cannot distinguish "no data" from "the request failed" will send
          someone hunting through the wrong half of the system.
        -->
        @if (store.error(); as message) {
          <div class="flex items-start gap-2 rounded-lg border border-pink bg-pink/5 px-4 py-3">
            <mat-icon class="!h-5 !w-5 !text-[20px] text-pink">error_outline</mat-icon>
            <div class="min-w-0">
              <div class="text-sm font-semibold text-pink">Could not load the record</div>
              <div class="lab-mono mt-0.5 break-words text-[11px] text-ink-600">{{ message }}</div>
            </div>
            <button mat-stroked-button class="!ml-auto !h-[30px] !text-[11px]"
                    (click)="store.refresh()">Retry</button>
          </div>
        }

        <!-- ── Headline numbers ────────────────────────────────────────── -->
        @if (store.stats(); as stats) {
          <div class="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
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

          <!--
            ── Prompt configurations ──────────────────────────────────────

            The answer to "which setup produced that result?".

            Deduplicated by the backend on the frozen-context digest, so this
            is a list rather than a grouping: run the same three blocks a
            hundred times and there is one row; go back to an earlier setup and
            it reuses the row it made the first time.

            Broken out per model on purpose. A configuration is only comparable
            within one model — averaging a 4B and a 30B under the same prompt
            gives a number that describes neither — so there is deliberately no
            single accuracy figure for a configuration as a whole.
          -->
          @if (store.configurations().length) {
            <div class="lab-card overflow-hidden">
              <div class="flex items-baseline justify-between border-b border-ink-200 px-4 py-2.5">
                <span class="text-sm font-semibold text-navy">Prompt configurations</span>
                <span class="text-[11px] text-ink-500">
                  {{ store.configurations().length }} distinct setup(s) ·
                  system, technical and EMG versions
                </span>
              </div>

              <div class="divide-y divide-ink-100">
                @for (configuration of store.configurations(); track configuration.id) {
                  <div class="px-4 py-3">
                    <div class="flex flex-wrap items-center gap-2">
                      <span class="lab-chip bg-navy text-white lab-mono">
                        {{ configuration.label }}
                      </span>
                      <span class="text-[11px] text-ink-500">
                        {{ configuration.executions }} run(s) ·
                        last used {{ configuration.last_used_at | date: 'dd MMM HH:mm' }}
                      </span>
                    </div>

                    @if (configuration.by_model.length) {
                      <div class="mt-2 grid gap-1.5 sm:grid-cols-2 xl:grid-cols-3">
                        @for (row of configuration.by_model; track row.litellm_model) {
                          <div class="flex items-center gap-2 rounded-md bg-ink-50 px-2 py-1.5 text-[11px]">
                            <mat-icon class="!h-4 !w-4 shrink-0 !text-[16px] text-ink-400">
                              memory
                            </mat-icon>
                            <div class="min-w-0 flex-1">
                              <div class="lab-mono truncate text-navy">{{ row.litellm_model }}</div>
                              <div class="text-[10px] text-ink-500">
                                {{ row.executions }} run(s) ·
                                {{ (row.pass_rate * 100).toFixed(0) }}% valid
                                @if (row.command_accuracy !== null) {
                                  · {{ (row.command_accuracy * 100).toFixed(0) }}% correct
                                  ({{ row.command_matched }}/{{ row.command_labelled }})
                                } @else {
                                  · unlabelled
                                }
                              </div>
                            </div>
                          </div>
                        }
                      </div>
                    } @else {
                      <div class="mt-1 text-[11px] text-ink-500">
                        No completed runs under this configuration yet.
                      </div>
                    }
                  </div>
                }
              </div>
            </div>
          }

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
                  <th class="px-3 py-2 text-left font-semibold">Expected</th>
                  <th class="px-3 py-2 text-left font-semibold">Got</th>
                  <th class="px-3 py-2 text-center font-semibold">Match</th>
                  <th class="px-3 py-2 text-left font-semibold">Config</th>
                  <th class="px-3 py-2 text-left font-semibold">Input</th>
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
                    <!--
                      Expected and got, side by side, because a table of
                      commands with no answer key beside them cannot be read as
                      right or wrong — only as "something happened".
                    -->
                    <td class="lab-mono px-3 py-1.5 text-ink-600">
                      {{ execution.expected_serial_command ?? '—' }}
                    </td>
                    <td class="lab-mono px-3 py-1.5"
                        [class]="matchTone(execution)">
                      <!--
                        A refusal and a rejection both leave no command, and they
                        are opposite outcomes: one is the model behaving well.
                        Showing the same dash for both would hide that.
                      -->
                      {{ execution.movement?.serial_command
                         ?? execution.validation_result?.normalised_serial
                         ?? (execution.metrics?.refused_to_act ? 'no command' : '—') }}
                    </td>
                    <td class="px-3 py-1.5 text-center">
                      <!--
                        Three states, not two. A blank cell means the run was
                        never labelled, which is different from being wrong, and
                        showing a cross for it would invent a failure.
                      -->
                      @if (execution.metrics?.command_matches_expected === true) {
                        <mat-icon class="!h-4 !w-4 !text-[16px] text-navy"
                                  matTooltip="Matches the expected command">check_circle</mat-icon>
                      } @else if (execution.metrics?.command_matches_expected === false) {
                        <mat-icon class="!h-4 !w-4 !text-[16px] text-pink"
                                  matTooltip="Differs from the expected command">cancel</mat-icon>
                      } @else {
                        <span class="text-ink-300"
                              matTooltip="No expected command was given for this run">–</span>
                      }
                    </td>
                    <td class="px-3 py-1.5">
                      <span class="lab-chip lab-mono bg-navy/5 text-navy"
                            matTooltip="The frozen prompt setup: system · technical · EMG versions. Rows sharing it saw byte-identical constants.">
                        {{ execution.prompt_configuration_label ?? '—' }}
                      </span>
                    </td>
                    <!--
                      What the model was actually shown. A matrix run and a
                      features run are different experiments, and averaging them
                      together is the easiest mistake this table could invite.
                    -->
                    <td class="px-3 py-1.5">
                      <span class="lab-chip bg-ink-100 text-ink-600"
                            [matTooltip]="inputTooltip(execution)">
                        @if (execution.matrix_rows_sent) {
                          {{ execution.dynamic_content ?? 'matrix' }}
                          <span class="lab-mono">· {{ execution.matrix_rows_sent }}r</span>
                        } @else {
                          envelope image
                        }
                      </span>
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
                  <tr><td colspan="14" class="px-4 py-8 text-center text-ink-500">
                    @if (store.loading()) {
                      Loading…
                    } @else if (store.error()) {
                      The record could not be loaded — see the error above.
                    } @else if (!store.executions().length) {
                      No executions recorded yet. Run one from the laboratory.
                    } @else {
                      {{ store.executions().length }} execution(s) loaded, but none
                      match the current filters.
                    }
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
    command_labelled: number; command_matched: number;
    command_accuracy: number | null;
  }): { label: string; value: string; note?: string; colour: string }[] {
    return [
      { label: 'Executions', value: String(stats.executions), colour: '#001F3F' },
      {
        label: 'Pass rate',
        value: stats.pass_rate === null ? '—' : `${(stats.pass_rate * 100).toFixed(0)}%`,
        note: 'cleared all seven stages',
        colour: (stats.pass_rate ?? 0) >= 0.8 ? '#001F3F' : '#D81B60',
      },
      {
        // Passing validation only means the command was well formed and safe.
        // Whether it was the *right* command is a separate question, and this
        // is the only card that answers it.
        //
        // The denominator is on the card, not just the rate: 100% of two runs
        // and 100% of two hundred are different claims, and a bare percentage
        // makes them look identical.
        label: 'Command accuracy',
        value: stats.command_accuracy === null
          ? '—'
          : `${(stats.command_accuracy * 100).toFixed(0)}%`,
        note: stats.command_labelled
          ? `${stats.command_matched}/${stats.command_labelled} labelled runs`
          : 'no expected commands set',
        colour: stats.command_accuracy === null
          ? '#4A657D'
          : stats.command_accuracy >= 0.8 ? '#001F3F' : '#D81B60',
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

  /**
   * Colour the produced command by whether it matched the answer key.
   *
   * Neutral when there was no key. Colouring an unlabelled run would assert a
   * verdict nobody gave.
   */
  protected matchTone(execution: Execution): string {
    const match = execution.metrics?.command_matches_expected;
    if (match === true) return 'text-navy font-semibold';
    if (match === false) return 'text-pink font-semibold';
    return 'text-ink-600';
  }

  /**
   * What the model was shown, for rows recorded under either flow.
   *
   * The history is mixed and has to stay readable: executions from the text
   * flow are still in the table, and relabelling them as image runs would be a
   * lie in the one column whose job is to say what the model saw. New runs
   * write 'features' with no row count, so they fall through to the last case.
   */
  protected inputTooltip(execution: Execution): string {
    const rows = execution.matrix_rows_sent;
    if (rows) {
      return execution.dynamic_content === 'both'
        ? `Text flow: the raw matrix (${rows} rows) and the derived descriptors.`
        : `Text flow: ${rows} rows of raw EMG as text.`;
    }
    if (execution.dynamic_content === 'semantic') {
      return 'Text flow: a serialised semantic state, not the signal.';
    }
    return 'The model saw a plot of the EMG window and the descriptors taken from it.';
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
