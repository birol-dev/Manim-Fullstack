import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useExports } from "./hooks";
import { installFakeStudio } from "./test/fakeStudio";
import type { ExportJob } from "./types";

const job: ExportJob = { id: "e1", template: "countdown", format: "mp4", quality: "720p", status: "rendering", progress: 10, created: 1 };

describe("export list recovery", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("retries connection failures and resumes polling active exports", async () => {
    const studio = installFakeStudio();
    let failed = true;
    studio.reply = (call) => call.path === "/api/studio/exports" && failed ? { status: 503, body: { detail: "offline" } } : null;
    const { result, unmount } = renderHook(() => useExports(true));
    await act(async () => {});
    expect(result.current.error).toBeTruthy();
    failed = false;
    studio.exports.push({ ...job });
    await act(async () => { await vi.advanceTimersByTimeAsync(4000); });
    expect(result.current.error).toBeNull();
    expect(result.current.jobs?.[0].status).toBe("rendering");
    studio.exports[0] = { ...job, status: "done", progress: 100 };
    await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
    expect(result.current.jobs?.[0].status).toBe("done");
    const calls = studio.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    expect(studio.calls).toHaveLength(calls);
    unmount();
  });

  it("keeps known exports during an error and supports immediate retry", async () => {
    const studio = installFakeStudio();
    studio.exports.push({ ...job });
    const { result } = renderHook(() => useExports(true));
    await act(async () => {});
    studio.reply = (call) => call.path === "/api/studio/exports" ? { status: 503, body: { detail: "offline" } } : null;
    await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
    expect(result.current.jobs?.[0].id).toBe("e1");
    expect(result.current.error).toBeTruthy();
    studio.reply = null;
    await act(async () => { result.current.retry(); });
    expect(result.current.error).toBeNull();
    expect(result.current.jobs?.[0].id).toBe("e1");
  });
});
