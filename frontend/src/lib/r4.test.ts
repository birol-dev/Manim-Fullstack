// Fix round 4 (visual): logic behind the layout, quality, console and copy fixes.
import { describe, expect, it } from "vitest";

import { qualityShortLabel, qualityTooltip } from "./constants";
import { focusWithRing } from "./focus";
import { friendlyKatex } from "./katex";
import { horizontalDefaults, TOAST_TOP_PX, workPanelSizes } from "./layout";
import { consoleCopyText, latestQueuedLineId, withQueuePosition } from "./logs";
import { codeBreakSegments, longestSegment, SHORT_GROUP_CHARS, stepMetaWidth } from "./timeline";
import { stripBoxDrawing } from "./traceback";
import type { AnimationStep } from "./types";

describe("quality is one setting for all files (item 1) and fits its 78 px select (item 2)", () => {
  it("says so in the tooltip", () => {
    expect(qualityTooltip("h")).toBe("Quality (all files): High · 1080p · 60 fps");
    expect(qualityTooltip("m")).toBe("Quality (all files): Medium · 720p · 30 fps");
  });

  it("shows a short label in the toolbar", () => {
    expect(qualityShortLabel("l")).toBe("480p");
    expect(qualityShortLabel("h")).toBe("1080p");
    expect(qualityShortLabel("k")).toBe("2160p");
  });
});

describe("live queue position in the console (item 3)", () => {
  it("rewrites the server's position", () => {
    const line = "Waiting for another render to finish… (position 2 in queue)";
    expect(withQueuePosition(line, 1)).toBe("Waiting for another render to finish… (position 1 in queue)");
    expect(withQueuePosition(line, null)).toBe(line);
    expect(withQueuePosition("Waiting for another render to finish…", 3)).toBe("Waiting for another render to finish… (position 3 in queue)");
  });

  it("finds the latest queued notice", () => {
    const lines = [
      { id: 1, level: "info", text: "Waiting for another render to finish… (position 2 in queue)" },
      { id: 2, level: "command", text: "$ manim a.py A" },
      { id: 3, level: "info", text: "Waiting for another render to finish… (position 4 in queue)" },
      { id: 4, level: "stdout", text: "Waiting for another render (printed by a script)" },
    ];
    expect(latestQueuedLineId(lines)).toBe(3);
    expect(latestQueuedLineId([])).toBeNull();
  });
});

describe("alternative steps in the meta width (extra f)", () => {
  it("reserves room for the alt chip instead of the ×N badge", () => {
    const step = { type: "play" as const, label: "x", line: 9, duration: 0.3, loop_line: 7, repeat: 4 };
    const counted = stepMetaWidth(step, "0.3s");
    const alt = stepMetaWidth({ ...step, alternative: true }, "0.3s");
    const plain = stepMetaWidth({ type: "play", label: "x", line: 9, duration: 0.3 }, "0.3s");
    expect(alt).toBeGreaterThan(plain);
    expect(alt).toBeLessThan(counted);
  });
});

