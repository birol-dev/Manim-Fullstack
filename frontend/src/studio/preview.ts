/**
 * Preview scheduling, free of React so it can be tested with fake timers:
 * - PosterQueue: gallery thumbnails, a few at a time, cached in memory by request.
 * - LatestPreview: the editor's live preview, debounced; a response older than the one on
 *   screen is ignored.
 */
import type { PreviewRequest, PreviewResponse } from "./types";

/** JSON with object keys sorted, so equal requests get equal keys. */
export function stableKey(value: unknown): string {
  return JSON.stringify(value, (_key, item) => {
    if (item && typeof item === "object" && !Array.isArray(item)) {
      return Object.fromEntries(Object.keys(item as object).sort().map((key) => [key, (item as Record<string, unknown>)[key]]));
    }
    return item;
  });
}

/** Stills contain no sound; changing music must not request another image. */
export function visualPreviewKey(request: PreviewRequest): string {
  const settings = { ...request.settings };
  delete settings.sound;
  return stableKey({ ...request, settings });
}

type Fetcher = (request: PreviewRequest, signal?: AbortSignal) => Promise<PreviewResponse>;

interface QueueEntry {
  request: PreviewRequest;
  resolve: (value: PreviewResponse) => void;
  reject: (reason: unknown) => void;
}

export class PosterQueue {
  private readonly cache = new Map<string, Promise<PreviewResponse>>();
  private readonly waiting: QueueEntry[] = [];
  private running = 0;
  private readonly fetcher: Fetcher;
  private readonly concurrency: number;

  constructor(fetcher: Fetcher, concurrency = 2) {
    this.fetcher = fetcher;
    this.concurrency = concurrency;
  }

  get inFlight() {
    return this.running;
  }

  get queued() {
    return this.waiting.length;
  }

  /** Forget completed thumbnail requests (for example, after changing the workspace). */
  clear() {
    this.cache.clear();
  }

  /** The poster for *request*: cached, joined if already on its way, else queued. */
  get(request: PreviewRequest): Promise<PreviewResponse> {
    const key = visualPreviewKey(request);
    const cached = this.cache.get(key);
    if (cached) return cached;
    const promise = new Promise<PreviewResponse>((resolve, reject) => {
      this.waiting.push({ request, resolve, reject });
      this.pump();
    });
    this.cache.set(key, promise);
    // A failure isn't cached: the next request tries again.
    promise.catch(() => {
      if (this.cache.get(key) === promise) this.cache.delete(key);
    });
    return promise;
  }

  /** Move a waiting request to the front (a card scrolled into view). */
  prioritize(request: PreviewRequest) {
    const key = visualPreviewKey(request);
    const index = this.waiting.findIndex((entry) => stableKey(entry.request) === key);
    if (index > 0) this.waiting.unshift(...this.waiting.splice(index, 1));
  }

  private pump() {
    while (this.running < this.concurrency && this.waiting.length) {
      const entry = this.waiting.shift()!;
      this.running += 1;
      this.fetcher(entry.request)
        .then(entry.resolve, entry.reject)
        .finally(() => {
          this.running -= 1;
          this.pump();
        });
    }
  }
}

export interface PreviewState {
  response: PreviewResponse | null;
  /** A request is waiting for the debounce or for the server. */
  pending: boolean;
  error: unknown;
  /** The request whose response (or error) is on screen. */
  shownKey: string | null;
}

interface LatestPreviewOptions {
  fetcher: Fetcher;
  delay?: number;
  /** Send the very first request at once (the editor opening), later ones after the delay. */
  leading?: boolean;
  onChange: (state: PreviewState) => void;
}

export class LatestPreview {
  private readonly fetcher: Fetcher;
  private readonly delay: number;
  private readonly onChange: (state: PreviewState) => void;
  private readonly leading: boolean;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private issued = 0;
  private applied = 0;
  private inFlight = 0;
  private scheduledKey: string | null = null;
  private lastIssuedKey: string | null = null;
  // Renders run one at a time on the server: while one is out, only the newest edit waits here
  // (sending each edit would queue stale renders ahead of the one that matters).
  private queued: { request: PreviewRequest; key: string } | null = null;
  private disposed = false;
  private state: PreviewState = { response: null, pending: false, error: null, shownKey: null };

  constructor({ fetcher, delay = 400, leading = false, onChange }: LatestPreviewOptions) {
    this.fetcher = fetcher;
    this.delay = delay;
    this.leading = leading;
    this.onChange = onChange;
  }

  get current() {
    return this.state;
  }

  /** Ask for a preview of *request* once nothing has changed for the delay. */
  schedule(request: PreviewRequest, { immediate = false } = {}) {
    if (this.disposed) return;
    const key = visualPreviewKey(request);
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    // Already shown or already on its way: nothing to do.
    if (key === this.lastIssuedKey) {
      this.scheduledKey = null;
      this.queued = null;
      this.emit({ pending: this.inFlight > 0 && this.state.shownKey !== key });
      return;
    }
    this.scheduledKey = key;
    this.emit({ pending: true });
    const fire = () => {
      this.timer = null;
      if (this.inFlight > 0) this.queued = { request, key };
      else this.issue(request, key);
    };
    if (immediate || (this.leading && this.issued === 0)) fire();
    else this.timer = setTimeout(fire, this.delay);
  }

  /** Send a scheduled request now instead of waiting. */
  flush(request: PreviewRequest) {
    this.schedule(request, { immediate: true });
  }

  /** Ask again for the same request (after a failure). */
  retry(request: PreviewRequest) {
    this.lastIssuedKey = null;
    this.schedule(request, { immediate: true });
  }

  dispose() {
    this.disposed = true;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.queued = null;
  }

  private issue(request: PreviewRequest, key: string) {
    const seq = ++this.issued;
    this.lastIssuedKey = key;
    if (this.scheduledKey === key) this.scheduledKey = null;
    this.inFlight += 1;
    this.fetcher(request).then(
      (response) => this.settle(seq, key, { response, error: null }),
      (error) => this.settle(seq, key, { error }),
    );
  }

  private settle(seq: number, key: string, result: { response?: PreviewResponse; error: unknown }) {
    this.inFlight -= 1;
    if (this.disposed) return;
    if (this.queued && this.inFlight === 0) {
      const next = this.queued;
      this.queued = null;
      this.issue(next.request, next.key);
    }
    const stillWaiting = this.scheduledKey !== null || this.inFlight > 0;
    if (seq < this.applied) {
      // An answer to an older request than the one on screen: drop it.
      this.emit({ pending: stillWaiting });
      return;
    }
    this.applied = seq;
    // Newer requests are still out: keep showing "updating" until the latest lands.
    const pending = this.scheduledKey !== null || seq < this.issued;
    if (result.response) this.emit({ response: result.response, error: null, pending, shownKey: key });
    else this.emit({ error: result.error, pending, shownKey: key });
  }

  private emit(patch: Partial<PreviewState>) {
    this.state = { ...this.state, ...patch };
    this.onChange(this.state);
  }
}
