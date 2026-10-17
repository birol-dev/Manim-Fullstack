import { describe, expect, it } from "vitest";

import { createConsoleGrouper, groupConsoleRows, parseRichCodeRow, type ConsoleLine } from "./traceback";

/** Rich's real output for r1v_err.py (manim 0.19, COLUMNS=100), paths shortened. */
const REAL = [
  "INFO     Animation 0 : Partial movie file written",
  "╭──────────────────────────── Traceback (most recent call last) ────────────────────────────╮",
  "│ <site-packages>/manim/manager.py:193 in construct                                           │",
  "│                                                                                              │",
  "│   190 │                                                                                      │",
  "│   191 │   def construct(self) -> None:                                                       │",
  "│ ❱ 193 │   │   self.scene.construct()                                                         │",
  "│                                                                                              │",
  "│ r1v_err.py:6 in construct                                                                    │",
  "│                                                                                              │",
  "│   3                                                                                          │",
  "│   4 class ErrScene(Scene):                                                                   │",
  "│   5 │   def construct(self):                                                                 │",
  "│ ❱ 6 │   │   self.play(Foo())                                                                 │",
  "│   7                                                                                          │",
  "╰──────────────────────────────────────────────────────────────────────────────────────────────╯",
  "NameError: name 'Foo' is not defined",
];

const entries = (texts: readonly string[], start = 1): ConsoleLine[] => texts.map((text, index) => ({ id: start + index, level: "stderr", text }));

function lineFor(rows: ReturnType<typeof groupConsoleRows>, needle: string) {
  const row = rows.find((item) => item.kind === "line" && item.entry.text.includes(needle));
  return row?.kind === "line" ? row.line : undefined;
}

describe("parseRichCodeRow (#8 review: rows without the │ guide)", () => {
  it("reads unindented rows, which Rich draws without the guide", () => {
    expect(parseRichCodeRow("│   4 class ErrScene(Scene):    │")).toMatchObject({ line: 4, failing: false });
    expect(parseRichCodeRow("│   1 from manim import *       │")).toMatchObject({ line: 1 });
    expect(parseRichCodeRow("│   3                           │")).toMatchObject({ line: 3 });
  });

  it("reads guided and failing rows, with wide line numbers", () => {
    expect(parseRichCodeRow("│   5 │   def construct(self):  │")).toMatchObject({ line: 5, failing: false });
    expect(parseRichCodeRow("│ ❱ 6 │   │   self.play(Foo())  │")).toMatchObject({ line: 6, failing: true });
    expect(parseRichCodeRow("│ ❱  320 │   │   return x       │")).toMatchObject({ line: 320, failing: true });
    expect(parseRichCodeRow("│   1234 │ x = 1                │")).toMatchObject({ line: 1234 });
  });

  it("doesn't take frame headers, wrapped header tails, or blank rows for code", () => {
    expect(parseRichCodeRow("│ r1v_err.py:6 in construct     │")).toBeNull();
    expect(parseRichCodeRow("│ 2 in render                   │")).toBeNull();
    expect(parseRichCodeRow("│ .py:155 in render             │")).toBeNull();
    expect(parseRichCodeRow("│                               │")).toBeNull();
    expect(parseRichCodeRow("plain 4 text")).toBeNull();
  });

  it("gives the gutter length so only the code part is linked", () => {
    const text = "│   4 class ErrScene(Scene):";
    const row = parseRichCodeRow(text)!;
    expect(text.slice(row.gutter)).toBe("class ErrScene(Scene):");
  });
});

describe("groupConsoleRows on real Rich output", () => {
  const rows = groupConsoleRows(entries(REAL), ["r1v_err.py"]);

  it("links each code row to its own line, including the unguided ones", () => {
    expect(lineFor(rows, "class ErrScene")).toBe(4);
    expect(lineFor(rows, "def construct(self):")).toBe(5);
    expect(lineFor(rows, "self.play(Foo())")).toBe(6);
    expect(lineFor(rows, "│   3 ")).toBe(3);
    expect(lineFor(rows, "r1v_err.py:6 in construct")).toBe(6);
  });

  it("marks only the ❱ row as failing and hides the library frame", () => {
    const failing = rows.filter((row) => row.kind === "line" && row.failing);
    expect(failing).toHaveLength(1);
    expect(failing[0].kind === "line" && failing[0].line).toBe(6);
    expect(rows.filter((row) => row.kind === "hidden")).toHaveLength(1);
  });
});

describe("createConsoleGrouper (incremental, #8 review: no 2,000-line rescan)", () => {
  const filler = (count: number, start: number) => entries(Array.from({ length: count }, (_, index) => `INFO line ${start + index}`), start);

  it("matches groupConsoleRows at every step while lines stream in, tracebacks included", () => {
    const all = [...filler(30, 1), ...entries(REAL, 31), ...filler(10, 31 + REAL.length), ...entries(REAL, 41 + REAL.length)];
    const grouper = createConsoleGrouper<ConsoleLine>();
    for (let end = 1; end <= all.length; end += 1) {
      const logs = all.slice(0, end);
      expect(grouper.group(logs, ["r1v_err.py"])).toEqual(groupConsoleRows(logs, ["r1v_err.py"]));
    }
  });

  it("only groups the new line once the earlier output is settled", () => {
    const grouper = createConsoleGrouper<ConsoleLine>();
    const logs = filler(2000, 1);
    grouper.group(logs, []);
    expect(grouper.scanned).toBe(2000);
    // The buffer is full: one line drops off the front as one arrives.
    const next = [...logs.slice(1), ...filler(1, 2001)];
    expect(grouper.group(next, [])).toEqual(groupConsoleRows(next, []));
    expect(grouper.scanned).toBe(1);
  });

  it("regroups only the open traceback while it streams in", () => {
    const grouper = createConsoleGrouper<ConsoleLine>();
    const head = filler(500, 1);
    const tb = entries(REAL.slice(1), 501);
    grouper.group([...head, ...tb.slice(0, 5)], ["r1v_err.py"]);
    grouper.group([...head, ...tb.slice(0, 6)], ["r1v_err.py"]);
    expect(grouper.scanned).toBe(6);
  });

  it("starts over after the console is cleared or the link files change", () => {
    const grouper = createConsoleGrouper<ConsoleLine>();
    const first = entries(REAL);
    grouper.group(first, ["r1v_err.py"]);
    expect(grouper.group([], ["r1v_err.py"])).toEqual([]);
    const second = entries(REAL, 100);
    expect(grouper.group(second, ["r1v_err.py"])).toEqual(groupConsoleRows(second, ["r1v_err.py"]));
    expect(grouper.group(second, ["other.py"])).toEqual(groupConsoleRows(second, ["other.py"]));
  });

  it("regroups a traceback whose start was trimmed off the front", () => {
    const grouper = createConsoleGrouper<ConsoleLine>();
    const logs = entries(REAL);
    grouper.group(logs, ["r1v_err.py"]);
    const cut = logs.slice(3);
    expect(grouper.group(cut, ["r1v_err.py"])).toEqual(groupConsoleRows(cut, ["r1v_err.py"]));
  });
});
