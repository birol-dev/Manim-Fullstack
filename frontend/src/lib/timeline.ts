import type { AnimationStep } from "./types";

/** Seconds one run of a timeline step takes, assuming Manim's 1s default when it isn't a literal. */
export function stepSeconds(step: AnimationStep): number {
  return typeof step.duration === "number" && step.duration > 0 ? step.duration : 1;
}

/** True when the step is a branch the parser doesn't count (another branch of that if/match runs instead). */
export function isAlternative(step: AnimationStep): boolean {
  return step.alternative === true;
}

/** True when the step sits inside a loop. */
export function isLooped(step: AnimationStep): boolean {
  return typeof step.loop_line === "number";
}

/** How many times the step runs; 1 for loops whose iteration count the parser can't know. */
export function stepRuns(step: AnimationStep): number {
  return typeof step.repeat === "number" && step.repeat >= 0 ? step.repeat : 1;
}

/** Short badge for a looped step: "×3", or "×?" when the count is only known at runtime. */
export function repeatLabel(step: AnimationStep): string | null {
  if (!isLooped(step)) return null;
  return typeof step.repeat === "number" ? `×${step.repeat}` : "×?";
}

export interface TimelineTotal {
  seconds: number;
  /** Some durations are guesses (Manim defaults, runtime expressions, unknown loop counts). */
  estimated: boolean;
  /** Animations Manim will actually play, counting loop repetitions. */
  runs: number;
  /** Some loops have an unknown iteration count, so the total is a lower bound. */
  unknownLoops: boolean;
}

/**
 * Runs of a step that the parser can vouch for: the product of the *known* loop
 * counts around it, counting a loop of unknown length as one pass. So a ×3 loop
 * inside a ×? loop gives 3 (per outer pass), where stepRuns() gives 1. Display
 * only (the timeline total); progress keeps using stepRuns / executionOrder.
 */
export function knownRuns(step: AnimationStep): number {
  if (!step.loops?.length) return stepRuns(step);
  return step.loops.reduce((product, [, , count]) => product * (typeof count === "number" && count >= 0 ? count : 1), 1);
}

export function timelineTotal(steps: readonly AnimationStep[]): TimelineTotal {
  let seconds = 0;
  let runs = 0;
  let estimated = false;
  let unknownLoops = false;
  for (const step of steps) {
    if (isAlternative(step)) {
      estimated = true;
      continue;
    }
    // An unknown outer loop still multiplies by its known inner loops (per outer pass); the "+" says it's open-ended.
    const count = knownRuns(step);
    seconds += stepSeconds(step) * count;
    runs += count;
    if (typeof step.duration !== "number" || step.estimated) estimated = true;
    if ((isLooped(step) && typeof step.repeat !== "number") || step.loops?.some(([, , loopCount]) => typeof loopCount !== "number")) {
      unknownLoops = true;
    }
  }
  return { seconds: Math.round(seconds * 10) / 10, estimated: estimated || unknownLoops, runs, unknownLoops };
}

/** Animation count Manim will report, counting loop repetitions (unknown loops count once). */
export function expandedStepCount(steps: readonly AnimationStep[]): number {
  return steps.reduce((sum, step) => sum + (isAlternative(step) ? 0 : stepRuns(step)), 0);
}

/**
 * Step indices in the order Manim plays them, expanding loop bodies the way they run:
 * a body [a, b] repeated 3 times gives a, b, a, b, a, b (not a, a, a, b, b, b).
 * Uses each step's `loops` chain from the parser; a loop with an unknown count runs
 * once here, and a step from an older server without `loops` repeats in place.
 * Steps of a branch the parser doesn't count (`alternative`) are skipped: per pass
 * only the counted branch of an if/elif/else or match/case runs here.
 * Stops after *limit* entries so huge literal loops stay cheap.
 */
