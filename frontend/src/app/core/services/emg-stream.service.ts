import { Injectable, signal } from '@angular/core';

import { environment } from '@env/environment';
import { EmgWindow } from '../models/emg.model';

type StreamState = 'idle' | 'connecting' | 'open' | 'closed' | 'error';

/**
 * Live EMG ingestion channel.
 *
 * Backs the manual/live toggle: in live mode the acquisition hardware (or a
 * bridge process) pushes 8-channel windows here, and the backend can be told to
 * launch an execution per frame using the pinned configuration.
 */
@Injectable({ providedIn: 'root' })
export class EmgStreamService {
  readonly state = signal<StreamState>('idle');
  readonly lastWindow = signal<EmgWindow | null>(null);
  readonly framesReceived = signal(0);
  readonly executionsTriggered = signal(0);
  readonly lastError = signal<string | null>(null);
  readonly sessionKey = signal<string>('');

  private socket: WebSocket | null = null;

  connect(sessionKey: string, config: {
    samplingConfigurationId: string | null;
    handedness: string;
    autoRun: boolean;
    subjectRef?: string | null;
    limitProfile?: string | null;
    experimentId?: string | null;
  }): void {
    this.disconnect();
    this.sessionKey.set(sessionKey);
    this.state.set('connecting');

    this.socket = new WebSocket(`${environment.wsBase}/ws/emg/${sessionKey}`);

    this.socket.onopen = () => {
      this.state.set('open');
      this.socket?.send(JSON.stringify({
        type: 'configure',
        sampling_configuration_id: config.samplingConfigurationId,
        handedness: config.handedness,
        auto_run: config.autoRun,
        subject_ref: config.subjectRef ?? null,
        limit_profile: config.limitProfile ?? null,
        experiment_id: config.experimentId ?? null,
      }));
    };

    this.socket.onmessage = (event) => {
      let payload: Record<string, unknown>;
      try {
        payload = JSON.parse(event.data as string);
      } catch {
        return;
      }
      switch (payload['type']) {
        case 'frame_ack':
          this.framesReceived.update((n) => n + 1);
          break;
        case 'execution_result':
          this.executionsTriggered.update((n) => n + 1);
          break;
        case 'error':
          this.lastError.set(String(payload['detail'] ?? 'Unknown stream error.'));
          break;
      }
    };

    this.socket.onerror = () => this.state.set('error');
    this.socket.onclose = () => this.state.set('closed');
  }

  /** Forward a window captured locally (e.g. from a serial bridge in the page). */
  push(window: EmgWindow, sequence: number, autoRun: boolean): void {
    if (this.socket?.readyState !== WebSocket.OPEN) return;
    this.lastWindow.set(window);
    this.socket.send(JSON.stringify({
      session_id: this.sessionKey(),
      sequence,
      window,
      auto_run: autoRun,
    }));
  }

  disconnect(): void {
    this.socket?.close();
    this.socket = null;
    this.state.set('idle');
  }
}
