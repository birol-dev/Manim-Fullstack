/** Regression tests for the review fixes: autosave settle, seen exports, preference fallback, notices. */
import { act, render, renderHook, waitFor } from "@testing-library/react";
import { toast } from "sonner";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Autosaver, type Snapshot } from "./autosave";
import { ExportNotices, resetExportNoticesForTests, watchExport } from "./exportNotices";
import { SEEN_EXPORTS_KEY, useExportActivity } from "./hooks";
import { rememberedExport } from "./options";
import { flushPreferences, readPreference, resetPreferencesForTests, setExportChoice, writePreference } from "./preferences";
import { installFakeStudio, type FakeStudio } from "./test/fakeStudio";
import type { ExportJob, Project } from "./types";

const snap = (title: string): Snapshot => ({ title, template: "countdown", params: { title }, settings: {} });
const project = (id: string): Project => ({ id, title: "", template: "countdown", params: {}, settings: {}, revision: 1, created: 0, updated: 0 });
const job = (id: string, status: ExportJob["status"] = "done", extra: Partial<ExportJob> = {}): ExportJob =>
  ({ id, status, template: "countdown", format: "mp4", quality: "720p", created: 1, progress: 100, ...extra });

describe("Autosaver.settle", () => {
  it("waits for a save in flight, then saves the newer edit, one at a time", async () => {
    let release: () => void = () => {};
    const calls: string[] = [];
    let running = 0;
    const update = vi.fn(async (_id: string, snapshot: Snapshot) => {
      running += 1;
      expect(running).toBe(1);
      calls.push(snapshot.title);
      if (calls.length === 1) await new Promise<void>((resolve) => { release = resolve; });
      running -= 1;
    });
    const saver = new Autosaver({ projectId: "p1", create: async () => project("p1"), update, onCreated: () => {}, onStatus: () => {} });
    saver.change(snap("a"));
    saver.flush();
    saver.change(snap("ab"));
    const settled = saver.settle();
    release();
    await expect(settled).resolves.toBe(true);
    expect(calls).toEqual(["a", "ab"]);
    expect(saver.dirty).toBe(false);
  });

  it("answers false when the project changed elsewhere", async () => {
    const saver = new Autosaver({
      projectId: "p1", create: async () => project("p1"),
      update: async () => { throw new Error("conflict"); },
      onCreated: () => {}, onStatus: () => {}, onConflict: () => true,
    });
    saver.change(snap("a"));
    await expect(saver.settle()).resolves.toBe(false);
    expect(saver.halted).toBe(true);
  });
});

describe("seen exports", () => {
  beforeEach(() => {
    resetPreferencesForTests();
    localStorage.clear();
  });

  it("keeps a long history quiet: the newest exports are the ones remembered", async () => {
    const studio = installFakeStudio();
    studio.exports = Array.from({ length: 250 }, (_, index) => job(`e${String(index).padStart(3, "0")}`));
    const first = renderHook(() => useExportActivity(false));
    await waitFor(() => expect(localStorage.getItem(SEEN_EXPORTS_KEY)).not.toBeNull());
    const stored: string[] = JSON.parse(localStorage.getItem(SEEN_EXPORTS_KEY)!);
    expect(stored).toHaveLength(200);
    expect(stored[0]).toBe("e000"); // the newest (the list arrives newest first)
    first.unmount();
    const second = renderHook(() => useExportActivity(false));
    await waitFor(() => expect(studio.calls.filter((call) => call.path === "/api/studio/exports")).toHaveLength(2));
    expect(second.result.current.activity).toBe(false);
    second.unmount();
  });
});

describe("preferences", () => {
  let studio: FakeStudio;
  beforeEach(() => {
    resetPreferencesForTests();
    localStorage.clear();
    studio = installFakeStudio();
    studio.reply = (call) => {
      if (call.path !== "/api/studio/preferences" || call.method !== "PATCH") return null;
      const body = call.body as Record<string, unknown>;
      return "favourite_designs" in body
        ? { status: 422, body: { detail: "Invalid preferences.", errors: [{ field: "favourite_designs.0", message: "no" }] } }
        : { status: 200, body };
    };
  });

  it("saves the good values when one in the same batch is refused", async () => {
    writePreference("favourite_designs", ["not a design"]);
    writePreference("brand_name", "Ada");
    await flushPreferences();
    const patches = studio.calls.filter((call) => call.method === "PATCH").map((call) => call.body);
    expect(patches).toContainEqual({ brand_name: "Ada" });
  });

  it("remembers the last export's file type and quality", () => {
    expect(rememberedExport()).toEqual({ format: "mp4", quality: "1080p" });
    setExportChoice("webm", "720p");
    expect(readPreference("export_format")).toBe("webm");
    expect(rememberedExport()).toEqual({ format: "webm", quality: "720p" });
    setExportChoice("nope", "720p");
    expect(rememberedExport().format).toBe("mp4"); // an unknown type falls back
  });
});

describe("ExportNotices", () => {
  let studio: FakeStudio;
  beforeEach(() => {
    resetExportNoticesForTests();
    studio = installFakeStudio();
    vi.spyOn(toast, "success");
    vi.spyOn(toast, "error");
  });
  afterEach(() => vi.restoreAllMocks());

  const listings = () => studio.calls.filter((call) => call.path === "/api/studio/exports").length;

  it("announces an export that finishes anywhere, but not old ones", async () => {
    studio.exports = [job("old"), job("new", "rendering", { title: "Promo" })];
    render(<ExportNotices />);
    await waitFor(() => expect(listings()).toBe(1));
    studio.exports = [job("old"), job("new", "done", { title: "Promo" })];
    await waitFor(() => expect(toast.success).toHaveBeenCalledTimes(1), { timeout: 4000 });
    expect(vi.mocked(toast.success).mock.calls[0][0]).toBe("Promo is ready");
  });

  it("announces a list once, when its last row finishes", async () => {
    const row = (id: string, status: ExportJob["status"]) => job(id, status, { batch_id: "b1", batch_title: "Badges" });
    studio.exports = [row("a", "rendering"), row("b", "queued")];
    render(<ExportNotices />);
    await waitFor(() => expect(listings()).toBe(1));
    studio.exports = [row("a", "done"), row("b", "rendering")];
    await waitFor(() => expect(listings()).toBeGreaterThanOrEqual(2), { timeout: 4000 });
    expect(toast.success).not.toHaveBeenCalled();
    studio.exports = [row("a", "done"), row("b", "failed")];
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1), { timeout: 4000 });
    expect(vi.mocked(toast.error).mock.calls[0][0]).toBe("Badges is finished");
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("leaves an export to the dialog that is following it", async () => {
    studio.exports = [job("mine", "rendering")];
    const stop = watchExport("mine");
    render(<ExportNotices />);
    await waitFor(() => expect(listings()).toBe(1));
    studio.exports = [job("mine")];
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 1800)); });
    expect(toast.success).not.toHaveBeenCalled();
    stop();
  });
});
