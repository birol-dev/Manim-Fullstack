import { ListVideo } from "lucide-react";

import { EmptyState } from "@/components/ui/panel";
import { formatDuration } from "@/lib/format";
import { stepSeconds } from "@/lib/progress";
import type { AnimationStep } from "@/lib/types";
import { cn } from "@/lib/utils";

const PX_PER_SECOND = 72;
const MIN_BLOCK_PX = 96;
const MAX_BLOCK_PX = 360;

interface TimelineViewProps {
  scene: string;
  steps: AnimationStep[];
  /** Index of the step Manim is rendering right now. */
  activeIndex: number | null;
  onJumpToLine: (line: number) => void;
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

  const total = steps.reduce((sum, step) => sum + stepSeconds(step), 0);
  const estimated = steps.some((step) => typeof step.duration !== "number");

  return (
    <div className="flex h-full flex-col gap-2 overflow-hidden px-3 py-2">
      <p className="shrink-0 text-2xs text-fg-subtle">
        <span className="font-medium text-fg-muted">{scene}</span> · {steps.length} steps · {estimated ? "≈ " : ""}
        {formatDuration(Math.round(total * 10) / 10)}
      </p>
      <ol className="flex min-h-0 flex-1 items-stretch gap-1.5 overflow-x-auto pb-1">
        {steps.map((step, index) => {
          const isPlay = step.type === "play";
          const seconds = stepSeconds(step);
          const width = Math.min(MAX_BLOCK_PX, Math.max(MIN_BLOCK_PX, seconds * PX_PER_SECOND));
          const isActive = activeIndex === index;
          return (
            <li key={`${step.line}-${index}`} className="flex shrink-0" style={{ width }}>
              <button
                type="button"
                onClick={() => onJumpToLine(step.line)}
                title={`Line ${step.line}: ${isPlay ? `self.play(${step.label})` : step.label}`}
                className={cn(
                  "flex min-h-16 w-full flex-col justify-between gap-1 rounded-md border px-2.5 py-2 text-left transition-colors",
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
                <span className="line-clamp-3 whitespace-normal break-words font-mono text-[11.5px] leading-snug text-fg">
                  {isPlay ? step.label : step.label.replace(/^Wait /, "")}
                </span>
                <span className="text-2xs tabular-nums text-fg-subtle">
                  {typeof step.duration === "number" ? formatDuration(seconds) : isPlay ? "1s" : String(step.duration ?? "1s")}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
