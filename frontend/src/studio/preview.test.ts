import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LatestPreview, PosterQueue, stableKey, type PreviewState } from "./preview";
import type { PreviewRequest, PreviewResponse } from "./types";

interface Deferred {
  request: PreviewRequest;
  resolve: (value: PreviewResponse) => void;
  reject: (reason: unknown) => void;
}

function controllableFetcher() {
  const calls: Deferred[] = [];
  const fetcher = vi.fn(
    (request: PreviewRequest) =>
      new Promise<PreviewResponse>((resolve, reject) => {
        calls.push({ request, resolve, reject });
      }),
  );
  return { calls, fetcher };
}

const req = (title: string, extra: Partial<PreviewRequest> = {}): PreviewRequest => ({
  template: "countdown",
  params: { title },
  settings: { aspect: "16:9" },
  mode: "poster",
  ...extra,
});
const res = (url: string): PreviewResponse => ({ url, mode: "poster", width: 640, height: 360 });
const flush = () => new Promise<void>((resolve) => queueMicrotask(resolve)).then(() => Promise.resolve());

describe("stableKey", () => {
  it("doesn't depend on key order", () => {
    expect(stableKey({ a: 1, b: { c: 2, d: [1, { y: 1, x: 2 }] } })).toBe(stableKey({ b: { d: [1, { x: 2, y: 1 }], c: 2 }, a: 1 }));
    expect(stableKey({ a: [1, 2] })).not.toBe(stableKey({ a: [2, 1] }));
  });
});

