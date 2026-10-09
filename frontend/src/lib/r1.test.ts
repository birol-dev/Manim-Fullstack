import { describe, expect, it } from "vitest";
import katex from "katex";

import { friendlyKatex } from "./katex";
import {
  codeBreakSegments,
  expandedStepCount,
  longestSegment,
  repeatLabel,
  stepIndexForAnimation,
  timelineTotal,
} from "./timeline";
import { groupConsoleRows } from "./traceback";
import type { AnimationStep } from "./types";

function katexError(formula: string): string {
  try {
    katex.renderToString(formula, { displayMode: true, throwOnError: true, strict: "ignore" });
  } catch (error) {
    return (error as Error).message;
  }
  throw new Error(`${formula} rendered`);
}

describe("friendlyKatex", () => {
  it("explains unexpected end of input and drops the position suffix", () => {
    const raw = katexError("\\frac{a");
    expect(raw).toMatch(/Unexpected end of input/);
    const friendly = friendlyKatex(raw);
    expect(friendly).toBe("Missing closing brace '}': a { … } group isn't closed.");
    expect(friendly).not.toMatch(/at end of input|\\frac/);
  });

  it.each([
    ["\\fracc{a}", /Unknown command \\fracc/],
    ["x^", /\^ needs an argument in braces/],
    ["\\sqrt", /\\sqrt needs an argument in braces/],
    ["a}", /extra closing brace/],
    ["{a", /Missing closing brace/],
    ["x^a^b", /Two superscripts/],
    ["\\begin{foo}x\\end{foo}", /Unknown environment 'foo'/],
    ["\\begin{matrix}x\\end{pmatrix}", /\\begin\{matrix\} is closed by \\end\{pmatrix\}/],
    ["\\left( x", /\\left needs a matching \\right/],
    ["$x$", /Remove the \$ signs/],
  ])("%s", (formula, expected) => {
    const friendly = friendlyKatex(katexError(formula));
    expect(friendly).toMatch(expected);
    expect(friendly).not.toMatch(/at position \d+/);
  });

  it("handles the generic Expected/got form and caps the length at 180", () => {
    expect(friendlyKatex("KaTeX parse error: Expected 'EOF', got '&' at position 2: a&̲")).toBe(
      "Check the formula: expected the end of the formula, but found '&'.",
    );
    const long = friendlyKatex(`KaTeX parse error: ${"x".repeat(400)}`);
    expect(long.length).toBe(181);
    expect(long.endsWith("…")).toBe(true);
  });
});

describe("timeline", () => {
  const steps: AnimationStep[] = [
    { type: "play", label: "Write(t)", line: 7, duration: 2, estimated: true },
    { type: "play", label: "FadeIn(sub, shift=UP)", line: 8, duration: 1, estimated: true },
    { type: "wait", label: "Wait 0.5s", line: 9, duration: 0.5 },
  ];

  it("sums Write's text-length run time (text scene ≈ 3.5s, like the rendered video)", () => {
    expect(timelineTotal(steps)).toEqual({ seconds: 3.5, estimated: true, runs: 3, unknownLoops: false });
  });

  it("is exact when every duration is explicit", () => {
    expect(timelineTotal([{ type: "play", label: "x", line: 1, duration: 3 }]).estimated).toBe(false);
  });

  it("multiplies looped steps and flags unknown loop counts", () => {
    const looped: AnimationStep[] = [
      { type: "play", label: "Indicate(dot)", line: 5, duration: 1, estimated: true, repeat: 3, loop_line: 4 },
      { type: "play", label: "FadeOut(m)", line: 8, duration: 1, estimated: true, repeat: null, loop_line: 7 },
      { type: "wait", label: "Wait 1s", line: 9, duration: 1 },
    ];
    expect(timelineTotal(looped)).toEqual({ seconds: 5, estimated: true, runs: 5, unknownLoops: true });
    expect(repeatLabel(looped[0])).toBe("×3");
    expect(repeatLabel(looped[1])).toBe("×?");
    expect(repeatLabel(looped[2])).toBeNull();
    expect(expandedStepCount(looped)).toBe(5);
    // Manim's animation counter runs 0,1,2 inside the first loop, then 3 for FadeOut, 4 for the wait.
    expect(stepIndexForAnimation(looped, 2)).toBe(0);
    expect(stepIndexForAnimation(looped, 3)).toBe(1);
    expect(stepIndexForAnimation(looped, 4)).toBe(2);
    expect(stepIndexForAnimation(looped, null)).toBeNull();
  });

  it("only offers breaks between tokens, never inside identifiers", () => {
    const label = "Write(title), Create(circle)";
    const segments = codeBreakSegments(label);
    expect(segments.join("")).toBe(label);
    expect(segments).toEqual(["Write(", "title), ", "Create(", "circle)"]);
    // No segment starts with a lone comma and identifiers stay whole.
    expect(segments.some((segment) => segment.startsWith(","))).toBe(false);
    expect(codeBreakSegments("img.animate.shift(LEFT * 2)")).toEqual(["img.", "animate.", "shift(", "LEFT ", "* ", "2)"]);
    expect(codeBreakSegments("TransformMatchingTex(eq1, eq2)")).toEqual(["TransformMatchingTex(", "eq1, ", "eq2)"]);
    expect(codeBreakSegments("Circle(color=BLUE, radius=0.5)")).toEqual(["Circle(", "color=", "BLUE, ", "radius=", "0.5)"]);
    expect(codeBreakSegments("x == y")).toEqual(["x == ", "y"]);
    expect(longestSegment("TransformMatchingTex(eq1, eq2)")).toBe("TransformMatchingTex(".length);
  });
});

