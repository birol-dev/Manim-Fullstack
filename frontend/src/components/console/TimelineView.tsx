import { useRef, useState } from "react";
import { ListVideo, Repeat } from "lucide-react";

import { CodeText } from "@/components/ui/code-text";
import { EmptyState } from "@/components/ui/panel";
import { formatDuration } from "@/lib/format";
import { longestSegment, repeatLabel, stepMetaWidth, stepSeconds, timelineTotal } from "@/lib/timeline";
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
function stepWidth(step: AnimationStep, label: string, durationText: string): number {
  const byTime = stepSeconds(step) * PX_PER_SECOND;
  // The meta row ("wait · 0.2s  ×2  L12") never truncates.
  const byMeta = stepMetaWidth(step, durationText);
  const byToken = longestSegment(label) * CHAR_PX + CARD_PADDING_PX;
  // Half the label plus slack for token-boundary wrapping, so a typical call fits two lines (short consoles).
  const byLines = (Math.ceil(label.length / 2) + 6) * CHAR_PX + CARD_PADDING_PX;
  return Math.round(Math.min(MAX_BLOCK_PX, Math.max(MIN_BLOCK_PX, byTime, byToken, byMeta, Math.min(byLines, 260))));
}

const NEXT_KEYS = ["ArrowRight", "ArrowDown"];
const PREVIOUS_KEYS = ["ArrowLeft", "ArrowUp"];

export function TimelineView({ scene, steps, activeIndex, onJumpToLine }: TimelineViewProps) {
  // Roving focus: the card list is one Tab stop; arrows, Home and End move between cards.
  const [focused, setFocused] = useState<number | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
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
  // The remembered card, else the one rendering now, else the first.
  const current = focused !== null && focused < steps.length ? focused : activeIndex !== null && activeIndex < steps.length ? activeIndex : 0;
  const looped = steps.filter((step) => typeof step.loop_line === "number").length;

  return (
    <div className="flex h-full flex-col gap-2 overflow-hidden px-3 py-2">
      <p
        className="shrink-0 text-2xs text-fg-subtle"
        title={
          [
            total.estimated
              ? "Estimated from Manim's default run times (Write scales with text length). Explicit run_time= values are exact."
              : "",
            total.unknownLoops
              ? "A loop's count is only known at runtime: the total counts one pass of it (known inner loops included), so the real length is open-ended (+)."
              : "",
          ]
            .filter(Boolean)
            .join(" ") || undefined
        }
      >
        <span className="font-medium text-fg-muted">{scene}</span> · {steps.length} {steps.length === 1 ? "step" : "steps"}
        {looped > 0 && (
          <>
            {" "}
            ({looped} in {looped === 1 ? "a loop" : "loops"}
            {total.runs !== steps.length || total.unknownLoops ? `, ${total.runs}${total.unknownLoops ? "+" : ""} plays` : ""})
          </>
        )}{" "}
        · {total.estimated ? "≈ " : ""}
        {formatDuration(total.seconds)}
        {total.unknownLoops ? "+" : ""}
      </p>
      <div
        ref={listRef}
        role="listbox"
        aria-label={`Animation steps in ${scene}`}
        aria-orientation="horizontal"
        aria-describedby="timeline-keys"
        onKeyDown={(event) => {
          const index = current;
          let next: number | null = null;
          if (NEXT_KEYS.includes(event.key)) next = Math.min(steps.length - 1, index + 1);
          else if (PREVIOUS_KEYS.includes(event.key)) next = Math.max(0, index - 1);
          else if (event.key === "Home") next = 0;
          else if (event.key === "End") next = steps.length - 1;
          else if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onJumpToLine(steps[index].line);
            return;
          }
          if (next === null) return;
          event.preventDefault();
          setFocused(next);
          const option = listRef.current?.querySelector<HTMLElement>(`[data-step-index="${next}"]`);
          option?.focus();
          option?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
        }}
        className="flex min-h-0 flex-1 items-start gap-1.5 overflow-auto pb-1"
      >
        {steps.map((step, index) => {
          const isPlay = step.type === "play";
          const seconds = stepSeconds(step);
          const label = isPlay ? step.label : step.label.replace(/^Wait /, "");
          const isActive = activeIndex === index;
          const repeat = repeatLabel(step);
          const durationText =
            typeof step.duration === "number" ? formatDuration(seconds) : isPlay ? "1s" : String(step.duration ?? "1s");
          return (
            <div key={`${step.line}-${index}`} className="flex shrink-0" style={{ width: stepWidth(step, label, durationText) }}>
              <div
                role="option"
                data-step-index={index}
                tabIndex={index === current ? 0 : -1}
                aria-selected={index === current}
                aria-current={isActive ? "step" : undefined}
                aria-label={`${stepTitle(step)} · ${step.estimated && typeof step.duration === "number" ? "about " : ""}${durationText}`}
                onClick={() => {
                  setFocused(index);
                  onJumpToLine(step.line);
                }}
                onFocus={() => setFocused(index)}
                title={stepTitle(step)}
                className={cn(
                  "flex w-full cursor-pointer flex-col gap-1 rounded-md border px-2.5 py-1.5 text-left transition-colors focus-visible:outline-2 focus-visible:-outline-offset-1 focus-visible:outline-accent",
                  isPlay
                    ? "border-accent/25 bg-accent-soft hover:border-accent/60"
                    : "hatched border-dashed border-line-strong hover:border-fg-subtle",
                  isActive && "border-accent ring-1 ring-accent",
                )}
              >
                {/* One meta row (kind · duration … loop · line) keeps cards ~20 px shorter, so they fit a short console. */}
                <span className="flex items-center justify-between gap-2 text-2xs tabular-nums text-fg-subtle">
                  <span className="min-w-0 truncate">
                    <span className={cn("font-medium", isPlay ? "text-accent" : "text-fg-muted")}>{isPlay ? "play" : "wait"}</span>
                    {" · "}
                    {step.estimated && typeof step.duration === "number" ? "≈ " : ""}
                    {durationText}
                  </span>
                  <span className="flex shrink-0 items-center gap-1.5">
                    {repeat && (
                      <span
                        className="inline-flex items-center gap-0.5 rounded bg-overlay px-1 font-medium text-fg-muted"
                        aria-label={typeof step.repeat === "number" ? `Repeats ${step.repeat} times` : "Repeats in a loop"}
                      >
                        <Repeat className="size-2.5" />
                        {repeat}
                      </span>
                    )}
                    <span>L{step.line}</span>
                  </span>
                </span>
                <span className="code-wrap line-clamp-3 whitespace-normal font-mono text-[11.5px] leading-snug text-fg">
                  <CodeText text={label} />
                </span>
              </div>
            </div>
          );
        })}
      </div>
      <p id="timeline-keys" className="sr-only">
        Arrow keys move between steps, Home and End jump to the first and last, Enter jumps to the step's line.
      </p>
    </div>
  );
}