describe("LatestPreview", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("waits 400 ms after the last change and sends only the latest", async () => {
    const { calls, fetcher } = controllableFetcher();
    const states: PreviewState[] = [];
    const preview = new LatestPreview({ fetcher, onChange: (state) => states.push(state) });
    preview.schedule(req("H"));
    vi.advanceTimersByTime(200);
    preview.schedule(req("He"));
    vi.advanceTimersByTime(399);
    preview.schedule(req("Hey"));
    vi.advanceTimersByTime(399);
    expect(fetcher).not.toHaveBeenCalled();
    expect(preview.current.pending).toBe(true);
    vi.advanceTimersByTime(1);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(calls[0].request.params.title).toBe("Hey");
    calls[0].resolve(res("/hey.png"));
    await flush();
    expect(preview.current).toMatchObject({ response: res("/hey.png"), pending: false, error: null });
  });

  it("sends the first request at once with leading", () => {
    const { fetcher } = controllableFetcher();
    const preview = new LatestPreview({ fetcher, leading: true, onChange: () => {} });
    preview.schedule(req("first"));
    expect(fetcher).toHaveBeenCalledTimes(1);
    preview.schedule(req("second"));
    expect(fetcher).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(400);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("ignores a response that arrives after a newer one", async () => {
    const { calls, fetcher } = controllableFetcher();
    const preview = new LatestPreview({ fetcher, onChange: () => {} });
    preview.schedule(req("old"));
    vi.advanceTimersByTime(400);
    preview.schedule(req("new"));
    vi.advanceTimersByTime(400);
    expect(calls).toHaveLength(2);

    calls[1].resolve(res("/new.png"));
    await flush();
    expect(preview.current).toMatchObject({ response: res("/new.png"), pending: false });

    calls[0].resolve(res("/old.png"));
    await flush();
    expect(preview.current.response).toEqual(res("/new.png"));
    expect(preview.current.pending).toBe(false);
  });

  it("shows an older answer while a newer one is on its way, then replaces it", async () => {
    const { calls, fetcher } = controllableFetcher();
    const preview = new LatestPreview({ fetcher, onChange: () => {} });
    preview.schedule(req("a"));
    vi.advanceTimersByTime(400);
    preview.schedule(req("b"));
    vi.advanceTimersByTime(400);
    calls[0].resolve(res("/a.png"));
    await flush();
    expect(preview.current).toMatchObject({ response: res("/a.png"), pending: true });
    calls[1].resolve(res("/b.png"));
    await flush();
    expect(preview.current).toMatchObject({ response: res("/b.png"), pending: false });
  });

  it("keeps the last image when a request fails, and clears the error on success", async () => {
    const { calls, fetcher } = controllableFetcher();
    const preview = new LatestPreview({ fetcher, onChange: () => {} });
    preview.schedule(req("ok"));
    vi.advanceTimersByTime(400);
    calls[0].resolve(res("/ok.png"));
    await flush();
    preview.schedule(req("bad"));
    vi.advanceTimersByTime(400);
    const failure = new Error("422");
    calls[1].reject(failure);
    await flush();
    expect(preview.current).toMatchObject({ response: res("/ok.png"), error: failure, pending: false });
    preview.schedule(req("fixed"));
    vi.advanceTimersByTime(400);
    calls[2].resolve(res("/fixed.png"));
    await flush();
    expect(preview.current).toMatchObject({ response: res("/fixed.png"), error: null });
  });

  it("doesn't ask again for what it already asked for; retry does", async () => {
    const { calls, fetcher } = controllableFetcher();
    const preview = new LatestPreview({ fetcher, onChange: () => {} });
    preview.schedule(req("same"));
    vi.advanceTimersByTime(400);
    calls[0].resolve(res("/same.png"));
    await flush();
    preview.schedule(req("other"));
    preview.schedule({ ...req("same"), params: { title: "same" } });
    vi.advanceTimersByTime(1000);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(preview.current.pending).toBe(false);
    preview.retry(req("same"));
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("stops after dispose", async () => {
    const { calls, fetcher } = controllableFetcher();
    const onChange = vi.fn();
    const preview = new LatestPreview({ fetcher, onChange });
    preview.schedule(req("x"));
    preview.dispose();
    vi.advanceTimersByTime(1000);
    expect(fetcher).not.toHaveBeenCalled();
    expect(calls).toHaveLength(0);
  });
});

describe("PosterQueue", () => {
  it("runs at most two at a time, in order", async () => {
    const { calls, fetcher } = controllableFetcher();
    const queue = new PosterQueue(fetcher, 2);
    const results = ["a", "b", "c", "d"].map((title) => queue.get(req(title)));
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(queue.queued).toBe(2);
    calls[0].resolve(res("/a.png"));
    await flush();
    expect(fetcher).toHaveBeenCalledTimes(3);
    expect(calls[2].request.params.title).toBe("c");
    calls[1].resolve(res("/b.png"));
    calls[2].resolve(res("/c.png"));
    await flush();
    calls[3].resolve(res("/d.png"));
    await expect(Promise.all(results)).resolves.toEqual([res("/a.png"), res("/b.png"), res("/c.png"), res("/d.png")]);
    expect(queue.inFlight).toBe(0);
  });

  it("caches by request (whatever the key order) and retries failures", async () => {
    const { calls, fetcher } = controllableFetcher();
    const queue = new PosterQueue(fetcher, 2);
    const first = queue.get({ template: "t", params: { a: 1, b: 2 }, settings: {}, mode: "poster" });
    const same = queue.get({ mode: "poster", settings: {}, params: { b: 2, a: 1 }, template: "t" });
    expect(same).toBe(first);
    expect(fetcher).toHaveBeenCalledTimes(1);
    calls[0].reject(new Error("busy"));
    await expect(first).rejects.toThrow("busy");
    await flush();
    queue.get({ template: "t", params: { a: 1, b: 2 }, settings: {}, mode: "poster" });
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("moves a waiting request to the front", async () => {
    const { calls, fetcher } = controllableFetcher();
    const queue = new PosterQueue(fetcher, 1);
    queue.get(req("1"));
    queue.get(req("2"));
    queue.get(req("3"));
    queue.prioritize(req("3"));
    calls[0].resolve(res("/1.png"));
    await flush();
    expect(calls[1].request.params.title).toBe("3");
  });
});
