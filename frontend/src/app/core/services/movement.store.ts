import { Injectable, inject, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../api/api.service';
import { ManualCommandResult, MovementLogEntry } from '../models/llm.model';
import { ProsthesisLinkService } from './prosthesis-link.service';

/**
 * Sending a command by hand, and reading the log of everything sent.
 *
 * The manual path exists to separate two failures that look identical from the
 * outside. When a run produces no movement, the cause is either the model's
 * answer or the plumbing — validator, WebSocket, serial link, firmware. Typing
 * `C` and watching the hand close settles that in one action, with no inference
 * in the way.
 *
 * It is not a shortcut around validation: the backend puts a typed command
 * through the same seven stages a model's answer goes through. The mechanical
 * stops do not care who chose the number, and a typo in a text field can strip
 * a gearmotor exactly as well as a bad model can.
 */
@Injectable({ providedIn: 'root' })
export class MovementStore {
  private readonly api = inject(ApiService);
  private readonly link = inject(ProsthesisLinkService);

  readonly sending = signal(false);
  readonly error = signal<string | null>(null);
  readonly lastResult = signal<ManualCommandResult | null>(null);

  readonly log = signal<MovementLogEntry[]>([]);
  readonly loadingLog = signal(false);
  readonly sourceFilter = signal<string | null>(null);

  /**
   * Validate, publish to the simulator, then transmit to the hardware.
   *
   * In that order, and not in parallel. The backend validates and renders; only
   * then does the browser put anything on the wire. A command that fails
   * validation must never reach a motor, and the only way to guarantee that is
   * for the transmission to happen after the verdict rather than alongside it.
   */
  async send(serialCommand: string, handedness: 'right' | 'left'): Promise<boolean> {
    this.sending.set(true);
    this.error.set(null);

    try {
      const result = await firstValueFrom(this.api.sendManualCommand({
        serial_command: serialCommand,
        handedness,
      }));
      this.lastResult.set(result);

      // The hardware, if a link is open. The backend cannot reach the serial
      // port — it lives in this browser — so delivery is confirmed back to the
      // log rather than assumed by whoever wrote the row.
      if (this.link.connected() && result.normalised_serial) {
        const delivered = await this.link.send({
          serial_command: result.normalised_serial,
        } as never);
        await firstValueFrom(this.api.confirmHardwareDelivery(
          result.id,
          (this.link.transport() ?? 'serial') as 'serial' | 'ble',
          delivered ? undefined : (this.link.error() ?? 'The write failed.'),
        ));
      }

      await this.refreshLog();
      return true;
    } catch (err) {
      this.error.set(this.describe(err));
      return false;
    } finally {
      this.sending.set(false);
    }
  }

  async refreshLog(): Promise<void> {
    this.loadingLog.set(true);
    try {
      const entries = await firstValueFrom(
        this.api.movementLog(300, this.sourceFilter() ?? undefined),
      );
      this.log.set(entries);
    } catch (err) {
      this.error.set(this.describe(err));
    } finally {
      this.loadingLog.set(false);
    }
  }

  async setSourceFilter(source: string | null): Promise<void> {
    this.sourceFilter.set(source);
    await this.refreshLog();
  }

  /**
   * A rejected command arrives as a 400 with the validator's own message, which
   * already names the actuator, the value and the profile that refused it.
   * `HttpErrorResponse` does not extend `Error`, so a plain `instanceof Error`
   * check falls through to `String(err)` and prints "[object Object]".
   */
  private describe(err: unknown): string {
    if (err instanceof HttpErrorResponse) {
      const detail = (err.error as { detail?: string } | null)?.detail;
      return detail ?? err.message ?? `HTTP ${err.status}`;
    }
    if (err instanceof Error) return err.message;
    return String(err);
  }
}
