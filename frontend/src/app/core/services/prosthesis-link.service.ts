import { Injectable, computed, signal } from '@angular/core';

import { MovementFrame } from '../models/hand.model';
import { EncoderTelemetry, MechanicalTelemetry } from '../api/api.service';

export type LinkState = 'unsupported' | 'disconnected' | 'connecting' | 'connected' | 'error';
export type LinkTransport = 'serial' | 'ble';

/** One transmission attempt, kept so the panel can show what actually went out. */
export interface LinkEvent {
  at: number;
  command: string;
  delivered: boolean;
  detail?: string;
}

/**
 * The physical link to the HANDi EPN V3.
 *
 * ## Why two transports, and why Serial is the real one
 *
 * The firmware speaks **Bluetooth SPP at 115200 baud** — and SPP is Bluetooth
 * *Classic*, not BLE. The Web Bluetooth API only reaches BLE GATT services, so
 * it cannot open an SPP socket at all. Any implementation built purely on Web
 * Bluetooth would fail against this hardware no matter how carefully it was
 * written.
 *
 * What does work: once the operating system has paired the prosthesis, SPP is
 * exposed as a virtual serial port, and the **Web Serial API** can open that
 * port at 115200 and write to it. That is the supported path here, and it
 * matches the documented protocol exactly.
 *
 * The BLE path is kept for firmware that exposes a Nordic UART service instead.
 * It is a genuine alternative, not a fallback: a build either offers NUS or it
 * does not, and picking the wrong one fails immediately rather than silently.
 *
 * ## What this service will and will not send
 *
 * It transmits only commands that already cleared the full validation
 * pipeline — it is fed from the simulator bridge, which the backend only
 * publishes to after all seven stages pass. There is no path from a raw model
 * response to this class, which is deliberate: the browser is the last place
 * that should be deciding whether a pose is safe to execute.
 *
 * The 50 ms minimum interval from the protocol specification is enforced here
 * as well as documented in the prompt. A model cannot violate it — it does not
 * control transmission timing — but a burst of repetitions or a reconnect
 * could, and the motor driver is the thing that would pay for it.
 */
@Injectable({ providedIn: 'root' })
export class ProsthesisLinkService {
  /** Minimum gap between writes, from the protocol spec. */
  private static readonly MIN_INTERVAL_MS = 50;

  /** Nordic UART service, for firmware builds that expose BLE instead of SPP. */
  private static readonly NUS_SERVICE = '6e400001-b5a3-f393-e0a9-e50e24dcca9e';
  private static readonly NUS_RX = '6e400002-b5a3-f393-e0a9-e50e24dcca9e';

  readonly state = signal<LinkState>('disconnected');
  readonly transport = signal<LinkTransport | null>(null);
  readonly deviceName = signal<string | null>(null);
  readonly error = signal<string | null>(null);
  readonly sentCount = signal(0);
  readonly recent = signal<LinkEvent[]>([]);
  readonly encoderTelemetry = signal<MechanicalTelemetry | null>(null);

  /**
   * True when a command would reach hardware.
   *
   * The whole point of the feature: when this is false the command still
   * reaches the simulator, so an experiment is never blocked by the absence of
   * a physical hand.
   */
  readonly connected = computed(() => this.state() === 'connected');

  private port: SerialPort | null = null;
  private writer: WritableStreamDefaultWriter<Uint8Array> | null = null;
  private reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
  private bleCharacteristic: BluetoothRemoteGATTCharacteristic | null = null;
  private lastSentAt = 0;

  /** Is a transport available in this browser at all? */
  supports(transport: LinkTransport): boolean {
    if (transport === 'serial') return 'serial' in navigator;
    return 'bluetooth' in navigator;
  }

