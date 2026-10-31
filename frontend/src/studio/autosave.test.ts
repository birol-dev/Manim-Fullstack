import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Autosaver, type SaveStatus, type Snapshot } from "./autosave";
import type { Project } from "./types";

const snap = (title: string): Snapshot => ({ title, template: "countdown", params: { title }, settings: { aspect: "16:9" } });
const project = (id: string): Project => ({ id, title: "", template: "countdown", params: {}, settings: {}, revision: 1, created: 0, updated: 0 });
const flush = async () => {
  for (let i = 0; i < 5; i += 1) await Promise.resolve();
};

describe("Autosaver", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("creates the project on the first edit, then updates it (debounced)", async () => {
    const create = vi.fn(async () => project("p1"));
    const update = vi.fn(async () => ({}));
    const onCreated = vi.fn();
    const statuses: SaveStatus[] = [];
    const saver = new Autosaver({ projectId: null, create, update, onCreated, onStatus: (status) => statuses.push(status) });

    saver.change(snap("a"));
    saver.change(snap("ab"));
    vi.advanceTimersByTime(799);
    expect(create).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(create).toHaveBeenCalledWith(snap("ab"), false);
    await flush();
    expect(onCreated).toHaveBeenCalledWith(project("p1"));
    expect(statuses.at(-1)).toBe("saved");

    saver.change(snap("abc"));
    vi.advanceTimersByTime(800);
    await flush();
    expect(update).toHaveBeenCalledWith("p1", snap("abc"), false);
    expect(create).toHaveBeenCalledTimes(1);
  });

  it("saves edits made during a save right after it", async () => {
    let finish: (value: Project) => void = () => {};
    const create = vi.fn(() => new Promise<Project>((resolve) => (finish = resolve)));
    const update = vi.fn(async () => ({}));
    const saver = new Autosaver({ projectId: null, create, update, onCreated: () => {}, onStatus: () => {} });
    saver.change(snap("one"));
    vi.advanceTimersByTime(800);
    saver.change(snap("two"));
    vi.advanceTimersByTime(800); // the create is still running: no second create
    expect(create).toHaveBeenCalledTimes(1);
    finish(project("p2"));
    await flush();
    vi.advanceTimersByTime(800);
    await flush();
    expect(update).toHaveBeenCalledWith("p2", snap("two"), false);
    expect(saver.dirty).toBe(false);
  });

  it("reports a failed save and tries again on the next edit only", async () => {
    const update = vi.fn().mockRejectedValueOnce(new Error("nope")).mockResolvedValue({});
    const statuses: SaveStatus[] = [];
    const saver = new Autosaver({ projectId: "p3", create: vi.fn(), update, onCreated: () => {}, onStatus: (status) => statuses.push(status) });
    saver.change(snap("x"));
    vi.advanceTimersByTime(800);
    await flush();
    expect(statuses.at(-1)).toBe("error");
    vi.advanceTimersByTime(5000);
    expect(update).toHaveBeenCalledTimes(1);
    saver.change(snap("xy"));
    vi.advanceTimersByTime(800);
    await flush();
    expect(update).toHaveBeenCalledTimes(2);
    expect(statuses.at(-1)).toBe("saved");
  });

  it("stops for good when the project changed elsewhere and resumes from a fresh copy", async () => {
    const conflict = new Error("409");
    const update = vi.fn().mockRejectedValueOnce(conflict).mockResolvedValue({});
    const onConflict = vi.fn(() => true);
    const statuses: SaveStatus[] = [];
    const saver = new Autosaver({ projectId: "p3", create: vi.fn(), update, onCreated: () => {}, onStatus: (status) => statuses.push(status), onConflict });
    saver.change(snap("mine"));
    vi.advanceTimersByTime(800);
    await flush();
    expect(onConflict).toHaveBeenCalledWith(conflict);
    expect(statuses.at(-1)).toBe("idle");
    expect(saver.dirty).toBe(true);

    saver.change(snap("still mine"));
    vi.advanceTimersByTime(5000);
    await flush();
    expect(update).toHaveBeenCalledTimes(1); // no retry, no overwrite

    saver.resume();
    expect(saver.dirty).toBe(false);
    saver.change(snap("after loading"));
    vi.advanceTimersByTime(800);
    await flush();
    expect(update).toHaveBeenCalledTimes(2);
    expect(update).toHaveBeenLastCalledWith("p3", snap("after loading"), false);
    expect(statuses.at(-1)).toBe("saved");
  });

  it("flushes on leave, with keepalive when asked", async () => {
    const update = vi.fn(async () => ({}));
    const saver = new Autosaver({ projectId: "p4", create: vi.fn(), update, onCreated: () => {}, onStatus: () => {} });
    saver.flush();
    expect(update).not.toHaveBeenCalled(); // nothing changed
    saver.change(snap("bye"));
    saver.flush(true);
    expect(update).toHaveBeenCalledWith("p4", snap("bye"), true);
    vi.advanceTimersByTime(2000);
    expect(update).toHaveBeenCalledTimes(1);
  });

  it("keeps a failed page-hide save dirty and allows retry without editing", async () => {
    const update = vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValue({});
    const onStatus = vi.fn();
    const saver = new Autosaver({ projectId: "p4", create: vi.fn(), update, onCreated: () => {}, onStatus });
    saver.change(snap("latest"));
    saver.flush(true);
    await flush();
    expect(saver.dirty).toBe(true);
    expect(onStatus).toHaveBeenLastCalledWith("error", expect.any(Error));
    saver.flush();
    await flush();
    expect(update).toHaveBeenLastCalledWith("p4", snap("latest"), false);
    expect(saver.dirty).toBe(false);
  });

  it("serializes a page-hide save behind an ongoing update", async () => {
    let finish = () => {};
    const update = vi.fn().mockImplementationOnce(() => new Promise<void>((resolve) => { finish = resolve; })).mockResolvedValue({});
    const saver = new Autosaver({ projectId: "p4", create: vi.fn(), update, onCreated: () => {}, onStatus: () => {} });
    saver.change(snap("old"));
    saver.flush();
    saver.change(snap("new"));
    saver.flush(true);
    expect(update).toHaveBeenCalledTimes(1);
    finish();
    await flush();
    expect(update).toHaveBeenLastCalledWith("p4", snap("new"), true);
    expect(saver.dirty).toBe(false);
  });

  it("uses keepalive when leaving a new, unsaved project", async () => {
    const create = vi.fn(async () => project("p5"));
    const onCreated = vi.fn();
    const saver = new Autosaver({ projectId: null, create, update: vi.fn(), onCreated, onStatus: () => {} });
    saver.change(snap("new"));
    saver.flush(true);
    saver.dispose();
    await flush();
    expect(create).toHaveBeenCalledWith(snap("new"), true);
    expect(onCreated).not.toHaveBeenCalled();
    expect(saver.dirty).toBe(false);
  });

  it("finishes edits queued behind an in-flight save when the editor closes", async () => {
    let finish = () => {};
    const update = vi.fn().mockImplementationOnce(() => new Promise<void>((resolve) => { finish = resolve; })).mockResolvedValue({});
    const saver = new Autosaver({ projectId: "p4", create: vi.fn(), update, onCreated: () => {}, onStatus: () => {} });
    saver.change(snap("first"));
    saver.flush();
    saver.change(snap("last"));
    saver.flush(true);
    saver.dispose();
    finish();
    await flush();
    expect(update).toHaveBeenCalledTimes(2);
    expect(update).toHaveBeenLastCalledWith("p4", snap("last"), true);
    expect(saver.dirty).toBe(false);
  });
});
