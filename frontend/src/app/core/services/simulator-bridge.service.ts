import { Injectable, signal } from '@angular/core';

import { environment } from '@env/environment';
import { MovementFrame, RejectionFrame } from '../models/hand.model';

type SocketState = 'idle' | 'connecting' | 'open' | 'closed' | 'error';

/**
 * Read-only WebSocket feed of validated movements.
 *
 * The simulator has no manual controls by design: it renders only what this
 * bridge delivers, and the backend only publishes poses that cleared all seven
 * validation stages. An unsafe pose is therefore unrenderable, not merely
 * discouraged.
 */
@Injectable({ providedIn: 'root' })
export class SimulatorBridgeService {
  readonly state = signal<SocketState>('idle');
  readonly lastMovement = signal<MovementFrame | null>(null);
  readonly lastRejection = signal<RejectionFrame | null>(null);
  readonly receivedCount = signal(0);

  private socket: WebSocket | null = null;
  private heartbeat?: ReturnType<typeof setInterval>;
  private reconnectDelay = 1_000;

  connect(): void {
    if (this.socket && this.socket.readyState <= WebSocket.OPEN) return;

    this.state.set('connecting');
    this.socket = new WebSocket(`${environment.wsBase}/ws/simulator`);

    this.socket.onopen = () => {
      this.state.set('open');
      this.reconnectDelay = 1_000;
      this.heartbeat = setInterval(() => this.socket?.send('ping'), 25_000);
    };

    this.socket.onmessage = (event) => {
      let payload: unknown;
      try {
        payload = JSON.parse(event.data as string);
      } catch {
        return;
      }
      const frame = payload as { type?: string };
      if (frame.type === 'movement') {
        this.lastMovement.set(payload as MovementFrame);
        this.lastRejection.set(null);
        this.receivedCount.update((n) => n + 1);
      } else if (frame.type === 'rejected') {
        this.lastRejection.set(payload as RejectionFrame);
      }
    };

    this.socket.onerror = () => this.state.set('error');

    this.socket.onclose = () => {
      this.state.set('closed');
      clearInterval(this.heartbeat);
      // Exponential backoff, capped: a research workstation may sleep.
      setTimeout(() => this.connect(), this.reconnectDelay);
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, 30_000);
    };
  }

  disconnect(): void {
    clearInterval(this.heartbeat);
    this.socket?.close();
    this.socket = null;
    this.state.set('idle');
  }

  /** Push a locally-produced frame (used when a run returns over HTTP). */
  emitLocal(frame: MovementFrame): void {
    this.lastMovement.set(frame);
    this.lastRejection.set(null);
    this.receivedCount.update((n) => n + 1);
  }
}
