import { useCallback, useEffect, useRef, useState } from "react";

export type LogLevel = "command" | "info" | "success" | "warning" | "error" | "stdout" | "stderr";

export interface LogEntry {
  id: number;
  level: LogLevel;
  text: string;
}

const MAX_LOG_LINES = 2000;

/**
 * Console log buffer. Manim can print hundreds of lines a second, so entries
 * are collected and committed once per animation frame.
 */
export function useLogs() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const pending = useRef<LogEntry[]>([]);
  // Committed + pending entries, readable synchronously from event handlers.
  const all = useRef<LogEntry[]>([]);
  const frame = useRef<number | null>(null);
  const nextId = useRef(1);

  const flush = useCallback(() => {
    frame.current = null;
    if (pending.current.length === 0) return;
    const batch = pending.current;
    pending.current = [];
    setLogs((previous) => {
      const merged = previous.concat(batch);
      return merged.length > MAX_LOG_LINES ? merged.slice(merged.length - MAX_LOG_LINES) : merged;
    });
  }, []);

  const append = useCallback(
    (level: LogLevel, text: string) => {
      const entry = { id: nextId.current++, level, text };
      pending.current.push(entry);
      all.current.push(entry);
      if (all.current.length > MAX_LOG_LINES * 2) all.current = all.current.slice(-MAX_LOG_LINES);
      if (frame.current === null) frame.current = requestAnimationFrame(flush);
    },
    [flush],
  );

  const clear = useCallback(() => {
    pending.current = [];
    all.current = [];
    if (frame.current !== null) {
      cancelAnimationFrame(frame.current);
      frame.current = null;
    }
    setLogs([]);
  }, []);

  useEffect(
    () => () => {
      if (frame.current !== null) cancelAnimationFrame(frame.current);
    },
    [],
  );

  const snapshot = useCallback(() => all.current.slice(-MAX_LOG_LINES), []);

  return { logs, append, clear, snapshot };
}
