// Fix round 3: progress maps Manim's animation index onto loop bodies in execution
// order (a, b, a, b, ...), using the parser's `loops` chain. Ordering logic only.
import { describe, expect, it } from "vitest";
import { executionOrder, stepIndexForAnimation } from "./timeline";
import type { AnimationStep } from "./types";

const play = (label: string, line: number, extra: Partial<AnimationStep> = {}): AnimationStep => ({
  type: "play",
  label,
  line,
  duration: 1,
  ...extra,
});

describe("executionOrder", () => {
  it("interleaves a loop body: [a, b] x 3 -> a, b, a, b, a, b", () => {
    const steps = [
      play("a", 5, { repeat: 3, loop_line: 4, loops: [[4, 8, 3]] }),
      play("b", 6, { repeat: 3, loop_line: 4, loops: [[4, 8, 3]] }),
      play("after", 7),
    ];
    expect(executionOrder(steps)).toEqual([0, 1, 0, 1, 0, 1, 2]);
    expect([0, 1, 2, 3, 4, 5, 6].map((index) => stepIndexForAnimation(steps, index))).toEqual([0, 1, 0, 1, 0, 1, 2]);
  });

  it("expands nested loops in order and multiplies their counts", () => {
    // for i in range(2): (for j in range(3): a) ; b
    const steps = [
      play("a", 6, { repeat: 6, loop_line: 4, loops: [[4, 8, 2], [5, 12, 3]] }),
      play("b", 7, { repeat: 2, loop_line: 4, loops: [[4, 8, 2]] }),
    ];
    expect(executionOrder(steps)).toEqual([0, 0, 0, 1, 0, 0, 0, 1]);
  });

  it("skips loops that run zero times, wherever they are", () => {
    const inner = [
      play("never", 6, { repeat: 0, loop_line: 4, loops: [[4, 8, 3], [5, 12, 0]] }),
      play("b", 7, { repeat: 3, loop_line: 4, loops: [[4, 8, 3]] }),
    ];
    expect(executionOrder(inner)).toEqual([1, 1, 1]);
    const outer = [play("never", 6, { repeat: 0, loop_line: 4, loops: [[4, 8, 0], [5, 12, 3]] }), play("end", 8)];
    expect(executionOrder(outer)).toEqual([1]);
    expect(stepIndexForAnimation(outer, 0)).toBe(1);
  });

  it("keeps two loops on different lines apart", () => {
    const steps = [
      play("a", 5, { repeat: 2, loop_line: 4, loops: [[4, 8, 2]] }),
      play("b", 7, { repeat: 2, loop_line: 6, loops: [[6, 8, 2]] }),
    ];
    expect(executionOrder(steps)).toEqual([0, 0, 1, 1]);
  });

  it("runs an unknown loop once, and falls back to in-place repeats for older servers", () => {
    const unknown = [play("a", 5, { repeat: null, loop_line: 4, loops: [[4, 8, null]] }), play("b", 6)];
    expect(executionOrder(unknown)).toEqual([0, 1]);
    const legacy = [play("a", 5, { repeat: 2, loop_line: 4 }), play("b", 6, { repeat: 2, loop_line: 4 })];
    expect(executionOrder(legacy)).toEqual([0, 0, 1, 1]);
  });

  it("stays cheap for huge literal loops and clamps past the end", () => {
    const steps = [
      play("a", 5, { repeat: 1e12, loop_line: 4, loops: [[4, 8, 1e6], [5, 12, 1e6]] }),
      play("b", 6, { repeat: 1e6, loop_line: 4, loops: [[4, 8, 1e6]] }),
    ];
    expect(executionOrder(steps, 10)).toHaveLength(10);
    expect(stepIndexForAnimation(steps, 5)).toBe(0);
    expect(stepIndexForAnimation([play("a", 1)], 99)).toBe(0);
    expect(stepIndexForAnimation([], 0)).toBeNull();
    expect(stepIndexForAnimation(steps, -1)).toBeNull();
  });
});
