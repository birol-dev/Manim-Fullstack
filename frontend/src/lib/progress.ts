import type { ActiveRender } from "@/hooks/useRenderSession";
import type { AnimationStep } from "./types";

/**
 * Overall progress estimate (0–100) from Manim's per-animation progress and
 * the number of play()/wait() calls parsed from the scene. Returns null before
 * Manim reports anything.
 */
/** Keep the higher of two percents so a looping scene cannot walk the meter backwards. */
export function risingPercent(previous: number | null, next: number | null): number | null {
  if (next === null) return previous;
  if (previous === null) return next;
  return Math.max(previous, next);
}

export function overallPercent(active: ActiveRender, stepCount: number): number | null {
  const progress = active.progress;
  if (!progress) return null;
  if (progress.animation === undefined || stepCount <= 0) return progress.percent;
  const total = Math.max(stepCount, progress.animation + 1);
  return Math.min(100, Math.round(((progress.animation + progress.percent / 100) / total) * 100));
}

/** Seconds a timeline step takes, assuming Manim's 1s default when it isn't a literal. */
export function stepSeconds(step: AnimationStep): number {
  return typeof step.duration === "number" && step.duration > 0 ? step.duration : 1;
}
