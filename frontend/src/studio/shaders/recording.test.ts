import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { recordCanvas, recordingType } from "./recording";

vi.mock("@fix-webm-duration/fix", () => ({ fixWebmDuration: vi.fn(async (blob: Blob) => blob) }));

const stopTrack = vi.fn();
class FakeRecorder {
  static instances: FakeRecorder[] = [];
  static isTypeSupported = (type: string) => type === "video/webm;codecs=vp8";
  state = "inactive";
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onerror: (() => void) | null = null;
  onstop: (() => void) | null = null;
  constructor() { FakeRecorder.instances.push(this); }
  start() { this.state = "recording"; }
  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["video-frame"]) });
    this.onstop?.();
  }
}

beforeEach(() => {
  vi.useFakeTimers();
  stopTrack.mockClear();
  FakeRecorder.instances = [];
  vi.stubGlobal("MediaRecorder", FakeRecorder);
  Object.defineProperty(HTMLCanvasElement.prototype, "captureStream", { configurable: true, value: vi.fn(() => ({ getTracks: () => [{ stop: stopTrack }] })) });
});
afterEach(() => {
  vi.useRealTimers(); vi.unstubAllGlobals();
  Reflect.deleteProperty(HTMLCanvasElement.prototype, "captureStream");
});

describe("video recording", () => {
  it("uses a supported codec, reports progress, and releases the stream on completion", async () => {
    expect(recordingType()).toBe("video/webm;codecs=vp8");
    const progress = vi.fn();
    const promise = recordCanvas(document.createElement("canvas"), 3, new AbortController().signal, progress);
    await vi.advanceTimersByTimeAsync(3000);
    const blob = await promise;
    expect(blob.type).toBe("video/webm");
    expect(blob.size).toBeGreaterThan(0);
    expect(progress).toHaveBeenCalled();
    expect(stopTrack).toHaveBeenCalledOnce();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("cancels a recording without leaving live tracks or timers", async () => {
    const abort = new AbortController();
    const promise = recordCanvas(document.createElement("canvas"), 10, abort.signal, vi.fn());
    const rejected = expect(promise).rejects.toThrow("cancelled");
    abort.abort();
    await rejected;
    expect(stopTrack).toHaveBeenCalledOnce();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("cleans up on recording errors and rejects unsupported browsers", async () => {
    const promise = recordCanvas(document.createElement("canvas"), 5, new AbortController().signal, vi.fn());
    const rejected = expect(promise).rejects.toThrow("Couldn't record");
    FakeRecorder.instances.at(-1)!.onerror?.();
    await rejected;
    expect(stopTrack).toHaveBeenCalledOnce();
    expect(vi.getTimerCount()).toBe(0);
    vi.stubGlobal("MediaRecorder", undefined);
    await expect(recordCanvas(document.createElement("canvas"), 5, new AbortController().signal, vi.fn())).rejects.toThrow("isn't supported");
  });
});