describe("timeline wrapping (item 4)", () => {
  it("keeps short calls whole and wraps after the attribute dots", () => {
    expect(codeBreakSegments("dot.animate.shift(RIGHT * 0.5)")).toEqual(["dot.", "animate.", "shift(RIGHT * 0.5)"]);
    expect(codeBreakSegments("dot.animate.shift(UP * 0.3)")).toEqual(["dot.", "animate.", "shift(UP * 0.3)"]);
    expect(codeBreakSegments("FadeIn(img)")).toEqual(["FadeIn(img)"]);
  });

  it("still breaks long calls, calls with commas, and strings", () => {
    expect(codeBreakSegments("Transform(c, undefined_name)")).toEqual(["Transform(", "c, ", "undefined_name)"]);
    const long = `shift(${"x".repeat(SHORT_GROUP_CHARS + 1)})`;
    expect(codeBreakSegments(long)).toEqual(["shift(", `${"x".repeat(SHORT_GROUP_CHARS + 1)})`]);
    expect(codeBreakSegments('Text("a b")')).toEqual(["Text(", '"a ', 'b")']);
    for (const text of ["dot.animate.shift(RIGHT * 0.5)", "Write(title), Create(circle)", "f(g(h(1)), 2)", "x[0](y)"]) {
      expect(codeBreakSegments(text).join("")).toBe(text);
    }
    expect(longestSegment("dot.animate.shift(RIGHT * 0.5)")).toBe("shift(RIGHT * 0.5)".length);
  });

  it("makes a wait card wide enough for 'wait · 0.2s ×2 L12' (was 'wai…' at 120 px)", () => {
    const wait: AnimationStep = { type: "wait", label: "Wait 0.2s", line: 12, duration: 0.2, loop_line: 9, repeat: 2 } as AnimationStep;
    const width = stepMetaWidth(wait, "0.2s");
    expect(width).toBeGreaterThan(120);
    expect(width).toBeLessThan(200);
    const plain: AnimationStep = { type: "play", label: "Create(c)", line: 5, duration: 1 } as AnimationStep;
    expect(stepMetaWidth(plain, "1s")).toBeLessThan(width);
  });
});

describe("editor / preview split at narrow widths (item 5)", () => {
  it("gives the preview half the row and a narrower sidebar below 1200 px", () => {
    expect(horizontalDefaults(1024)).toEqual({ sidebarPx: 208, previewPercent: 50 });
    expect(horizontalDefaults(1199)).toEqual({ sidebarPx: 208, previewPercent: 50 });
    expect(horizontalDefaults(1440)).toEqual({ sidebarPx: 240, previewPercent: 42 });
    expect(horizontalDefaults(1920)).toEqual({ sidebarPx: 240, previewPercent: 42 });
  });

  it("puts toasts under the top bar and preview header (item 6)", () => {
    expect(TOAST_TOP_PX).toBe(44 + 40 + 8);
  });
});

describe("work panel minimums on short viewports (extra e)", () => {
  it("keeps the old sizes where they fit", () => {
    expect(workPanelSizes(700)).toEqual({ bottomDefaultPx: 154, topMinPx: 368, bottomMinPx: 120 });
    expect(workPanelSizes(900).topMinPx).toBe(368);
    // ~430 px: exactly room for the 240 px top floor and the 120 px console.
    expect(workPanelSizes(430)).toEqual({ bottomDefaultPx: 120, topMinPx: 241, bottomMinPx: 120 });
  });

  it("never lets the minimums overlap or go negative below ~430 px", () => {
    for (let height = 110; height <= 1200; height += 7) {
      const work = Math.max(0, height - 68);
      const { topMinPx, bottomMinPx, bottomDefaultPx } = workPanelSizes(height);
      expect(topMinPx).toBeGreaterThanOrEqual(0);
      expect(bottomMinPx).toBeGreaterThan(0);
      // Both minimums (and the 1 px handle) fit the work area, and the default console respects both.
      expect(topMinPx + 1 + bottomMinPx).toBeLessThanOrEqual(work + 1);
      expect(bottomDefaultPx).toBeGreaterThanOrEqual(bottomMinPx);
      expect(topMinPx + 1 + bottomDefaultPx).toBeLessThanOrEqual(work + 1);
    }
    expect(workPanelSizes(400)).toEqual({ bottomDefaultPx: 120, topMinPx: 211, bottomMinPx: 120 });
    expect(workPanelSizes(150)).toEqual({ bottomDefaultPx: 81, topMinPx: 0, bottomMinPx: 81 });
  });
});

describe("dialog autofocus ring (item 8)", () => {
  it("marks the button until it loses focus", () => {
    const first = document.createElement("button");
    const second = document.createElement("button");
    document.body.append(first, second);
    focusWithRing(first);
    expect(document.activeElement).toBe(first);
    expect(first.hasAttribute("data-autofocus-ring")).toBe(true);
    second.focus();
    expect(first.hasAttribute("data-autofocus-ring")).toBe(false);
    first.remove();
    second.remove();
  });
});

