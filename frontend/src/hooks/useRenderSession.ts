import { useCallback, useEffect, useRef, useState } from "react";

import { wsUrl } from "@/lib/api";
import type { OutputKind, Quality } from "@/lib/types";
import type { LogLevel } from "./useLogs";

export type ConnectionState = "connecting" | "open" | "closed";

export interface RenderRequest {
  filename: string;
  scene: string;
  quality: Quality;
  useOpenGL: boolean;
  downloadOnly: boolean;
  /** Code to render instead of the file on disk (unsaved buffer or browser storage). */
  code?: string;
}

export interface RenderProgress {
  percent: number;
  /** Zero-based index of the play()/wait() call Manim is rendering. */
  animation?: number;
  label?: string;
}

export interface ActiveRender {
  id: string;
  request: RenderRequest;
  progress: RenderProgress | null;
  startedAt: number;
  /** Waiting for another render (any tab) to finish; Manim hasn't started yet. */
  queued?: boolean;
}

export interface RenderOutput {
  /** Backend path, e.g. "/media/videos/example/480p15/Intro.mp4". */
  url: string;
  kind: OutputKind;
  filename: string;
  relPath: string;
  /** Download-only output that the server deletes after it is fetched once. */
  temporary: boolean;
}

export interface RenderOutcome {
  id: string;
  request: RenderRequest;
  success: boolean;
  status: string;
  output: RenderOutput | null;
  durationMs: number;
}

interface ServerEvent {
  type: string;
  render_id?: string | number | null;
  message?: string;
  stream?: string;
  status?: string;
  percent?: number;
  animation?: number;
  label?: string;
  filename?: string;
  rel_path?: string;
  url?: string;
  kind?: OutputKind;
  is_temp_download?: boolean;
  success?: boolean;
}

interface Options {
  log: (level: LogLevel, text: string) => void;
  onOutput: (output: RenderOutput, render: ActiveRender) => void;
  onFinished: (outcome: RenderOutcome) => void;
}

/** The server's notice that a render waits for the render slot. */
export const QUEUED_MESSAGE_PREFIX = "Waiting for another render";

const RECONNECT_DELAYS_MS = [500, 1000, 2000, 4000, 8000];
const CONNECT_TIMEOUT_MS = 8000;

function makeId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

