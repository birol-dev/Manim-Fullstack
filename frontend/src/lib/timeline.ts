import type { AnimationStep } from "./types";

/** Seconds one run of a timeline step takes, assuming Manim's 1s default when it isn't a literal. */
export function stepSeconds(step: AnimationStep): number {
  return typeof step.duration === "number" && step.duration > 0 ? step.duration : 1;
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

export function timelineTotal(steps: readonly AnimationStep[]): TimelineTotal {
  let seconds = 0;
  let runs = 0;
  let estimated = false;
  let unknownLoops = false;
  for (const step of steps) {
    const count = stepRuns(step);
    seconds += stepSeconds(step) * count;
    runs += count;
    if (typeof step.duration !== "number" || step.estimated) estimated = true;
    if (isLooped(step) && typeof step.repeat !== "number") unknownLoops = true;
  }
  return { seconds: Math.round(seconds * 10) / 10, estimated: estimated || unknownLoops, runs, unknownLoops };
}

/** Animation count Manim will report, counting loop repetitions (unknown loops count once). */
export function expandedStepCount(steps: readonly AnimationStep[]): number {
  return steps.reduce((sum, step) => sum + stepRuns(step), 0);
}

/** Map Manim's running animation index onto the timeline step it belongs to. */
export function stepIndexForAnimation(steps: readonly AnimationStep[], animation: number | null | undefined): number | null {
  if (animation === null || animation === undefined || animation < 0) return null;
  let seen = 0;
  for (let index = 0; index < steps.length; index += 1) {
    seen += stepRuns(steps[index]);
    if (animation < seen) return index;
  }
  return steps.length ? steps.length - 1 : null;
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
