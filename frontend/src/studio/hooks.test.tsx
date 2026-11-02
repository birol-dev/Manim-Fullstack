import { act, renderHook, waitFor } from "@testing-library/react";
import { expect, it } from "vitest";

import { SEEN_EXPORTS_KEY, useExportActivity } from "./hooks";
import { installFakeStudio } from "./test/fakeStudio";
import type { ExportJob } from "./types";

const job = (id: string, status: ExportJob["status"] = "done"): ExportJob => ({ id, status, template: "countdown", format: "mp4", quality: "720p", created: 1, progress: 100 });

it("seeds old exports on first run and persists the baseline across editor visits", async () => {
  const studio = installFakeStudio();
  studio.exports = [job("old-newest"), job("old-older")];
  const first = renderHook(() => useExportActivity(false));
  await waitFor(() => expect(JSON.parse(localStorage.getItem(SEEN_EXPORTS_KEY)!)).toEqual(["old-newest", "old-older"]));
  expect(first.result.current.activity).toBe(false);
  first.unmount();
  studio.exports = [job("new"), ...studio.exports];
  const second = renderHook(() => useExportActivity(false));
  await waitFor(() => expect(second.result.current.activity).toBe(true));
  act(() => second.result.current.markSeen());
  expect(second.result.current.activity).toBe(false);
  second.unmount();
  const third = renderHook(() => useExportActivity(false));
  await waitFor(() => expect(studio.calls.filter((call) => call.path === "/api/studio/exports")).toHaveLength(3));
  expect(third.result.current.activity).toBe(false);
});

it("seeds an empty install and flags a running export and its later completion", async () => {
  const studio = installFakeStudio();
  const view = renderHook(({ open, refresh }) => useExportActivity(open, refresh), { initialProps: { open: false, refresh: 0 } });
  await waitFor(() => expect(localStorage.getItem(SEEN_EXPORTS_KEY)).toBe("[]"));
  studio.exports = [job("new", "rendering")];
  view.rerender({ open: false, refresh: 1 });
  await waitFor(() => expect(view.result.current.activity).toBe(true));
  studio.exports = [job("new")];
  view.rerender({ open: false, refresh: 2 });
  await waitFor(() => expect(studio.calls.filter((call) => call.path === "/api/studio/exports")).toHaveLength(3));
  expect(view.result.current.activity).toBe(true);
  view.rerender({ open: true, refresh: 2 });
  expect(view.result.current.activity).toBe(false);
  act(() => view.result.current.markSeen());
  view.rerender({ open: false, refresh: 2 });
  expect(view.result.current.activity).toBe(false);
  expect(JSON.parse(localStorage.getItem(SEEN_EXPORTS_KEY)!)).toEqual(["new"]);
});

it("marks only the result that was viewed, even before the refreshed list arrives", async () => {
  const studio = installFakeStudio();
  localStorage.setItem(SEEN_EXPORTS_KEY, "[]");
  studio.exports = [job("another"), job("viewed", "rendering")];
  const view = renderHook(({ refresh }) => useExportActivity(false, refresh), { initialProps: { refresh: 0 } });
  await waitFor(() => expect(view.result.current.activity).toBe(true));
  act(() => view.result.current.markSeen("viewed"));
  studio.exports = [job("another"), job("viewed")];
  view.rerender({ refresh: 1 });
  await waitFor(() => expect(studio.calls.filter((call) => call.path === "/api/studio/exports")).toHaveLength(2));
  expect(view.result.current.activity).toBe(true);
  expect(JSON.parse(localStorage.getItem(SEEN_EXPORTS_KEY)!)).toEqual(["viewed"]);
  act(() => view.result.current.markSeen("another"));
  expect(view.result.current.activity).toBe(false);
});
