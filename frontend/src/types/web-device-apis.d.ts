/**
 * Minimal ambient types for the two browser device APIs used to reach the
 * prosthesis.
 *
 * Declared here rather than pulled in as `@types/w3c-web-serial` and
 * `@types/web-bluetooth` on purpose: this file covers exactly the surface
 * `ProsthesisLinkService` touches, in about eighty lines, and it means the
 * build has no dependency that exists only to describe four method calls. If
 * the service ever needs more of either API, adding the packages becomes the
 * better trade — but it is not the trade today.
 *
 * Both APIs are Chromium-only and both require a user gesture and an explicit
 * device selection by the user. Neither can be used to enumerate or connect to
 * hardware silently.
 */

// ── Web Serial ──────────────────────────────────────────────────────────────
// The transport that actually works with this hardware. Bluetooth SPP is
// Bluetooth Classic, which Web Bluetooth cannot reach; but once the OS has
// paired the prosthesis, SPP surfaces as a virtual serial port and this API can
// open it at the documented 115200 baud.

interface SerialPortInfo {
  usbVendorId?: number;
  usbProductId?: number;
}

interface SerialOptions {
  baudRate: number;
  dataBits?: 7 | 8;
  stopBits?: 1 | 2;
  parity?: 'none' | 'even' | 'odd';
  bufferSize?: number;
  flowControl?: 'none' | 'hardware';
}

interface SerialPort {
  readonly readable: ReadableStream<Uint8Array> | null;
  readonly writable: WritableStream<Uint8Array> | null;
  /** Settles when the port closes — including when the device goes out of range. */
  readonly closed?: Promise<void>;
  open(options: SerialOptions): Promise<void>;
  close(): Promise<void>;
  getInfo?(): SerialPortInfo;
}

interface Serial {
  /** Opens the browser's port chooser. Requires a user gesture. */
  requestPort(options?: { filters?: SerialPortInfo[] }): Promise<SerialPort>;
  /** Ports the user has already granted access to in this origin. */
  getPorts(): Promise<SerialPort[]>;
}

// ── Web Bluetooth ───────────────────────────────────────────────────────────
// Kept for firmware builds that expose a Nordic UART service over BLE instead
// of SPP. A genuine alternative rather than a fallback: a build either offers
// it or it does not.

interface BluetoothRemoteGATTCharacteristic extends EventTarget {
  readonly value?: DataView;
  startNotifications(): Promise<BluetoothRemoteGATTCharacteristic>;
  stopNotifications(): Promise<BluetoothRemoteGATTCharacteristic>;
  writeValue(value: BufferSource): Promise<void>;
  writeValueWithoutResponse(value: BufferSource): Promise<void>;
}

interface BluetoothRemoteGATTService {
  getCharacteristic(uuid: string): Promise<BluetoothRemoteGATTCharacteristic>;
}

interface BluetoothRemoteGATTServer {
  connect(): Promise<BluetoothRemoteGATTServer>;
  disconnect(): void;
  getPrimaryService(uuid: string): Promise<BluetoothRemoteGATTService>;
}

interface BluetoothDevice extends EventTarget {
  readonly id: string;
  readonly name?: string;
  readonly gatt?: BluetoothRemoteGATTServer;
}

interface Bluetooth {
  requestDevice(options: {
    filters?: { services?: string[]; name?: string; namePrefix?: string }[];
    optionalServices?: string[];
    acceptAllDevices?: boolean;
  }): Promise<BluetoothDevice>;
  getAvailability(): Promise<boolean>;
}

interface Navigator {
  readonly serial: Serial;
  readonly bluetooth: Bluetooth;
}
