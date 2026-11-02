import { describe, expect, it } from "vitest";
import { EditorHistory } from "./editorHistory";

describe("editor history", () => {
  it("coalesces typing by pause and field, while preserving each other edit", () => {
    const h = new EditorHistory(0);
    h.change(1, "field-a", 0); h.change(2, "field-a", 200); h.change(3, "field-a", 799);
    h.change(4, "field-a", 1400); h.change(5, "field-b", 1450); h.change(6);
    expect(h.undo()).toBe(true); expect(h.current).toBe(5);
    h.undo(); expect(h.current).toBe(4);
    h.undo(); expect(h.current).toBe(3);
    h.undo(); expect(h.current).toBe(0);
    expect(h.undo()).toBe(false);
    h.redo(); expect(h.current).toBe(3);
  });
  it("caps history at 100, ignores no-ops, and branches after undo", () => {
    const h = new EditorHistory({ n: 0 });
    expect(h.change({ n: 0 })).toBe(false);
    for (let n = 1; n <= 105; n++) h.change({ n });
    for (let n = 0; n < 100; n++) expect(h.undo()).toBe(true);
    expect(h.current.n).toBe(5); expect(h.canUndo).toBe(false);
    h.redo(); h.change({ n: 999 }); expect(h.canRedo).toBe(false);
  });
  it("makes remote snapshots and related list changes atomic undo steps", () => {
    const initial = { rows: ["a", "b"], correct: 2, theme: "clean" };
    const h = new EditorHistory(initial);
    h.change({ ...initial, rows: ["b", "a"], correct: 1 });
    h.change({ ...h.current, theme: "midnight" });
    h.undo(); expect(h.current.theme).toBe("clean");
    h.undo(); expect(h.current).toEqual(initial);
    h.redo(); expect(h.current.correct).toBe(1);
  });
});
