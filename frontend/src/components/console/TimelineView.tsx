import { ListVideo, Repeat } from "lucide-react";

import { CodeText } from "@/components/ui/code-text";
import { EmptyState } from "@/components/ui/panel";
import { formatDuration } from "@/lib/format";
import { longestSegment, repeatLabel, stepSeconds, timelineTotal } from "@/lib/timeline";
import type { AnimationStep } from "@/lib/types";
import { cn } from "@/lib/utils";

const PX_PER_SECOND = 72;
const MIN_BLOCK_PX = 120;
const MAX_BLOCK_PX = 360;
/** Approximate advance of one 11.5px JetBrains Mono glyph, plus the card's padding. */
const CHAR_PX = 7;
const CARD_PADDING_PX = 22;

interface TimelineViewProps {
  scene: string;
  steps: AnimationStep[];
  /** Index of the step Manim is rendering right now. */
  activeIndex: number | null;
  onJumpToLine: (line: number) => void;
}

function stepTitle(step: AnimationStep): string {
  const call = step.type === "play" ? `self.play(${step.label})` : step.label;
  const loop =
    typeof step.loop_line === "number"
      ? ` · in the loop on line ${step.loop_line}${typeof step.repeat === "number" ? `, runs ${step.repeat}×` : ", repeat count known only at runtime"}`
      : "";
  return `Line ${step.line}: ${call}${loop}`;
}

/**
 * Card width: time-proportional, but never narrower than its longest token,
 * and wide enough that a typical label fits in about two lines (short cards).
 */
function stepWidth(step: AnimationStep, label: string): number {
  const byTime = stepSeconds(step) * PX_PER_SECOND;
  const byToken = longestSegment(label) * CHAR_PX + CARD_PADDING_PX;
  const byLines = Math.ceil(label.length / 2) * CHAR_PX + CARD_PADDING_PX;
  return Math.round(Math.min(MAX_BLOCK_PX, Math.max(MIN_BLOCK_PX, byTime, byToken, Math.min(byLines, 260))));
}

export function TimelineView({ scene, steps, activeIndex, onJumpToLine }: TimelineViewProps) {
  if (!scene || steps.length === 0) {
    return (
      <EmptyState
        className="h-full py-4"
        icon={<ListVideo />}
        title={scene ? `No animations in ${scene}` : "No scene selected"}
        description="self.play(...) and self.wait(...) calls in construct() appear here as a timeline."
      />
    );
  }

  const total = timelineTotal(steps);
  const looped = steps.filter((step) => typeof step.loop_line === "number").length;

  return (
    <div className="flex h-full flex-col gap-2 overflow-hidden px-3 py-2">
      <p
        className="shrink-0 text-2xs text-fg-subtle"
        title={
          total.estimated
            ? "Estimated from Manim's default run times (Write scales with text length). Explicit run_time= values are exact."
            : undefined
        }
      >
        <span className="font-medium text-fg-muted">{scene}</span> · {steps.length} {steps.length === 1 ? "step" : "steps"}
        {looped > 0 && (
          <>
            {" "}
            ({looped} in {looped === 1 ? "a loop" : "loops"}
            {total.runs !== steps.length ? `, ${total.runs}${total.unknownLoops ? "+" : ""} plays` : ""})
          </>
        )}{" "}
        · {total.estimated ? "≈ " : ""}
        {formatDuration(total.seconds)}
        {total.unknownLoops ? "+" : ""}
      </p>
      <ol className="flex min-h-0 flex-1 items-start gap-1.5 overflow-auto pb-1">
        {steps.map((step, index) => {
          const isPlay = step.type === "play";
          const seconds = stepSeconds(step);
          const label = isPlay ? step.label : step.label.replace(/^Wait /, "");
          const isActive = activeIndex === index;
          const repeat = repeatLabel(step);
          const durationText =
            typeof step.duration === "number" ? formatDuration(seconds) : isPlay ? "1s" : String(step.duration ?? "1s");
          return (
            <li key={`${step.line}-${index}`} className="flex shrink-0" style={{ width: stepWidth(step, label) }}>
              <button
                type="button"
                onClick={() => onJumpToLine(step.line)}
                title={stepTitle(step)}
                className={cn(
                  "flex w-full flex-col gap-1 rounded-md border px-2.5 py-1.5 text-left transition-colors",
                  isPlay
                    ? "border-accent/25 bg-accent-soft hover:border-accent/60"
                    : "hatched border-dashed border-line-strong hover:border-fg-subtle",
                  isActive && "border-accent ring-1 ring-accent",
                )}
              >
                <span className="flex items-center justify-between gap-2 text-2xs text-fg-subtle">
                  <span className={cn("font-medium", isPlay ? "text-accent" : "text-fg-muted")}>{isPlay ? "play" : "wait"}</span>
                  <span className="tabular-nums">L{step.line}</span>
                </span>
                <span className="code-wrap line-clamp-3 whitespace-normal font-mono text-[11.5px] leading-snug text-fg">
                  <CodeText text={label} />
                </span>
                <span className="flex items-center justify-between gap-2 text-2xs tabular-nums text-fg-subtle">
                  <span>
                    {step.estimated && typeof step.duration === "number" ? "≈ " : ""}
                    {durationText}
                  </span>
                  {repeat && (
                    <span
                      className="inline-flex items-center gap-0.5 rounded bg-overlay px-1 font-medium text-fg-muted"
                      aria-label={typeof step.repeat === "number" ? `Repeats ${step.repeat} times` : "Repeats in a loop"}
                    >
                      <Repeat className="size-2.5" />
                      {repeat}
                    </span>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
