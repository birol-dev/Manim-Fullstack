import { describe, expect, it } from "vitest";

import { detectIndentUnit, indentBlock, isInsertRefusal, opensBlock, planBlockInsert, scanLines, stripComment, type BlockInsertPlan } from "./insert";

/** Apply a plan the way CodeEditor does, returning the new source. */
function apply(source: string, cursorLine: number, block = "sq = Square()\nself.play(Create(sq))"): string {
  const lines = source.split("\n");
  const plan = planBlockInsert(lines, cursorLine, block);
  if (isInsertRefusal(plan)) throw new Error(plan.refused);
  const out = [...lines];
  if (plan.replace) out.splice(plan.line - 1, 1, ...plan.text.split("\n"));
  else out.splice(plan.line, 0, ...plan.text.split("\n"));
  return out.join("\n");
}

const SCENE = [
  "from manim import *", // 1
  "", // 2
  "", // 3
  "class Intro(Scene):", // 4
  "    def construct(self):  # main", // 5
  "        circle = Circle()", // 6
  "        # Step 1:", // 7
  "        self.play(Create(circle))", // 8
  "", // 9
  "        self.wait()", // 10
  "", // 11
];

describe("insert planning", () => {
  it("strips comments but not # inside strings", () => {
    expect(stripComment("x = 1  # note")).toBe("x = 1  ");
    expect(stripComment('t = Text("#1")  # c')).toBe('t = Text("#1")  ');
    expect(stripComment("t = 'it\\'s # not'")).toBe("t = 'it\\'s # not'");
    expect(opensBlock("def construct(self):  # main")).toBe(true);
    expect(opensBlock("# Step 1:")).toBe(false);
    expect(opensBlock('x = "a:"')).toBe(false);
  });

  it("indents one level deeper after a colon followed by a comment", () => {
    expect(planBlockInsert(SCENE, 5, "dot = Dot()")).toEqual({ line: 5, replace: false, text: "        dot = Dot()" });
  });

  it("keeps a comment line's indentation, even when the comment ends with a colon", () => {
    expect(planBlockInsert(SCENE, 7, "dot = Dot()\nself.add(dot)")).toEqual({
      line: 7,
      replace: false,
      text: "        dot = Dot()\n        self.add(dot)",
    });
  });

  it("fills a blank line inside construct() using the code above it, skipping comments", () => {
    expect(planBlockInsert(SCENE, 9, "dot = Dot()")).toEqual({ line: 9, replace: true, text: "        dot = Dot()" });
    const commented = ["class A(Scene):", "    def construct(self):", "        # Step 1:", ""];
    expect(planBlockInsert(commented, 4, "x = 1")).toEqual({ line: 4, replace: true, text: "        x = 1" });
  });

  it("moves statements from module or class level to the end of construct()", () => {
    // Cursor on line 1 (where it starts when a file opens).
    expect(planBlockInsert(SCENE, 1, 'logo = SVGMobject("assets/logo.svg")')).toEqual({
      line: 10,
      replace: false,
      text: '        logo = SVGMobject("assets/logo.svg")',
    });
    // Blank line between the imports and the class.
    expect((planBlockInsert(SCENE, 2, "x = 1") as BlockInsertPlan).line).toBe(10);
    // On the class line itself.
    expect(planBlockInsert(SCENE, 4, "x = 1")).toEqual({ line: 10, replace: false, text: "        x = 1" });
    // A blank line right after construct()'s last statement is still inside it.
    expect(planBlockInsert(SCENE, 11, "x = 1")).toEqual({ line: 11, replace: true, text: "        x = 1" });
  });

  it("picks the construct() of the class around the cursor", () => {
    const two = [
      "class A(Scene):",
      "    def construct(self):",
      "        self.wait()",
      "",
      "class B(Scene):",
      "    def construct(self):",
      "        self.play(Create(Square()))",
      "",
    ];
    expect(planBlockInsert(two, 5, "x = 1")).toEqual({ line: 7, replace: false, text: "        x = 1" });
    expect(planBlockInsert(two, 1, "x = 1")).toEqual({ line: 3, replace: false, text: "        x = 1" });
  });

  it("leaves code inside any method (and nested blocks) where the cursor is", () => {
    const helper = ["class A(Scene):", "    def helper(self):", "        for i in range(3):", "            pass", "    def construct(self):", "        pass"];
    expect(planBlockInsert(helper, 4, "x = 1")).toEqual({ line: 4, replace: false, text: "            x = 1" });
    expect(planBlockInsert(helper, 3, "x = 1")).toEqual({ line: 3, replace: false, text: "            x = 1" });
  });

  it("falls back to the cursor when there is no construct()", () => {
    expect(planBlockInsert(["x = 1", ""], 2, "y = 2")).toEqual({ line: 2, replace: true, text: "y = 2" });
  });

  // ---- Round 3: logical statements, indentation style, strings ----------------
  describe("multi-line statements (R2 shots 07a-07d)", () => {
    it("goes after a multi-line self.play( call when the cursor is on an argument line (07a)", () => {
      const src = "from manim import *\nclass A(Scene):\n    def construct(self):\n        self.play(\n            Create(Circle()),\n            run_time=2,\n        )\n";
      for (const cursor of [4, 5, 6, 7]) {
        expect(planBlockInsert(src.split("\n"), cursor, "x = 1")).toEqual({ line: 7, replace: false, text: "        x = 1" });
      }
    });

    it("goes after a backslash continuation, at the statement's indentation (07b)", () => {
      const src = "from manim import *\nclass A(Scene):\n    def construct(self):\n        x = 1 + \\\n            2\n        self.wait()";
      expect(planBlockInsert(src.split("\n"), 4, "y = 2")).toEqual({ line: 5, replace: false, text: "        y = 2" });
      expect(planBlockInsert(src.split("\n"), 5, "y = 2")).toEqual({ line: 5, replace: false, text: "        y = 2" });
    });

    it("moves out of a multi-line docstring instead of inserting into it (07c)", () => {
      const src = 'from manim import *\nclass A(Scene):\n    def construct(self):\n        """Doc\n        more:\n        """\n        self.wait()';
      for (const cursor of [4, 5, 6]) {
        expect(planBlockInsert(src.split("\n"), cursor, "x = 1")).toEqual({ line: 6, replace: false, text: "        x = 1" });
      }
    });

    it("keeps a tab-indented file tab-indented (07d)", () => {
      const src = "from manim import *\nclass A(Scene):\n\tdef construct(self):\n\t\tself.wait()\n";
      expect(planBlockInsert(src.split("\n"), 3, "x = 1")).toEqual({ line: 3, replace: false, text: "\t\tx = 1" });
      expect(planBlockInsert(src.split("\n"), 4, "x = 1")).toEqual({ line: 4, replace: false, text: "\t\tx = 1" });
      // Blank last line, and the class line (moves into construct()).
      expect(planBlockInsert(src.split("\n"), 5, "x = 1")).toEqual({ line: 5, replace: true, text: "\t\tx = 1" });
      expect(planBlockInsert(src.split("\n"), 2, "x = 1")).toEqual({ line: 4, replace: false, text: "\t\tx = 1" });
    });

    it("treats a multi-line dict's `key:` line as part of the assignment, not a block opener", () => {
      const src = "from manim import *\nclass A(Scene):\n    def construct(self):\n        d = {\n            'a':\n                1,\n        }\n";
      expect(planBlockInsert(src.split("\n"), 5, "x = 1")).toEqual({ line: 7, replace: false, text: "        x = 1" });
    });

    it("indents into a block whose header spans lines", () => {
      const src = "class A(Scene):\n    def construct(self):\n        if (a and\n                b):  # both\n            pass";
      expect(planBlockInsert(src.split("\n"), 3, "x = 1")).toEqual({ line: 4, replace: false, text: "            x = 1" });
    });

    it("indents a blank line below a continued statement like the statement, not its last physical line", () => {
      const src = "class A(Scene):\n    def construct(self):\n        x = 1 + \\\n            2\n";
      expect(planBlockInsert(src.split("\n"), 5, "y = 2")).toEqual({ line: 5, replace: true, text: "        y = 2" });
    });

    it("uses construct()'s body even when its signature spans lines", () => {
      const src = "class A(Scene):\n    def construct(\n        self,\n    ):\n        self.wait()\n";
      expect(planBlockInsert(src.split("\n"), 1, "x = 1")).toEqual({ line: 5, replace: false, text: "        x = 1" });
    });
  });

  describe("strings", () => {
    it("ignores brackets, quotes and # inside strings, f-strings and comments", () => {
      const src = [
        "class A(Scene):",
        "    def construct(self):",
        '        t = Text("(not open")  # also ( not open',
        "        u = f\"{d['k']} {{literal}} {x:>3}\"",
        "        v = r\"\\\"\" + '#'",
        "        self.wait()",
      ];
      const infos = scanLines(src);
      expect(infos.map((info) => info.open)).toEqual([false, false, false, false, false, false]);
      expect(planBlockInsert(src, 4, "x = 1")).toEqual({ line: 4, replace: false, text: "        x = 1" });
    });

    it("handles f-strings with nested quotes (Python 3.12) and triple-quoted f-strings with fields across lines", () => {
      const src = ['        a = f"{x["k"]}"', '        b = f"""{', "            y", '        }"""', "        c = 1"];
      const infos = scanLines(src);
      expect(infos.map((info) => info.open)).toEqual([false, true, true, false, false]);
      expect(infos.map((info) => info.continues)).toEqual([false, false, true, true, false]);
    });

    it("moves past a triple-quoted string assignment spanning lines, whatever the inner indentation", () => {
      const src = "class A(Scene):\n    def construct(self):\n        s = '''\nno indent:\n'''\n        self.wait()";
      expect(planBlockInsert(src.split("\n"), 4, "x = 1")).toEqual({ line: 5, replace: false, text: "        x = 1" });
    });

    it("refuses a cursor inside a string that never ends, and an unclosed bracket at the end of the file", () => {
      const open = 'class A(Scene):\n    def construct(self):\n        """never closed\n        x';
      const refusal = planBlockInsert(open.split("\n"), 4, "x = 1");
      expect(isInsertRefusal(refusal) && refusal.refused).toMatch(/string that never ends/);
      const bracket = "class A(Scene):\n    def construct(self):\n        self.play(\n";
      const other = planBlockInsert(bracket.split("\n"), 3, "x = 1");
      expect(isInsertRefusal(other) && other.refused).toMatch(/never ends/);
    });

    it("recovers from an unterminated single-quoted string at the line end like Python", () => {
      expect(scanLines(['x = "oops', "y = 1"]).map((info) => info.open)).toEqual([false, false]);
      // A backslash at the end keeps a single-quoted string going.
      expect(scanLines(['x = "a\\', 'b"', "y"]).map((info) => info.continues)).toEqual([false, true, false]);
    });
  });

  describe("indentation style", () => {
    it("detects tabs, 2 spaces and 4 spaces", () => {
      expect(detectIndentUnit(["class A:", "\tdef f(self):", "\t\tpass"])).toBe("\t");
      expect(detectIndentUnit(["class A:", "  def f(self):", "    pass"])).toBe("  ");
      expect(detectIndentUnit(["class A:", "    def f(self):", "        pass"])).toBe("    ");
      expect(detectIndentUnit(["x = 1"])).toBe("    ");
    });

    it("re-indents a block's own nesting with the file's unit", () => {
      expect(indentBlock("for i in range(3):\n    self.wait()", "\t\t", "\t")).toBe("\t\tfor i in range(3):\n\t\t\tself.wait()");
      const src = "class A(Scene):\n  def construct(self):\n    self.wait()";
      expect(apply(src, 3, "for i in range(2):\n    self.wait()")).toBe(
        "class A(Scene):\n  def construct(self):\n    self.wait()\n    for i in range(2):\n      self.wait()",
      );
    });
  });

  it("keeps the round-1 cases working", () => {
    const plan = planBlockInsert(SCENE, 5, "dot = Dot()") as BlockInsertPlan;
    expect(plan.text).toBe("        dot = Dot()");
    expect(opensBlock("    for x in y:  # note")).toBe(true);
    expect(opensBlock("x = {'a':")).toBe(false);
  });
});
