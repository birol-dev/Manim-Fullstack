import { describe, expect, it } from "vitest";

import { isInsertRefusal, planBlockInsert } from "./insert";

const BLOCK = "sq = Square()\nself.play(Create(sq))";

function apply(source: string, cursorLine: number): string {
  const lines = source.split("\n");
  const plan = planBlockInsert(lines, cursorLine, BLOCK);
  if (isInsertRefusal(plan)) throw new Error(plan.refused);
  const out = [...lines];
  if (plan.replace) out.splice(plan.line - 1, 1, ...plan.text.split("\n"));
  else out.splice(plan.line, 0, ...plan.text.split("\n"));
  return out.join("\n");
}

const H = ["from manim import *", "class A(Scene):"];

describe("R4 #4: Insert edge cases produce valid Python", () => {
  it("splits a one-line construct() and adds the block to its body", () => {
    const source = [...H, "    def construct(self): self.wait()", ""].join("\n");
    const expected = [...H, "    def construct(self):", "        self.wait()", "        sq = Square()", "        self.play(Create(sq))", ""].join("\n");
    expect(apply(source, 3)).toBe(expected);
    // Cursor below, at module level: the same construct() is the target.
    expect(apply(`${source}\nx = 1\n`, 5)).toBe(`${expected}\nx = 1\n`);
  });

  it("keeps a return annotation and a colon inside a string on the one-line header", () => {
    const source = [...H, '    def construct(self, t: str = "a:b") -> None: self.wait(); self.wait()', ""].join("\n");
    expect(apply(source, 3).split("\n").slice(2, 5)).toEqual([
      '    def construct(self, t: str = "a:b") -> None:',
      "        self.wait(); self.wait()",
      "        sq = Square()",
    ]);
  });

  it("refuses (instead of breaking) a one-line construct() whose header spans lines", () => {
    const lines = [...H, "    def construct(", "        self): self.wait()", ""];
    const plan = planBlockInsert(lines, 4, BLOCK);
    expect(isInsertRefusal(plan) ? plan.refused : "inserted").toMatch(/one line/);
  });

  it("goes above a decorator, never between it and its def", () => {
    const source = [...H, "    def construct(self):", "        @staticmethod", "        def f():", "            pass", "        self.wait()", ""].join("\n");
    expect(apply(source, 4).split("\n").slice(3, 7)).toEqual(["        sq = Square()", "        self.play(Create(sq))", "        @staticmethod", "        def f():"]);
    // A blank line right after the decorator, and a chain of decorators with a comment between.
    const blank = [...H, "    def construct(self):", "        @staticmethod", "", "        def f():", "            pass", ""].join("\n");
    expect(apply(blank, 5).split("\n").slice(3, 6)).toEqual(["        sq = Square()", "        self.play(Create(sq))", "        @staticmethod"]);
    const chain = [...H, "    def construct(self):", "        self.wait()", "        @a", "        # why", "        @b(1,", "           2)", "        def f():", "            pass", ""].join("\n");
    expect(apply(chain, 8).split("\n").slice(4, 7)).toEqual(["        sq = Square()", "        self.play(Create(sq))", "        @a"]);
  });

  it("indents below a comment by the code around it, not by the comment's own indentation", () => {
    const deeper = [...H, "    def construct(self):", "        if True:", "            self.wait()", "        self.wait()", "            # stray", ""].join("\n");
    expect(apply(deeper, 7).split("\n").slice(6, 9)).toEqual(["            # stray", "        sq = Square()", "        self.play(Create(sq))"]);
    // A comment dedented to a level that is open above keeps that level.
    const closes = [...H, "    def construct(self):", "        if True:", "            self.wait()", "        # after the if", ""].join("\n");
    expect(apply(closes, 6).split("\n").slice(5, 7)).toEqual(["        # after the if", "        sq = Square()"]);
    // A comment dedented to a level that isn't a block level falls back to the code above.
    const odd = [...H, "    def construct(self):", "        if True:", "            self.wait()", "          # odd", ""].join("\n");
    expect(apply(odd, 6).split("\n")[6]).toBe("            sq = Square()");
  });
});