/** WebSocket connection to /api/render with automatic reconnects. */
export function useRenderSession({ log, onOutput, onFinished }: Options) {
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [active, setActive] = useState<ActiveRender | null>(null);
  const [stopping, setStopping] = useState(false);

  const socketRef = useRef<WebSocket | null>(null);
  const activeRef = useRef<ActiveRender | null>(null);
  const outputRef = useRef<RenderOutput | null>(null);
  const queueRef = useRef<string[]>([]);
  const attemptRef = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(false);
  const connectRef = useRef<() => void>(() => {});
  const callbacks = useRef({ log, onOutput, onFinished });
  useEffect(() => {
    callbacks.current = { log, onOutput, onFinished };
  });

  const updateActive = useCallback((render: ActiveRender | null) => {
    activeRef.current = render;
    setActive(render);
  }, []);

  const finish = useCallback(
    (success: boolean, status: string) => {
      const render = activeRef.current;
      if (!render) return;
      setStopping(false);
      updateActive(null);
      const output = outputRef.current;
      outputRef.current = null;
      callbacks.current.onFinished({
        id: render.id,
        request: render.request,
        success,
        status,
        output,
        durationMs: Date.now() - render.startedAt,
      });
    },
    [updateActive],
  );

  const handleEvent = useCallback(
    (event: ServerEvent) => {
      const render = activeRef.current;
      const { log } = callbacks.current;
      // Events from a render we already gave up on.
      if (event.render_id != null && event.render_id !== render?.id) return;

      // Queued until the server says anything else about this render (the "$ manim" line, logs...).
      if (render && event.render_id === render.id) {
        const queued = event.type === "info" && (event.message ?? "").startsWith(QUEUED_MESSAGE_PREFIX);
        if (queued !== Boolean(render.queued)) updateActive({ ...render, queued });
      }

      switch (event.type) {
        case "log":
          log(event.stream === "stderr" ? "stderr" : "stdout", event.message ?? "");
          break;
        case "info": {
          const message = event.message ?? "";
          log(message.startsWith("$ ") ? "command" : "info", message);
          break;
        }
        case "status":
          log(event.status === "success" ? "success" : event.status === "cancelled" ? "warning" : "error", event.message ?? "");
          break;
        case "latex_error_warning":
          log("warning", event.message ?? "");
          break;
        case "error":
          log("error", event.message ?? "Unknown server error.");
          // Errors tied to a render are always followed by a result; others are not.
          if (event.render_id == null) finish(false, "error");
          break;
        case "progress":
          if (activeRef.current) {
            updateActive({
              ...activeRef.current,
              progress: { percent: event.percent ?? 0, animation: event.animation, label: event.label },
            });
          }
          break;
        case "file_ready":
          if (render && event.url) {
            const output: RenderOutput = {
              url: event.url,
              kind: event.kind ?? "video",
              filename: event.filename ?? "render.mp4",
              relPath: event.rel_path ?? event.url,
              temporary: Boolean(event.is_temp_download),
            };
            outputRef.current = output;
            callbacks.current.onOutput(output, render);
          }
          break;
        case "result":
          finish(Boolean(event.success), event.status ?? "unknown");
          break;
      }
    },
    [finish, updateActive],
  );

  const scheduleReconnect = useCallback(() => {
    if (!mountedRef.current || reconnectTimer.current !== null) return;
    const delay = RECONNECT_DELAYS_MS[Math.min(attemptRef.current, RECONNECT_DELAYS_MS.length - 1)];
    attemptRef.current += 1;
    reconnectTimer.current = setTimeout(() => {
      reconnectTimer.current = null;
      connectRef.current();
    }, delay);
  }, []);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;
    const current = socketRef.current;
    if (current && (current.readyState === WebSocket.OPEN || current.readyState === WebSocket.CONNECTING)) return;
    if (reconnectTimer.current !== null) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }

    setConnection("connecting");
    let socket: WebSocket;
    try {
      socket = new WebSocket(wsUrl("/api/render"));
    } catch {
      setConnection("closed");
      scheduleReconnect();
      return;
    }
    socketRef.current = socket;

    socket.onopen = () => {
      if (socketRef.current !== socket) return;
      attemptRef.current = 0;
      setConnection("open");
      const queued = queueRef.current;
      queueRef.current = [];
      queued.forEach((payload) => socket.send(payload));
    };
    socket.onmessage = (message) => {
      if (socketRef.current !== socket) return;
      let event: ServerEvent;
      try {
        event = JSON.parse(String(message.data)) as ServerEvent;
      } catch {
        return;
      }
      handleEvent(event);
    };
    socket.onclose = () => {
      if (socketRef.current !== socket) return;
      socketRef.current = null;
      setConnection("closed");
      if (activeRef.current && queueRef.current.length === 0) {
        callbacks.current.log("error", "Lost connection to the render server.");
        finish(false, "disconnected");
      }
      scheduleReconnect();
    };
    // onclose always follows; nothing extra to do on error.
    socket.onerror = () => {};
  }, [finish, handleEvent, scheduleReconnect]);

  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  useEffect(() => {
    mountedRef.current = true;
    // Opening the socket is the external system this effect synchronizes with.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    connect();
    return () => {
      mountedRef.current = false;
      if (reconnectTimer.current !== null) clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
      const socket = socketRef.current;
      socketRef.current = null;
      socket?.close();
    };
  }, [connect]);

  const send = useCallback(
    (payload: object) => {
      const data = JSON.stringify(payload);
      const socket = socketRef.current;
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(data);
        return;
      }
      queueRef.current.push(data);
      attemptRef.current = 0;
      connect();
    },
    [connect],
  );

  const start = useCallback(
    (request: RenderRequest): string | null => {
      if (activeRef.current) return null;
      const id = makeId();
      outputRef.current = null;
      setStopping(false);
      updateActive({ id, request, progress: null, startedAt: Date.now() });
      send({
        type: "start",
        id,
        filename: request.filename,
        scene: request.scene,
        quality: request.quality,
        use_opengl: request.useOpenGL,
        download_only: request.downloadOnly,
        code: request.code,
      });

      setTimeout(() => {
        // Still waiting for a connection: give up instead of spinning forever.
        if (activeRef.current?.id === id && queueRef.current.length > 0) {
          queueRef.current = [];
          callbacks.current.log("error", "Couldn't reach the render server. Is the backend running?");
          finish(false, "offline");
        }
      }, CONNECT_TIMEOUT_MS);
      return id;
    },
    [finish, send, updateActive],
  );

  const cancel = useCallback(() => {
    const render = activeRef.current;
    if (!render) return;
    setStopping(true);
    const socket = socketRef.current;
    if (socket && socket.readyState === WebSocket.OPEN && queueRef.current.length === 0) {
      socket.send(JSON.stringify({ type: "cancel" }));
      // Nothing has run yet: drop it now. The server removes it from the queue, and
      // anything it still sends for this render is ignored by its id.
      if (render.queued) {
        callbacks.current.log("warning", "Cancelled before it started.");
        finish(false, "cancelled");
      }
    } else {
      queueRef.current = [];
      finish(false, "cancelled");
    }
  }, [finish]);

  const reconnect = useCallback(() => {
    attemptRef.current = 0;
    connect();
  }, [connect]);

  return { connection, active, stopping, start, cancel, reconnect };
}
