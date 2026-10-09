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
  /** Place in the server's render queue (1 = next), when the server reports it. */
  queuePosition?: number;
  /** The server sends typed "queued"/"started" events, so only "started" ends the wait. */
  queueEvents?: boolean;
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
  /** "queued" events: place in the render queue, 1 = next. */
  position?: number;
}

interface Options {
  log: (level: LogLevel, text: string) => void;
  onOutput: (output: RenderOutput, render: ActiveRender) => void;
  onFinished: (outcome: RenderOutcome) => void;
}

/**
 * The legacy info line for a queued render. Servers since #10 also send typed
 * "queued" and "started" events; the prefix is kept for older servers.
 */
export const QUEUED_MESSAGE_PREFIX = "Waiting for another render";
/** Servers that don't confirm a queued cancel within this time are taken at their word. */
export const QUEUED_CANCEL_FALLBACK_MS = 3000;

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

      if (render && event.render_id === render.id) {
        if (event.type === "queued") {
          updateActive({ ...render, queued: true, queuePosition: event.position || undefined, queueEvents: true });
        } else if (event.type === "info" && (event.message ?? "").startsWith(QUEUED_MESSAGE_PREFIX)) {
          // Legacy queue notice (also sent after "queued", for older clients).
          if (!render.queued) updateActive({ ...render, queued: true });
        } else if (render.queued && (event.type === "started" || (!render.queueEvents && event.type !== "result"))) {
          // "started", or for older servers anything else about this render (the "$ manim" line...).
          updateActive({ ...render, queued: false, queuePosition: undefined });
        }
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
          // A render cancelled while queued gets only a result; say what happened.
          if (render?.queued && event.status === "cancelled") log("warning", "Cancelled before it started.");
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
      socket.send(JSON.stringify({ type: "cancel", id: render.id }));
      if (render.queued) {
        // The server drops it from the queue and answers with one "cancelled" result.
        // Fallback for servers that never answer: finish locally; a late result is
        // then ignored by its id, so nothing is logged or toasted twice.
        setTimeout(() => {
          if (activeRef.current?.id !== render.id) return;
          callbacks.current.log("warning", "Cancelled before it started.");
          finish(false, "cancelled");
        }, QUEUED_CANCEL_FALLBACK_MS);
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
