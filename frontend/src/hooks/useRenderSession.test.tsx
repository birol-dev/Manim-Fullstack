import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FakeWebSocket } from "@/test/fakeSocket";
import { useRenderSession, type RenderRequest } from "./useRenderSession";

const REQUEST: RenderRequest = { filename: "a.py", scene: "A", quality: "l", useOpenGL: false, downloadOnly: false };

function setup() {
  const log = vi.fn();
  const onOutput = vi.fn();
  const onFinished = vi.fn();
  const hook = renderHook(() => useRenderSession({ log, onOutput, onFinished }));
  return { ...hook, log, onOutput, onFinished };
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
  });
}

afterEach(() => {
  vi.useRealTimers();
});

describe("useRenderSession", () => {
  it("connects, streams events, and finishes on result", async () => {
    const { result, log, onOutput, onFinished } = setup();
    await flush();
    expect(result.current.connection).toBe("open");

    let id: string | null = null;
    act(() => {
      id = result.current.start(REQUEST);
    });
    const socket = FakeWebSocket.latest();
    expect(socket.lastSent("start")).toMatchObject({ id, filename: "a.py", scene: "A", quality: "l" });
    // Only one render at a time.
    expect(result.current.start(REQUEST)).toBeNull();

    act(() => {
      socket.emit({ type: "info", render_id: id, message: "$ manim a.py A -ql" });
      socket.emit({ type: "info", render_id: id, message: "Stopping" });
      socket.emit({ type: "log", render_id: id, stream: "stderr", message: "warn" });
      socket.emit({ type: "log", render_id: id, stream: "stdout", message: "out" });
      socket.emit({ type: "latex_error_warning", render_id: id, message: "latex!" });
      socket.emit({ type: "progress", render_id: id, percent: 30, animation: 1, label: "Write" });
      socket.emit({ type: "file_ready", render_id: id, url: "/media/x.png", kind: "image", filename: "x.png", rel_path: "media/x.png" });
      socket.emit({ type: "status", render_id: id, status: "success", message: "done" });
    });
    expect(result.current.active?.progress).toEqual({ percent: 30, animation: 1, label: "Write" });
    expect(log.mock.calls.map(([level]) => level)).toEqual(["command", "info", "stderr", "stdout", "warning", "success"]);
    expect(onOutput).toHaveBeenCalledWith(
      { url: "/media/x.png", kind: "image", filename: "x.png", relPath: "media/x.png", temporary: false },
      expect.objectContaining({ id }),
    );

    act(() => socket.emit({ type: "result", render_id: id, success: true, status: "success" }));
    expect(result.current.active).toBeNull();
    expect(onFinished).toHaveBeenCalledWith(expect.objectContaining({ success: true, status: "success", output: expect.any(Object) }));
  });

  it("ignores stale events and malformed frames", async () => {
    const { result, onFinished, log } = setup();
    await flush();
    act(() => void result.current.start(REQUEST));
    const socket = FakeWebSocket.latest();

    act(() => {
      socket.emit({ type: "result", render_id: "someone-else", success: true });
      socket.onmessage?.(new MessageEvent("message", { data: "not json" }));
    });
    expect(result.current.active).not.toBeNull();
    expect(onFinished).not.toHaveBeenCalled();

    // Errors that aren't tied to a render end it immediately.
    act(() => socket.emit({ type: "error", message: "Server WebSocket error" }));
    expect(log).toHaveBeenCalledWith("error", "Server WebSocket error");
    expect(onFinished).toHaveBeenCalledWith(expect.objectContaining({ success: false, status: "error" }));
  });

  it("cancels over the socket, or locally when disconnected", async () => {
    const { result, onFinished } = setup();
    await flush();
    act(() => void result.current.start(REQUEST));
    const socket = FakeWebSocket.latest();

    act(() => result.current.cancel());
    expect(socket.lastSent().type).toBe("cancel");
    expect(result.current.active).not.toBeNull();

    act(() => socket.close());
    expect(onFinished).toHaveBeenCalledWith(expect.objectContaining({ status: "disconnected" }));
    expect(result.current.connection).toBe("closed");

    // No connection: cancelling a queued render finishes it right away.
    FakeWebSocket.autoOpen = false;
    act(() => void result.current.start(REQUEST));
    act(() => result.current.cancel());
    expect(onFinished).toHaveBeenLastCalledWith(expect.objectContaining({ status: "cancelled" }));
    act(() => result.current.cancel());
  });

  it("queues a render until the socket opens", async () => {
    FakeWebSocket.autoOpen = false;
    const { result } = setup();
    expect(result.current.connection).toBe("connecting");
    act(() => void result.current.start(REQUEST));
    const socket = FakeWebSocket.latest();
    expect(socket.sent).toHaveLength(0);

    act(() => socket.open());
    expect(socket.lastSent("start")).toMatchObject({ scene: "A" });
  });

  it("gives up on a render when no connection comes up", async () => {
    vi.useFakeTimers();
    FakeWebSocket.autoOpen = false;
    const { result, log, onFinished } = setup();
    act(() => void result.current.start(REQUEST));

    act(() => vi.advanceTimersByTime(8000));
    expect(log).toHaveBeenCalledWith("error", expect.stringContaining("Couldn't reach the render server"));
    expect(onFinished).toHaveBeenCalledWith(expect.objectContaining({ status: "offline" }));
  });

  it("reconnects with backoff after the connection drops", async () => {
    vi.useFakeTimers();
    const { result, unmount } = setup();
    await act(async () => {
      await vi.runOnlyPendingTimersAsync();
    });
    expect(result.current.connection).toBe("open");

    act(() => FakeWebSocket.latest().close());
    expect(result.current.connection).toBe("closed");
    const before = FakeWebSocket.instances.length;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(600);
    });
    expect(FakeWebSocket.instances.length).toBe(before + 1);
    expect(result.current.connection).toBe("open");

    act(() => result.current.reconnect());
    unmount();
    expect(FakeWebSocket.latest().readyState).toBe(FakeWebSocket.CLOSED);
  });
});
