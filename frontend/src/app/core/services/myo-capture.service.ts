import { Injectable, signal } from '@angular/core';

const MYO_CONTROL = 'd5060001-a904-deb9-4748-2c7f4a124842';
const MYO_EMG_SERVICE = 'd5060005-a904-deb9-4748-2c7f4a124842';
const MYO_EMG_CHARACTERISTICS = [1, 2, 3, 4].map(n => `d5060${n}05-a904-deb9-4748-2c7f4a124842`);

@Injectable({ providedIn: 'root' })
export class MyoCaptureService {
  readonly state = signal<'idle' | 'connecting' | 'streaming' | 'error'>('idle');
  readonly samples = signal<number[][]>([]); readonly error = signal<string | null>(null);
  private device: BluetoothDevice | null = null;

  async connect(): Promise<void> {
    if (!('bluetooth' in navigator)) throw new Error('Web Bluetooth requires Chrome or Edge.');
    this.state.set('connecting'); this.error.set(null);
    try {
      this.device = await navigator.bluetooth.requestDevice({
        filters: [{ namePrefix: 'Myo' }], optionalServices: [MYO_CONTROL, MYO_EMG_SERVICE],
      });
      const server = await this.device.gatt!.connect();
      const service = await server.getPrimaryService(MYO_EMG_SERVICE);
      for (const uuid of MYO_EMG_CHARACTERISTICS) {
        const characteristic = await service.getCharacteristic(uuid);
        await characteristic.startNotifications();
        characteristic.addEventListener('characteristicvaluechanged', event => this.onFrame(event));
      }
      this.state.set('streaming');
    } catch (error) { this.state.set('error'); this.error.set(error instanceof Error ? error.message : String(error)); throw error; }
  }

  private onFrame(event: Event): void {
    const value = (event.target as BluetoothRemoteGATTCharacteristic).value;
    if (!value) return;
    const rows: number[][] = [];
    for (let offset = 0; offset + 7 < value.byteLength; offset += 8) {
      rows.push(Array.from({ length: 8 }, (_, channel) => value.getInt8(offset + channel)));
    }
    this.samples.update(current => [...current, ...rows].slice(-2000));
  }
  clear(): void { this.samples.set([]); }
  disconnect(): void { this.device?.gatt?.disconnect(); this.device = null; this.state.set('idle'); }
}
