import { useEffect, useRef, useState } from "react";

import { cancelMotion, getMotion, startMotion } from "./api";
import { stableKey } from "./preview";
import type { MotionPreview, PreviewRequest } from "./types";

/** Explicit playback only. Edits cancel the job and hide its result immediately. */
export function useMotionPreview(request: PreviewRequest | undefined, session: string) {
  const key = stableKey({ request: request ?? null, session });
  const [state, setState] = useState<{ key: string; pending?: boolean; response?: MotionPreview; error?: unknown }>(() => ({ key }));
  // Forget completed motion on every edit, including a later undo back to the
  // exact content that originally produced it. Playback always needs a new click.
  if (state.key !== key) setState({ key });
  const serial = useRef(0);
  const job = useRef<string | null>(null);
  const starting = useRef<Promise<MotionPreview> | null>(null);
  const active = useRef<string | null>(null);
  useEffect(() => () => {
    serial.current++;
    active.current = null;
    if (job.current) void cancelMotion(job.current).catch(() => {});
    job.current = null;
  }, [key]);

  const start = async () => {
    if (!request || active.current === key) return;
    const generation = ++serial.current;
    active.current = key;
    setState({ key, pending: true });
    const current = () => serial.current === generation;
    try {
      // A new click waits for any older POST to return its cancellable handle.
      if (starting.current) await starting.current.catch(() => {});
      if (!current()) return;
      const promise = startMotion(session, request);
      starting.current = promise;
      let response = await promise;
      if (starting.current === promise) starting.current = null;
      if (!current()) {
        await cancelMotion(response.id).catch(() => {});
        return;
      }
      job.current = response.id;
      while (response.status === "queued" || response.status === "rendering") {
        await new Promise((resolve) => setTimeout(resolve, 350));
        if (!current()) return;
        response = await getMotion(response.id);
      }
      if (!current()) return;
      job.current = null;
      if (response.status !== "done" || !response.url) throw new Error(response.error || "Couldn't make a quick preview. Please try again.");
      setState({ key, response });
    } catch (error) {
      if (current()) setState({ key, error });
    } finally {
      if (current()) active.current = null;
    }
  };
  const cancel = () => {
    serial.current++;
    active.current = null;
    if (job.current) void cancelMotion(job.current).catch(() => {});
    job.current = null;
    setState({ key });
  };
  return { ...(state?.key === key ? state : null), start, cancel };
}
