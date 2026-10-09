import { Columns2, Download, ExternalLink, Film, History, Play, Square, XCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { EmptyState, Kbd, PaneHeader, PaneTitle } from "@/components/ui/panel";
import { Tooltip } from "@/components/ui/tooltip";
import type { ActiveRender, RenderOutcome } from "@/hooks/useRenderSession";
import { MOD_KEY } from "@/lib/constants";
import { overallPercent } from "@/lib/progress";
import type { PreviewItem } from "@/lib/types";

interface PreviewPaneProps {
  preview: PreviewItem | null;
  active: ActiveRender | null;
  /** Number of play()/wait() calls in the scene being rendered, when known. */
  stepCount: number;
  lastOutcome: RenderOutcome | null;
  loop: boolean;
  selectedScene: string;
  canRender: boolean;
  canCompare: boolean;
  onRender: () => void;
  onCancel: () => void;
  onCompare: () => void;
  onShowConsole: () => void;
}

function ProgressRing({ percent }: { percent: number | null }) {
  const radius = 26;
  const circumference = 2 * Math.PI * radius;
  return (
    <div className="relative size-16">
      <svg viewBox="0 0 64 64" className={percent === null ? "size-16 animate-spin" : "size-16 -rotate-90"}>
        <circle cx="32" cy="32" r={radius} fill="none" stroke="currentColor" strokeWidth="4" className="text-white/10" />
        <circle
          cx="32"
          cy="32"
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth="4"
          strokeLinecap="round"
          className="text-accent transition-[stroke-dashoffset] duration-300"
          strokeDasharray={circumference}
          strokeDashoffset={percent === null ? circumference * 0.75 : circumference * (1 - percent / 100)}
        />
      </svg>
      {percent !== null && (
        <span className="absolute inset-0 flex items-center justify-center text-xs font-semibold tabular-nums text-fg">{percent}%</span>
      )}
    </div>
  );
}

function RenderingOverlay({ active, stepCount, onCancel }: { active: ActiveRender; stepCount: number; onCancel: () => void }) {
  const progress = active.progress;
  const percent = overallPercent(active, stepCount);
  let detail = "Starting Manim…";
  if (progress?.animation !== undefined) {
    const total = Math.max(stepCount, progress.animation + 1);
    detail = `Animation ${progress.animation + 1} of ${total}${progress.label ? ` · ${progress.label}` : ""}`;
  } else if (progress) {
    detail = "Rendering frames…";
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-4 bg-black/75 p-6 text-center backdrop-blur-sm animate-in fade-in-0"
    >
      <ProgressRing percent={percent} />
      <div className="flex max-w-full flex-col gap-1">
        <p className="text-[13px] font-medium text-fg">Rendering {active.request.scene}</p>
        <p className="max-w-80 truncate font-mono text-2xs text-fg-muted" title={detail}>
          {detail}
        </p>
      </div>
      <Button size="sm" onClick={onCancel}>
        <Square className="fill-current" />
        Cancel
      </Button>
    </div>
  );
}

export function PreviewPane(props: PreviewPaneProps) {
  const { preview, active, lastOutcome } = props;
  const failed = lastOutcome && !lastOutcome.success && lastOutcome.status !== "cancelled";

  return (
    <section aria-label="Preview" className="flex h-full min-h-0 flex-col bg-surface">
      <PaneHeader className="h-10 justify-between pr-1.5">
        <div className="flex min-w-0 items-center gap-2">
          <PaneTitle>Preview</PaneTitle>
          {preview && <span className="truncate text-xs text-fg-muted">{preview.title}</span>}
        </div>
        <div className="flex items-center gap-0.5">
          {props.canCompare && (
            <Tooltip content="Compare renders side by side">
              <Button variant="ghost" size="icon-sm" aria-label="Compare renders" onClick={props.onCompare}>
                <Columns2 />
              </Button>
            </Tooltip>
          )}
          {preview && (
            <>
              <Tooltip content="Open in new tab">
                <Button asChild variant="ghost" size="icon-sm">
                  <a href={preview.url} target="_blank" rel="noreferrer" aria-label="Open in new tab">
                    <ExternalLink />
                  </a>
                </Button>
              </Tooltip>
              <Tooltip content="Download">
                <Button asChild variant="ghost" size="icon-sm">
                  <a href={preview.url} download={preview.downloadName} aria-label="Download">
                    <Download />
                  </a>
                </Button>
              </Tooltip>
            </>
          )}
        </div>
      </PaneHeader>

      <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden bg-black">
        {preview ? (
          preview.kind === "image" ? (
            <img key={preview.url} src={preview.url} alt={preview.title} className="max-h-full max-w-full object-contain" />
          ) : (
            <video
              key={preview.url}
              src={preview.url}
              controls
              autoPlay
              muted
              playsInline
              loop={props.loop && !preview.stale}
              className="max-h-full max-w-full"
            />
          )
        ) : failed ? (
          <EmptyState
            icon={<XCircle className="text-danger" />}
            title="Render failed"
            description="Manim stopped with an error. The console shows the traceback; click a line reference to jump to it."
            action={
              <Button size="sm" onClick={props.onShowConsole}>
                Show console
              </Button>
            }
          />
        ) : (
          <EmptyState
            icon={<Film />}
            title="Nothing rendered yet"
            description={
              <>
                Render {props.selectedScene ? <span className="text-fg-muted">{props.selectedScene}</span> : "a scene"} to preview it
                here. Shortcut: <Kbd>{MOD_KEY}</Kbd> <Kbd>Enter</Kbd>
              </>
            }
            action={
              <Button variant="primary" size="sm" onClick={props.onRender} disabled={!props.canRender}>
                <Play className="fill-current" />
                Render
              </Button>
            }
          />
        )}

        {preview?.stale && !active && (
          <div className="absolute inset-x-0 top-0 z-10 flex items-center justify-center gap-2 bg-warning-soft px-3 py-1.5 text-xs font-medium text-warning">
            <History className="size-3.5 shrink-0" />
            Out of date — the last render didn't replace this preview
          </div>
        )}

        {active && <RenderingOverlay active={active} stepCount={props.stepCount} onCancel={props.onCancel} />}
      </div>

      {preview && (
        <div className="flex h-7 shrink-0 items-center gap-2 border-t border-line px-3">
          {preview.stale && <span className="shrink-0 text-2xs font-medium text-warning">Out of date</span>}
          <span className="truncate font-mono text-2xs text-fg-subtle select-text" title={preview.location}>
            {preview.location}
          </span>
        </div>
      )}
    </section>
  );
}
