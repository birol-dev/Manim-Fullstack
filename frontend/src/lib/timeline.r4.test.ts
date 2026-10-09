// Round 4: only one branch of an if/elif/else or match/case inside a loop runs per pass.
// The parser marks the uncounted branches `alternative`; the totals and the execution
// order leave them out, and the total is estimated.
import { describe, expect, it } from "vitest";

import {
  executionOrder,
  expandedStepCount,
  isAlternative,
  stepIndexForAnimation,
  timelineTotal,
} from "./timeline";
import type { AnimationStep } from "./types";

const loop: [number, number, number] = [5, 8, 3];
const steps: AnimationStep[] = [
  {
    type: "play",
    label: "A()",
    line: 7,
    duration: 1,
    estimated: true,
    alternative: true,
    repeat: 3,
    loop_line: 5,
    loops: [loop],
  },
  {
    type: "play",
    label: "B()",
    line: 9,
    duration: 2,
    estimated: true,
    repeat: 3,
    loop_line: 5,
    loops: [loop],
  },
  {
    type: "play",
    label: "C()",
    line: 10,
    duration: 1,
    estimated: true,
    repeat: 3,
    loop_line: 5,
    loops: [loop],
  },
  {
    type: "wait",
    label: "Wait 1s",
    line: 11,
    duration: 1,
    repeat: 3,
    loop_line: 5,
    loops: [loop],
  },
];

describe("branches inside loops", () => {
  it("leaves the uncounted branch out of the totals and marks them estimated", () => {
    expect(isAlternative(steps[0])).toBe(true);
    expect(isAlternative(steps[1])).toBe(false);
    expect(timelineTotal(steps)).toEqual({
      seconds: 12,
      estimated: true,
      runs: 9,
      unknownLoops: false,
    });
    expect(expandedStepCount(steps)).toBe(9);
  });

  it("plays only the counted branch on each pass", () => {
    expect(executionOrder(steps)).toEqual([1, 2, 3, 1, 2, 3, 1, 2, 3]);
    expect(stepIndexForAnimation(steps, 0)).toBe(1);
    expect(stepIndexForAnimation(steps, 5)).toBe(3);
    expect(stepIndexForAnimation(steps, 99)).toBe(3);
  });

  it("an all-alternative list still has a total marked estimated", () => {
    const only = [steps[0]];
    expect(timelineTotal(only)).toEqual({
      seconds: 0,
      estimated: true,
      runs: 0,
      unknownLoops: false,
    });
    expect(executionOrder(only)).toEqual([]);
  });

  it("steps without the flag behave as before", () => {
    const plain = steps.map((step) => ({ ...step, alternative: undefined }));
    expect(timelineTotal(plain).runs).toBe(12);
    expect(executionOrder(plain)).toEqual([0, 1, 2, 3, 0, 1, 2, 3, 0, 1, 2, 3]);
  });
});