  /**
   * Ask the user to pick a device.
   *
   * Both APIs require a user gesture and show the browser's own chooser; there
   * is no way to connect silently, and no way for this application to see
   * devices the user did not explicitly select. That is a property of the web
   * platform rather than a limitation of this code, and it is the right one
   * for something that drives a motor.
   */
  async connect(transport: LinkTransport = 'serial'): Promise<boolean> {
    if (!this.supports(transport)) {
      this.state.set('unsupported');
      this.error.set(
        transport === 'serial'
          ? 'This browser has no Web Serial API. Chrome or Edge on desktop is required.'
          : 'This browser has no Web Bluetooth API.',
      );
      return false;
    }

    this.state.set('connecting');
    this.error.set(null);

    try {
      if (transport === 'serial') {
        await this.connectSerial();
      } else {
        await this.connectBle();
      }
      this.transport.set(transport);
      this.state.set('connected');
      return true;
    } catch (err) {
      // A cancelled chooser is not an error worth shouting about: the user
      // decided not to connect, which is a normal outcome.
      const cancelled = err instanceof DOMException && err.name === 'NotFoundError';
      this.state.set(cancelled ? 'disconnected' : 'error');
      this.error.set(cancelled ? null : this.describe(err));
      await this.cleanup();
      return false;
    }
  }

  private async connectSerial(): Promise<void> {
    const port = await navigator.serial.requestPort();
    // 115200 8N1, exactly as the protocol section of the manual specifies.
    await port.open({ baudRate: 115200, dataBits: 8, stopBits: 1, parity: 'none' });

    this.port = port;
    this.writer = port.writable!.getWriter();
    if (port.readable) {
      this.reader = port.readable.getReader();
      void this.readSerialTelemetry();
    }

    const info = port.getInfo?.();
    this.deviceName.set(
      info?.usbProductId
        ? `Serial ${info.usbVendorId?.toString(16)}:${info.usbProductId.toString(16)}`
        : 'Bluetooth serial port',
    );

    // The OS closes the virtual port when the device drops out of range, and
    // the promise below settles at that moment. Without this the UI would go on
    // claiming a live link to a prosthesis that walked away.
    void port.closed?.then(() => this.handleDrop('The serial port closed.'));
  }

  private async connectBle(): Promise<void> {
    const device = await navigator.bluetooth.requestDevice({
      filters: [{ services: [ProsthesisLinkService.NUS_SERVICE] }],
      optionalServices: [ProsthesisLinkService.NUS_SERVICE],
    });

    device.addEventListener('gattserverdisconnected', () =>
      this.handleDrop('The prosthesis disconnected.'),
    );

    const server = await device.gatt!.connect();
    const service = await server.getPrimaryService(ProsthesisLinkService.NUS_SERVICE);
    this.bleCharacteristic = await service.getCharacteristic(ProsthesisLinkService.NUS_RX);
    this.deviceName.set(device.name ?? 'BLE device');
  }

  async disconnect(): Promise<void> {
    await this.cleanup();
    this.state.set('disconnected');
    this.transport.set(null);
    this.deviceName.set(null);
  }

  /**
   * Send a validated movement to the hardware.
   *
   * Returns whether it was delivered. A `false` is not a failure of the
   * experiment — it means no hand was attached, and the simulator has the
   * frame regardless.
   */
  async send(frame: MovementFrame): Promise<boolean> {
    const command = frame.serial_command?.trim();
    if (!command) return false;
    if (!this.connected()) {
      this.record(command, false, 'No device connected — simulator only.');
      return false;
    }

    // Respect the documented minimum interval. Repetition runs fire several
    // executions back to back, and the firmware's motor driver is what absorbs
    // the consequence of ignoring this.
    const wait = ProsthesisLinkService.MIN_INTERVAL_MS - (Date.now() - this.lastSentAt);
    if (wait > 0) await new Promise((resolve) => setTimeout(resolve, wait));

    // ASCII, uppercase, newline-terminated: the wire format from the manual.
    const payload = new TextEncoder().encode(`${command.toUpperCase()}\n`);

    try {
      if (this.transport() === 'serial') {
        await this.writer!.write(payload);
      } else {
        // writeValueWithoutResponse is deliberate: NUS RX is write-without-
        // response, and waiting for an acknowledgement the characteristic never
        // sends would stall every command.
        await this.bleCharacteristic!.writeValueWithoutResponse(payload);
      }
      this.lastSentAt = Date.now();
      this.sentCount.update((n) => n + 1);
      this.record(command, true);
      return true;
    } catch (err) {
      this.handleDrop(this.describe(err));
      this.record(command, false, this.describe(err));
      return false;
    }
  }

