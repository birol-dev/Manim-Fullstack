import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

import { FakeWebSocket } from "./fakeSocket";

globalThis.WebSocket = FakeWebSocket as unknown as typeof WebSocket;

// findBy*/waitFor give up after 1 s by default, which a loaded CI box can exceed while
// the App re-renders. 5 s still fails fast on a real bug, well inside testTimeout.
configure({ asyncUtilTimeout: 5_000 });

Object.defineProperty(window, "matchMedia", {
  writable: true,
  configurable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

globalThis.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// Radix UI relies on these in pointer interactions.
window.HTMLElement.prototype.scrollIntoView = () => {};
window.HTMLElement.prototype.hasPointerCapture = () => false;
window.HTMLElement.prototype.setPointerCapture = () => {};
window.HTMLElement.prototype.releasePointerCapture = () => {};

window.HTMLMediaElement.prototype.play = () => Promise.resolve();
window.HTMLMediaElement.prototype.pause = () => {};
window.HTMLMediaElement.prototype.load = () => {};

URL.createObjectURL = () => "blob:http://localhost/render";
URL.revokeObjectURL = () => {};

Object.defineProperty(navigator, "clipboard", {
  configurable: true,
  value: { writeText: vi.fn(() => Promise.resolve()) },
});

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  FakeWebSocket.reset();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
