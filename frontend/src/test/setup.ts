import "@testing-library/jest-dom/vitest";
import { vi, beforeEach, afterEach } from "vitest";

// Mock WebSocket class
export class MockWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  readonly CONNECTING = 0;
  readonly OPEN = 1;
  readonly CLOSING = 2;
  readonly CLOSED = 3;

  static instances: MockWebSocket[] = [];
  url: string;
  private _onopen: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  readyState = 1;
  sentMessages: string[] = [];

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  get onopen() {
    return this._onopen;
  }

  set onopen(callback: ((event: Event) => void) | null) {
    this._onopen = callback;
    if (callback) {
      queueMicrotask(() => {
        if (this._onopen === callback) {
          callback(new Event("open"));
        }
      });
    }
  }

  send(data: string) {
    this.sentMessages.push(data);
  }

  close() {
    this.readyState = MockWebSocket.CLOSED;
    if (this.onclose) this.onclose(new CloseEvent("close"));
  }

  emitMessage(data: unknown) {
    if (this.onmessage) {
      this.onmessage(
        new MessageEvent("message", {
          data: typeof data === "string" ? data : JSON.stringify(data),
        })
      );
    }
  }
}

globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket;
(window as unknown as { WebSocket: unknown }).WebSocket = MockWebSocket;

// Mock matchMedia
Object.defineProperty(window, "matchMedia", {
  writable: true,
  configurable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Mock ResizeObserver
globalThis.ResizeObserver = class ResizeObserver {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
};

// Polyfill scrollIntoView and PointerCapture for Radix UI in jsdom
window.HTMLElement.prototype.scrollIntoView = vi.fn();
window.HTMLElement.prototype.hasPointerCapture = vi.fn(() => false);
window.HTMLElement.prototype.setPointerCapture = vi.fn();
window.HTMLElement.prototype.releasePointerCapture = vi.fn();

// Mock URL.createObjectURL and URL.revokeObjectURL
if (typeof URL.createObjectURL === "undefined") {
  URL.createObjectURL = vi.fn(() => "blob:http://localhost:5173/mock-blob-url");
} else {
  vi.spyOn(URL, "createObjectURL").mockImplementation(() => "blob:http://localhost:5173/mock-blob-url");
}

if (typeof URL.revokeObjectURL === "undefined") {
  URL.revokeObjectURL = vi.fn();
} else {
  vi.spyOn(URL, "revokeObjectURL").mockImplementation(vi.fn());
}

// Mock HTMLMediaElement methods
window.HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
window.HTMLMediaElement.prototype.pause = vi.fn();
window.HTMLMediaElement.prototype.load = vi.fn();

// Mock window.scrollTo
window.scrollTo = vi.fn();

// Reset mocks between tests
beforeEach(() => {
  localStorage.clear();
  MockWebSocket.instances = [];
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});