describe("groupConsoleRows", () => {
  const rich = [
    "INFO     Animation 0 : Partial movie file written",
    "╭─────────── Traceback (most recent call last) ───────────╮",
    "│ /venv/lib/python3.13/site-packages/manim/cli/render/commands.py:12 │",
    "│ 2 in render                                                      │",
    "│                                                                  │",
    "│ ❱ 122 │   │   scene.render()                                     │",
    "│                                                                  │",
    "│ /venv/lib/python3.13/site-packages/manim/scene/scene.py:320 in    │",
    "│ render                                                           │",
    "│ ❱  320 │   │   return self._get_manager().render(preview)        │",
    "│                                                                  │",
    "│ /scene.py:7 in construct                                         │",
    "│                                                                  │",
    "│   6 │   │   self.play(Create(c))                                 │",
    "│ ❱ 7 │   │   self.play(Transform(c, undefined_name))              │",
    "│   8                                                              │",
    "╰──────────────────────────────────────────────────────────────────╯",
    "NameError: name 'undefined_name' is not defined",
  ].map((text, index) => ({ id: index + 1, level: "stderr", text }));

  it("collapses library frames and keeps the user's frame and the error visible", () => {
    const rows = groupConsoleRows(rich, ["scene.py"]);
    const hidden = rows.filter((row) => row.kind === "hidden");
    expect(hidden).toHaveLength(1);
    expect(hidden[0].kind === "hidden" && hidden[0].frames).toBe(2);
    const visible = rows.flatMap((row) => (row.kind === "line" ? [row.entry.text] : []));
    expect(visible.some((text) => text.includes("Traceback"))).toBe(true);
    expect(visible.some((text) => text.includes("/scene.py:7 in construct"))).toBe(true);
    expect(visible.at(-1)).toMatch(/^NameError/);
    expect(visible.some((text) => text.includes("site-packages"))).toBe(false);
  });

  it("links every row of the user's frame, code rows to their own line", () => {
    const rows = groupConsoleRows(rich, ["scene.py"]);
    const lines = rows.flatMap((row) => (row.kind === "line" && row.userFrame ? [[row.entry.text.trim(), row.line, row.failing] as const] : []));
    expect(lines.find(([text]) => text.includes("/scene.py:7"))?.[1]).toBe(7);
    expect(lines.find(([text]) => text.includes("self.play(Create(c))"))?.[1]).toBe(6);
    const failing = lines.find(([, , isFailing]) => isFailing);
    expect(failing?.[1]).toBe(7);
  });

  it("collapses plain Python tracebacks too", () => {
    const plain = [
      "Traceback (most recent call last):",
      '  File "/venv/lib/site-packages/manim/__main__.py", line 10, in main',
      "    render()",
      '  File "/work/scene.py", line 12, in construct',
      "    self.play(Foo())",
      "NameError: name 'Foo' is not defined",
    ].map((text, index) => ({ id: index + 1, level: "stderr", text }));
    const rows = groupConsoleRows(plain, ["scene.py"]);
    expect(rows.map((row) => row.kind)).toEqual(["line", "hidden", "line", "line", "line"]);
    const code = rows[3];
    expect(code.kind === "line" && code.line).toBe(12);
  });

  it("leaves tracebacks without a user frame untouched", () => {
    const rows = groupConsoleRows(rich, ["other.py"]);
    expect(rows.every((row) => row.kind === "line")).toBe(true);
    expect(rows).toHaveLength(rich.length);
  });
});