describe("copying from the console (item 11, extra a)", () => {
  const frame = [
    "╭───────── Traceback (most recent call last) ─────────╮",
    "│ scene.py:7 in construct                             │",
    "│                                                     │",
    "│   6 │   │   self.play(Create(c))                    │",
    "│ ❱ 7 │   │   self.play(Transform(c, undefined_name)) │",
    "│   8 │   │   self.wait()                             │",
    "╰─────────────────────────────────────────────────────╯",
    "NameError: name 'undefined_name' is not defined",
  ];

  it("copies only the code of one traceback line (no ❱, number, gutter or padding)", () => {
    expect(stripBoxDrawing(frame[4])).toBe("self.play(Transform(c, undefined_name))");
    // Triple-click selections end with a newline.
    expect(stripBoxDrawing(`${frame[4]}\n`)).toBe("self.play(Transform(c, undefined_name))");
    // A selection that starts at the marker.
    expect(stripBoxDrawing("❱ 7 │   │   self.play(Transform(c, undefined_name)) │")).toBe("self.play(Transform(c, undefined_name))");
  });

  it("keeps relative indentation across several code lines", () => {
    const rows = ["│   3 │ class A(Scene):              │", "│   4 │     def construct(self):     │", "│ ❱ 5 │ │   │   self.play(Create(c)) │"];
    expect(stripBoxDrawing(rows.join("\n")).split("\n")).toEqual(["class A(Scene):", "    def construct(self):", "        self.play(Create(c))"]);
  });

  it("keeps markers when the selection includes other rows", () => {
    const plain = stripBoxDrawing(frame.join("\n")).split("\n");
    expect(plain).toContain("❱ 7         self.play(Transform(c, undefined_name))");
    expect(plain[0]).toBe("Traceback (most recent call last)");
    expect(plain[plain.length - 1]).toBe("NameError: name 'undefined_name' is not defined");
  });

  it("keeps lines that start with rule characters; only the rule runs go", () => {
    const text = ["│ x = 1 │", "── Locals ──", "─x = 2", "═══ done", "──────", "│ y = 3 │"].join("\n");
    expect(stripBoxDrawing(text).split("\n")).toEqual(["x = 1", "Locals", "x = 2", "done", "", "y = 3"]);
  });

  it("the Copy button copies every line, box drawing removed", () => {
    const lines = [{ text: "$ manim scene.py A" }, ...frame.map((text) => ({ text }))];
    const copied = consoleCopyText(lines, stripBoxDrawing);
    expect(copied.split("\n")[0]).toBe("$ manim scene.py A");
    expect(copied).not.toMatch(/[│╭╮╰╯─]/);
    expect(copied).toContain("❱ 7");
  });
});

describe("KaTeX hint for \\frac{a} (extra d)", () => {
  const messageFor = (formula: string) =>
    `KaTeX parse error: Unexpected end of input in a macro argument, expected '}' at end of input: ${formula}`;

  it("says a balanced formula is missing an argument, not a brace", () => {
    expect(friendlyKatex(messageFor("\\frac{a}"))).toBe("\\frac needs two arguments in braces, e.g. \\frac{a}{b}: one is missing.");
    expect(friendlyKatex(messageFor("\\frac a"))).toMatch(/\\frac needs two arguments/);
    expect(friendlyKatex(messageFor("x + \\sqrt"))).toBe("\\sqrt is missing an argument in braces, e.g. \\sqrt{x}.");
  });

  it("still reports an unclosed brace as one", () => {
    expect(friendlyKatex(messageFor("\\frac{a"))).toBe("Missing closing brace '}': a { … } group isn't closed.");
    expect(friendlyKatex(messageFor("\\frac{a}{"))).toMatch(/Missing closing brace/);
    expect(friendlyKatex(messageFor("\\{ \\frac{a}"))).toMatch(/\\frac needs two arguments/);
  });
});
