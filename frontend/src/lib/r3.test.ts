import { describe, expect, it } from "vitest";

import { BOTTOM_MIN_PX, workPanelSizes } from "./layout";
import { pathSegments } from "./paths";
import { stripBoxDrawing } from "./traceback";

describe("workPanelSizes (item 1)", () => {
  it("starts with a smaller console on short viewports and keeps ~300 px for the preview", () => {
    // 1024x700: work area 632 px; 22vh console, top row >= 368 (300 px stage + header + footer).
    expect(workPanelSizes(700)).toEqual({ bottomDefaultPx: 154, topMinPx: 368 });
    expect(workPanelSizes(640)).toEqual({ bottomDefaultPx: 141, topMinPx: 368 });
    // A real browser window at 1024x700 has a ~600 px viewport.
    expect(workPanelSizes(600)).toEqual({ bottomDefaultPx: 132, topMinPx: 368 });
  });

  it("keeps the old 26% default on tall viewports", () => {
    expect(workPanelSizes(900)).toEqual({ bottomDefaultPx: Math.round((900 - 68) * 0.26), topMinPx: 368 });
    expect(workPanelSizes(1080).bottomDefaultPx).toBe(Math.round((1080 - 68) * 0.26));
  });

  it("never squeezes the console below its minimum", () => {
    const { bottomDefaultPx, topMinPx } = workPanelSizes(480);
    expect(bottomDefaultPx).toBeGreaterThanOrEqual(BOTTOM_MIN_PX);
    expect(topMinPx + BOTTOM_MIN_PX).toBeLessThanOrEqual(480 - 68);
    expect(workPanelSizes(300).topMinPx).toBe(240);
  });
});

describe("stripBoxDrawing (item 7)", () => {
  it("removes Rich's border, keeps titles, code and indentation", () => {
    const copied = [
      "╭───────── Traceback (most recent call last) ─────────╮",
      "│ scene.py:7 in construct                             │",
      "│                                                     │",
      "│   6 │   │   self.play(Create(c))                    │",
      "│ ❱ 7 │   │   self.play(Transform(c, undefined_name)) │",
      "╰─────────────────────────────────────────────────────╯",
      "NameError: name 'undefined_name' is not defined",
    ].join("\n");
    const plain = stripBoxDrawing(copied);
    expect(plain).not.toMatch(/[│┃╭╮╰╯─]/);
    expect(plain.split("\n")).toEqual([
      "Traceback (most recent call last)",
      "scene.py:7 in construct",
      "",
      "  6         self.play(Create(c))",
      "❱ 7         self.play(Transform(c, undefined_name))",
      "NameError: name 'undefined_name' is not defined",
    ]);
  });

  it("handles a partial selection from the middle of a row", () => {
    expect(stripBoxDrawing("self.play(Create(c))      │")).toBe("self.play(Create(c))");
    expect(stripBoxDrawing("plain text, no box")).toBe("plain text, no box");
  });
});

describe("pathSegments (item 3)", () => {
  it("breaks after separators only", () => {
    expect(pathSegments("/usr/bin/ffmpeg")).toEqual(["/", "usr/", "bin/", "ffmpeg"]);
    expect(pathSegments("C:\\Tools\\manim.exe")).toEqual(["C:\\", "Tools\\", "manim.exe"]);
  });
});

describe("timeline total with an unknown outer loop (round 3 gap)", () => {
  it("applies the known inner multiplier per outer pass and marks the total open-ended", async () => {
    const { knownRuns, timelineTotal } = await import("./timeline");
    // for i in range(n):            <- unknown
    //     for j in range(3): play   <- ×3 per pass
    //     wait(1)
    const steps = [
      { type: "play" as const, label: "Create(Circle())", line: 6, duration: 1, estimated: true, repeat: null, loop_line: 4, loops: [[4, 8, null], [5, 12, 3]] as Array<[number, number, number | null]> },
      { type: "wait" as const, label: "Wait 1s", line: 7, duration: 1, repeat: null, loop_line: 4, loops: [[4, 8, null]] as Array<[number, number, number | null]> },
    ];
    expect(knownRuns(steps[0])).toBe(3);
    expect(knownRuns(steps[1])).toBe(1);
    expect(timelineTotal(steps)).toEqual({ seconds: 4, estimated: true, runs: 4, unknownLoops: true });
  });

  it("keeps fully known nested loops exact", async () => {
    const { timelineTotal } = await import("./timeline");
    const step = { type: "play" as const, label: "x", line: 3, duration: 2, repeat: 6, loop_line: 2, loops: [[2, 4, 2], [3, 8, 3]] as Array<[number, number, number | null]> };
    expect(timelineTotal([step])).toEqual({ seconds: 12, estimated: false, runs: 6, unknownLoops: false });
  });
});
