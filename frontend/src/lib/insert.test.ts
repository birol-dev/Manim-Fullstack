import { describe, expect, it } from "vitest";

import { opensBlock, planBlockInsert, stripComment } from "./insert";

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
    expect(planBlockInsert(SCENE, 2, "x = 1").line).toBe(10);
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
});
