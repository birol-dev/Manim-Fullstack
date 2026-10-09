import { useEffect, useLayoutEffect, useRef, useState } from "react";

/** "Stopping…" / "Leaving the queue…" stay on screen at least this long. */
export const STOPPING_MIN_DISPLAY_MS = 400;

interface Stoppable {
  id: string;
}

/**
 * Display-only: a cancel the server confirms within a few ms used to flash
 * "Stopping…" / "Leaving the queue…" for a single frame. The session state
 * still changes at once (a new render can start right away); this only keeps
 * the stopping render on screen until it has been visible for *minMs*. A
 * different render (new id) replaces it immediately.
 */
export function useMinimumStopping<T extends Stoppable>(
  active: T | null,
  stopping: boolean,
  minMs: number = STOPPING_MIN_DISPLAY_MS,
): { active: T | null; stopping: boolean } {
  const [held, setHeld] = useState<T | null>(null);
  const since = useRef<{ id: string; at: number } | null>(null);
  const last = useRef<T | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Layout effect: the held frame replaces the finished one before paint, so nothing blinks.
  useLayoutEffect(() => {
    if (stopping && active) {
      if (since.current?.id !== active.id) since.current = { id: active.id, at: Date.now() };
      last.current = active;
      return;
    }
    const start = since.current;
    const shown = last.current;
    since.current = null;
    if (!start || !shown || shown.id !== start.id) return;
    const remaining = minMs - (Date.now() - start.at);
    if (remaining <= 0) return;
    // Holding the last "Stopping…" frame is the point (display only).
    setHeld(shown);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      timer.current = null;
      setHeld(null);
    }, remaining);
  }, [active, stopping, minMs]);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  if (held && (!active || active.id === held.id)) return { active: held, stopping: true };
  return { active, stopping };
}
