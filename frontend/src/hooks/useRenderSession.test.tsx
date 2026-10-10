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

    // The server names the render an error belongs to (#18); one with no render_id is about a
    // malformed message or the connection, so it is logged and the running render goes on.
    act(() => socket.emit({ type: "error", render_id: null, message: "Message payload must be a JSON object." }));
    expect(log).toHaveBeenCalledWith("error", "Message payload must be a JSON object.");
    expect(result.current.active).not.toBeNull();
    expect(onFinished).not.toHaveBeenCalled();
  });

  it("attaches error events to the render their render_id names", async () => {
    const { result, onFinished, log } = setup();
    await flush();
    let first: string | null = null;
    act(() => {
      first = result.current.start(REQUEST);
    });
    const socket = FakeWebSocket.latest();

    // Another render's error: not logged, doesn't end this one.
    act(() => socket.emit({ type: "error", render_id: "someone-else", message: "Render execution error: other" }));
    expect(log).not.toHaveBeenCalledWith("error", "Render execution error: other");
    expect(result.current.active?.id).toBe(first);

    // This render's error is logged; its result (always sent after it) ends the render.
    act(() => socket.emit({ type: "error", render_id: first, message: "Python script not found." }));
    expect(log).toHaveBeenCalledWith("error", "Python script not found.");
    expect(result.current.active).not.toBeNull();
    act(() => socket.emit({ type: "result", render_id: first, success: false, status: "rejected" }));
    expect(onFinished).toHaveBeenCalledWith(expect.objectContaining({ id: first, success: false, status: "rejected" }));

    // The socket failing as that render stopped: the error names it after its result. Still its log.
    act(() => socket.emit({ type: "error", render_id: first, message: "Server WebSocket error: boom" }));
    expect(log).toHaveBeenCalledWith("error", "Server WebSocket error: boom");

    // Once a newer render runs, a late error from the old one isn't mixed into the new log.
    let second: string | null = null;
    act(() => {
      second = result.current.start(REQUEST);
    });
    expect(second).not.toBe(first);
    log.mockClear();
    act(() => socket.emit({ type: "error", render_id: first, message: "late" }));
    expect(log).not.toHaveBeenCalled();
    expect(result.current.active?.id).toBe(second);
    expect(onFinished).toHaveBeenCalledTimes(1);
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