  /**
   * Return the hand to OPEN.
   *
   * The safety section requires this at the end of a session. Left in a closed
   * grip the tendons stay loaded, which is bad for the printed linkage and
   * worse for anything the hand is holding.
   */
  async releaseToOpen(): Promise<void> {
    if (!this.connected()) return;
    await this.send({ serial_command: 'O' } as MovementFrame);
  }

  /** Read newline-delimited encoder feedback from compatible firmware. */
  private async readSerialTelemetry(): Promise<void> {
    const decoder = new TextDecoder();
    let pending = '';
    try {
      while (this.reader) {
        const { value, done } = await this.reader.read();
        if (done) break;
        pending += decoder.decode(value, { stream: true });
        const lines = pending.split(/\r?\n/);
        pending = lines.pop() ?? '';
        for (const line of lines) this.acceptTelemetryLine(line.trim());
      }
    } catch (err) {
      if (this.state() === 'connected') this.handleDrop(this.describe(err));
    }
  }

  /** Accept JSON `{actuators:[...]}` or `ENC,name,pos,min,max,velocity`. */
  private acceptTelemetryLine(line: string): void {
    if (!line) return;
    const now = new Date().toISOString();
    let incoming: EncoderTelemetry[] = [];
    try {
      if (line.startsWith('{')) {
        const decoded = JSON.parse(line) as { actuators?: EncoderTelemetry[] };
        incoming = Array.isArray(decoded.actuators) ? decoded.actuators : [];
      } else if (line.startsWith('ENC,')) {
        const [, actuator, position, minimum, maximum, velocity = '0'] = line.split(',');
        incoming = [{ actuator, position: Number(position), minimum: Number(minimum),
          maximum: Number(maximum), velocity: Number(velocity), captured_at: now }];
      }
    } catch { return; }
    incoming = incoming.filter((item) => item.actuator &&
      [item.position, item.minimum, item.maximum, item.velocity].every(Number.isFinite) &&
      item.maximum > item.minimum).map((item) => ({ ...item, captured_at: item.captured_at || now }));
    if (!incoming.length) return;
    const merged = new Map((this.encoderTelemetry()?.actuators ?? []).map((item) => [item.actuator, item]));
    incoming.forEach((item) => merged.set(item.actuator, item));
    this.encoderTelemetry.set({ actuators: [...merged.values()], received_at: now,
      stale_after_ms: 500, stall_velocity_threshold: 0.01 });
  }

  private async cleanup(): Promise<void> {
    try {
      await this.reader?.cancel();
      this.reader?.releaseLock();
      this.writer?.releaseLock();
      await this.port?.close();
    } catch {
      // Already gone. Nothing to report: the goal was for it to be closed.
    }
    this.writer = null;
    this.reader = null;
    this.port = null;
    this.bleCharacteristic = null;
  }

  private handleDrop(reason: string): void {
    if (this.state() === 'disconnected') return;
    this.state.set('error');
    this.error.set(reason);
    void this.cleanup();
  }

  private record(command: string, delivered: boolean, detail?: string): void {
    this.recent.update((list) =>
      [{ at: Date.now(), command, delivered, detail }, ...list].slice(0, 20),
    );
  }

  private describe(err: unknown): string {
    if (err instanceof Error) return `${err.name}: ${err.message}`;
    return String(err);
  }
}
