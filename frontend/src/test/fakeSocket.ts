/** Minimal WebSocket stand-in that tests can drive from the "server" side. */
export class FakeWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  static instances: FakeWebSocket[] = [];
  /** When false, new sockets stay in CONNECTING until open() is called. */
  static autoOpen = true;

  static reset() {
    FakeWebSocket.instances = [];
    FakeWebSocket.autoOpen = true;
  }

  static latest(): FakeWebSocket {
    const socket = FakeWebSocket.instances.at(-1);
    if (!socket) throw new Error("No WebSocket was created");
    return socket;
  }

  readonly url: string;
  readyState = FakeWebSocket.CONNECTING;
  sent: Array<Record<string, unknown>> = [];
  onopen: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
    if (FakeWebSocket.autoOpen) queueMicrotask(() => this.open());
  }

  open() {
    if (this.readyState !== FakeWebSocket.CONNECTING) return;
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.(new Event("open"));
  }

  send(data: string) {
    this.sent.push(JSON.parse(data));
  }

  close() {
    if (this.readyState === FakeWebSocket.CLOSED) return;
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.(new CloseEvent("close"));
  }

  /** Deliver a server event to the client. */
  emit(event: Record<string, unknown>) {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(event) }));
  }

  lastSent(type?: string): Record<string, unknown> {
    const matching = type ? this.sent.filter((message) => message.type === type) : this.sent;
    const message = matching.at(-1);
    if (!message) throw new Error(`Nothing sent${type ? ` of type ${type}` : ""}`);
    return message;
  }
}