export function executionOrder(steps: readonly AnimationStep[], limit = Number.POSITIVE_INFINITY): number[] {
  const out: number[] = [];
  const loopKey = (step: AnimationStep, depth: number) => {
    const loop = step.loops?.[depth];
    return loop ? `${loop[0]}:${loop[1]}` : null;
  };

  const expand = (indices: readonly number[], depth: number, into: number[], cap: number) => {
    let position = 0;
    while (position < indices.length && into.length < cap) {
      const step = steps[indices[position]];
      const key = loopKey(step, depth);
      if (key === null) {
        const copies = !step.loops && depth === 0 ? stepRuns(step) : 1;
        for (let copy = 0; copy < copies && into.length < cap; copy += 1) into.push(indices[position]);
        position += 1;
        continue;
      }
      const group: number[] = [];
      while (position < indices.length && loopKey(steps[indices[position]], depth) === key) {
        group.push(indices[position]);
        position += 1;
      }
      const count = step.loops?.[depth]?.[2];
      const times = typeof count === "number" && count >= 0 ? count : 1;
      if (times === 0) continue;
      const body: number[] = [];
      expand(group, depth + 1, body, cap - into.length);
      for (let pass = 0; pass < times && into.length < cap; pass += 1) {
        for (const index of body) {
          if (into.length >= cap) break;
          into.push(index);
        }
      }
    }
  };

  expand(
    steps.map((_, index) => index).filter((index) => !isAlternative(steps[index])),
    0,
    out,
    limit,
  );
  return out;
}

/** Map Manim's running animation index onto the timeline step it belongs to. */
export function stepIndexForAnimation(steps: readonly AnimationStep[], animation: number | null | undefined): number | null {
  if (animation === null || animation === undefined || animation < 0) return null;
  if (!steps.length) return null;
  const order = executionOrder(steps, animation + 1);
  if (animation < order.length) return order[animation];
  return order.length ? order[order.length - 1] : steps.length - 1;
}

/**
 * Split code into segments that may wrap *after* each one, so text breaks
 * between tokens (after "(", ",", ".", "=", spaces) instead of inside an
 * identifier. Joining the segments gives back the input.
 */
export function codeBreakSegments(text: string): string[] {
  const segments: string[] = [];
  let current = "";
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    current += char;
    const next = text[index + 1];
    if (next === undefined) break;
    // Keep closing punctuation and "=" glued to what precedes it ("circle),", "x==").
    const breakAfter =
      (char === "(" || char === "[" || char === "{") ||
      (char === "," && next !== " ") ||
      (char === " " && next !== "=" && next !== ")" && next !== ",") ||
      (char === "." && /[A-Za-z_]/.test(next) && !/\d/.test(text[index - 1] ?? "")) ||
      (char === "=" && next !== "=" && text[index - 1] !== "=" && text[index - 1] !== "!" && text[index - 1] !== "<" && text[index - 1] !== ">");
    if (breakAfter) {
      segments.push(current);
      current = "";
    }
  }
  if (current) segments.push(current);
  return segments;
}

/** Width in characters of the longest unbreakable run in *text*. */
export function longestSegment(text: string): number {
  return codeBreakSegments(text).reduce((max, segment) => Math.max(max, segment.trimEnd().length), 0);
}

/**
 * Split a file name into segments that may wrap after "_", "-", ".", spaces or
 * a lower→upper camelCase step ("qa_asset-final.png" -> "qa_", "asset-", "final.", "png").
 */
export function fileNameSegments(name: string): string[] {
  const segments: string[] = [];
  let current = "";
  for (let index = 0; index < name.length; index += 1) {
    const char = name[index];
    const next = name[index + 1];
    current += char;
    if (next === undefined) break;
    if ("_-. ".includes(char) || (/[a-z0-9]/.test(char) && /[A-Z]/.test(next))) {
      segments.push(current);
      current = "";
    }
  }
  if (current) segments.push(current);
  return segments;
}
