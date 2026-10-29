import { useCallback, useEffect, useRef, useState, type RefObject } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";

import { cancelExport, friendlyError, getCatalog, listExports, requestPreview } from "./api";
import { ACTIVE_EXPORT } from "./options";
import { LatestPreview, PosterQueue, stableKey, type PreviewState } from "./preview";
import type { Catalog, ExportJob, PreviewRequest, PreviewResponse } from "./types";

export function useCatalog() {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{ catalog: Catalog | null; error: unknown; attempt: number }>({
    catalog: null,
    error: null,
    attempt: -1,
  });
  useEffect(() => {
    let live = true;
    getCatalog().then(
      (catalog) => live && setState({ catalog, error: null, attempt }),
      (error) => live && setState({ catalog: null, error, attempt }),
    );
    return () => {
      live = false;
    };
  }, [attempt]);
  const retry = useCallback(() => setAttempt((value) => value + 1), []);
  const loading = state.attempt !== attempt;
  return { catalog: state.catalog, error: loading ? null : state.error, loading: loading && !state.catalog, retry };
}

/** Gallery thumbnails: two at a time, cached for the page's lifetime. */
export const posterQueue = new PosterQueue((request) => requestPreview(request), 2);

/** True once the element has come near the viewport (always true without IntersectionObserver). */
export function useNearViewport(ref: RefObject<Element | null>, margin = "300px"): boolean {
  const [seen, setSeen] = useState(() => typeof IntersectionObserver === "undefined");
  useEffect(() => {
    const element = ref.current;
    if (seen || !element || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setSeen(true);
          observer.disconnect();
        }
      },
      { rootMargin: margin },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref, seen, margin]);
  return seen;
}

/** A gallery poster for *request* (null: not yet). */
export function usePoster(request: PreviewRequest | null, queue: PosterQueue = posterQueue) {
  const key = request ? stableKey(request) : null;
  const [result, setResult] = useState<{ key: string; response?: PreviewResponse; error?: unknown } | null>(null);
  useEffect(() => {
    if (!key) return;
    let live = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const attempt = (retries: number) =>
      queue.get(JSON.parse(key) as PreviewRequest).then(
        (response) => live && setResult({ key, response }),
        (error) => {
          if (!live) return;
          // A busy or still-starting server (timeouts, 503) gets another try after a pause.
          const status = error instanceof ApiError ? error.status : 0;
          if (retries > 0 && (status === 0 || status === 429 || status >= 503)) timer = setTimeout(() => attempt(retries - 1), 4000);
          else setResult({ key, error });
        },
      );
    attempt(2);
    return () => {
      live = false;
      if (timer) clearTimeout(timer);
    };
  }, [key, queue]);
  const current = result && result.key === key ? result : null;
  return { response: current?.response ?? null, error: current?.error ?? null, loading: !!key && !current };
}

const IDLE: PreviewState = { response: null, pending: false, error: null, shownKey: null };

/**
 * The editor's live preview: asks ~400 ms after the last change and keeps the previous
 * image until a newer one arrives. *request* null pauses it (keeping what it has).
 */
export function useLivePreview(request: PreviewRequest | null, delay = 400) {
  const [state, setState] = useState<PreviewState>(IDLE);
  const scheduler = useRef<LatestPreview | null>(null);
  const key = request ? stableKey(request) : null;

  useEffect(() => {
    const preview = new LatestPreview({ fetcher: (body) => requestPreview(body), delay, leading: true, onChange: setState });
    scheduler.current = preview;
    return () => {
      preview.dispose();
      if (scheduler.current === preview) scheduler.current = null;
    };
  }, [delay]);

  useEffect(() => {
    if (key) scheduler.current?.schedule(JSON.parse(key) as PreviewRequest);
  }, [key, delay]);

  const retry = useCallback(() => {
    if (key) scheduler.current?.retry(JSON.parse(key) as PreviewRequest);
  }, [key]);

  return { ...state, retry };
}

/**
 * The URL to show for an image that changes: the new one replaces the old only once it has
 * loaded, so the preview never flashes empty between versions.
 */
export function useSmoothImage(url: string | null): string | null {
  const [shown, setShown] = useState<string | null>(null);
  useEffect(() => {
    if (!url || typeof Image === "undefined") return;
    let live = true;
    const image = new Image();
    const done = () => live && setShown(url);
    image.onload = done;
    image.onerror = done;
    image.src = url;
    return () => {
      live = false;
    };
  }, [url]);
  // Nothing loaded yet: show the first one straight away.
  return shown ?? url;
}

/** Recent exports, refreshed while any is still being made. */
export function useExports(enabled: boolean, refreshKey = 0, onLoaded?: (jobs: ExportJob[]) => void) {
  const [state, setState] = useState<{ jobs: ExportJob[] | null; error: unknown }>({ jobs: null, error: null });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!enabled) return;
    let live = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    listExports().then(
      (jobs) => {
        if (!live) return;
        onLoaded?.(jobs);
        setState({ jobs, error: null });
        if (jobs.some((job) => ACTIVE_EXPORT.has(job.status))) timer = setTimeout(() => setTick((value) => value + 1), 1500);
      },
      (error) => {
        if (!live) return;
        setState((prev) => ({ jobs: prev.jobs ?? [], error }));
        timer = setTimeout(() => setTick((value) => value + 1), 4000);
      },
    );
    return () => {
      live = false;
      if (timer) clearTimeout(timer);
    };
  }, [enabled, refreshKey, tick, onLoaded]);
  const cancel = async (job: ExportJob) => {
    try {
      await cancelExport(job.id);
      setTick((value) => value + 1);
    } catch (error) {
      toast.error(friendlyError(error, "Couldn't cancel the export."));
    }
  };
  return { ...state, cancel, retry: () => setTick((value) => value + 1) };
}

export const SEEN_EXPORTS_KEY = "studio:seen-exports";

function storedSeenExports(): Set<string> | null {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(SEEN_EXPORTS_KEY) ?? "null");
    return Array.isArray(value) && value.every((id) => typeof id === "string") ? new Set(value) : null;
  } catch {
    return null;
  }
}

function storeSeenExports(seen: Set<string>) {
  try { localStorage.setItem(SEEN_EXPORTS_KEY, JSON.stringify([...seen])); } catch { /* Storage can be unavailable in private windows. */ }
}

/** Seed the first successful listing, so pre-existing files never become new notifications. */
export function useExportActivity(open: boolean, refreshKey = 0) {
  const [seen, setSeen] = useState(storedSeenExports);
  const seenRef = useRef(seen);
  const onLoaded = useCallback((jobs: ExportJob[]) => {
    if (seenRef.current !== null) return;
    const initial = new Set(jobs.filter((job) => job.status === "done").map((job) => job.id));
    seenRef.current = initial;
    storeSeenExports(initial);
    setSeen(initial);
  }, []);
  const { jobs } = useExports(true, refreshKey, onLoaded);
  const markSeen = (id?: string) => {
    // Wait for the first successful listing before establishing the baseline.
    if (seenRef.current === null) return;
    const ids = id ? [id] : (jobs ?? []).filter((job) => job.status === "done").map((job) => job.id);
    if (ids.every((id) => seenRef.current!.has(id))) return;
    const next = new Set([...seenRef.current, ...ids]);
    seenRef.current = next;
    storeSeenExports(next);
    setSeen(next);
  };
  const activity = jobs?.some((job) => ACTIVE_EXPORT.has(job.status) || (!open && seen !== null && job.status === "done" && !seen.has(job.id))) ?? false;
  return { activity, markSeen };
}
