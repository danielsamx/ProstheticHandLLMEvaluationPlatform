import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../api/api.service';
import { Execution, ExecutionStats, PromptConfiguration } from '../models/llm.model';

/**
 * State for the reading surface.
 *
 * Separate from `LabStore` on purpose: the laboratory holds the *next*
 * experiment's configuration, the dashboard holds the record of past ones.
 * Merging them would put a filter on a table in the same object as the
 * temperature about to be sent to a model.
 */
@Injectable({ providedIn: 'root' })
export class DashboardStore {
  private readonly api = inject(ApiService);

  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  readonly stats = signal<ExecutionStats | null>(null);
  readonly executions = signal<Execution[]>([]);

  /**
   * The distinct prompt setups, newest first.
   *
   * Deduplicated by the backend at write time, so this is already the answer
   * to "how many different setups have I tried" — no grouping happens here.
   */
  readonly configurations = signal<PromptConfiguration[]>([]);

  /** Days back; 0 means all time. */
  readonly window = signal(0);
  readonly statusFilter = signal<'passed' | 'failed' | 'error' | null>(null);
  readonly modelFilter = signal('');

  /**
   * Filtering happens client-side; aggregates do not.
   *
   * The table shows a page, so filtering it locally is honest. The headline
   * numbers come from the database over the whole period, because aggregating
   * whatever rows happen to be loaded reports a different figure every time the
   * page size changes.
   */
  readonly filtered = computed(() => {
    const status = this.statusFilter();
    const model = this.modelFilter().trim().toLowerCase();

    return this.executions().filter((execution) => {
      if (model && !(execution.litellm_model ?? '').toLowerCase().includes(model)) {
        return false;
      }
      if (!status) return true;
      const isError = execution.status === 'provider_error' || execution.status === 'timeout';
      if (status === 'error') return isError;
      if (status === 'passed') return execution.validation_passed === true;
      return !isError && execution.validation_passed === false;
    });
  });

  private since(): string | undefined {
    const days = this.window();
    if (!days) return undefined;
    return new Date(Date.now() - days * 86_400_000).toISOString();
  }

  async refresh(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const [stats, executions, configurations] = await Promise.all([
        firstValueFrom(this.api.executionStats(this.since())),
        firstValueFrom(this.api.listExecutions(500)),
        firstValueFrom(this.api.listPromptConfigurations()),
      ]);
      this.stats.set(stats);
      this.executions.set(executions);
      this.configurations.set(configurations);
    } catch (err) {
      this.error.set(err instanceof Error ? err.message : String(err));
    } finally {
      this.loading.set(false);
    }
  }

  async setWindow(days: number): Promise<void> {
    this.window.set(days);
    await this.refresh();
  }

  /**
   * Download the record for analysis.
   *
   * Failures are included, and the export is triggered from the browser rather
   * than assembled here so the CSV the researcher gets is byte-identical to the
   * one the API produces.
   */
  async exportCsv(): Promise<void> {
    try {
      const blob = await firstValueFrom(this.api.exportExecutionsCsv({ since: this.since() }));
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `executions-${new Date().toISOString().slice(0, 10)}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      this.error.set(err instanceof Error ? err.message : String(err));
    }
  }
}
