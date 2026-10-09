import { Columns2, Download, ExternalLink, Film, History, ImageIcon, Play, Square, XCircle } from "lucide-react";

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
  /** Cancel was requested and the render hasn't stopped yet. */
  stopping?: boolean;
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

function RenderingOverlay({
  active,
  stepCount,
  stopping,
  onCancel,
}: {
  active: ActiveRender;
  stepCount: number;
  stopping: boolean;
  onCancel: () => void;
}) {
  const progress = active.progress;
  const percent = active.queued ? null : overallPercent(active, stepCount);
  let detail = "Starting Manim…";
  if (stopping) {
    detail = active.queued ? "Leaving the queue…" : "Stopping Manim…";
  } else if (active.queued) {
    detail = "Waiting for another render to finish…";
  } else if (progress?.animation !== undefined) {
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
        <p className="text-[13px] font-medium text-fg">
          {active.queued ? "Queued" : "Rendering"} {active.request.scene}
          {active.queued && active.queuePosition ? ` · position ${active.queuePosition}` : ""}
        </p>
        <p className="max-w-80 truncate font-mono text-2xs text-fg-muted" title={detail}>
          {detail}
        </p>
      </div>
      <Tooltip content={stopping ? "Stopping the render…" : "Cancel render"} side="top" wrap>
        <Button size="sm" onClick={onCancel} disabled={stopping}>
          <Square className="fill-current" />
          {stopping ? "Stopping…" : "Cancel"}
        </Button>
      </Tooltip>
    </div>
  );
}

/** Save *url* under *name* without leaving the page (the hidden link never takes focus). */
function downloadFile(url: string, name?: string) {
  const link = document.createElement("a");
  link.href = url;
  if (name) link.download = name;
  else link.setAttribute("download", "");
  link.rel = "noopener";
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  link.remove();
}

export function PreviewPane(props: PreviewPaneProps) {
  const { preview, active, lastOutcome } = props;
  const failed = lastOutcome && !lastOutcome.success && lastOutcome.status !== "cancelled";
  // Manim writes a PNG instead of a video when a scene never calls play() or wait().
  const still = preview?.kind === "image";

  return (
    <section aria-label="Preview" className="flex h-full min-h-0 flex-col bg-surface">
      <PaneHeader className="h-10 justify-between pr-1.5">
        <div className="flex min-w-0 items-center gap-2">
          <PaneTitle>Preview</PaneTitle>
          {/* While rendering, the header names the job, not the clip behind the overlay. */}
          {active ? (
            <span className="truncate text-xs text-fg-muted">
              {active.request.scene} · {active.queued ? "queued" : "rendering"}
            </span>
          ) : (
            preview && <span className="truncate text-xs text-fg-muted">{preview.title}</span>
          )}
        </div>
        <div className="flex items-center gap-0.5">
          {props.canCompare && (
            <Tooltip content="Compare renders side by side">
              <Button variant="ghost" size="icon-sm" aria-label="Compare renders" onClick={props.onCompare}>
                <Columns2 />
              </Button>
            </Tooltip>
          )}
          {preview && !active && (
            <>
              {/* Real buttons (not links): Safari and macOS skip links on Tab by default. */}
              <Tooltip content="Open in new tab">
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Open in new tab"
                  onClick={() => window.open(preview.url, "_blank", "noopener,noreferrer")}
                >
                  <ExternalLink />
                </Button>
              </Tooltip>
              <Tooltip content="Download">
                <Button variant="ghost" size="icon-sm" aria-label="Download" onClick={() => downloadFile(preview.url, preview.downloadName)}>
                  <Download />
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
              // Fewer unlabeled Tab stops in the native controls: no overflow menu (download,
              // speed, cast) and no picture-in-picture button. Playback and looping are unchanged.
              controlsList="nodownload noplaybackrate noremoteplayback"
              disablePictureInPicture
              aria-label={`Video preview: ${preview.title}`}
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

        {preview && !active && (preview.stale || still) && (
          <div className="absolute inset-x-0 top-0 z-10 flex flex-col">
            {preview.stale && (
              <div className="flex items-center justify-center gap-2 bg-warning-soft px-3 py-1.5 text-xs font-medium text-warning">
                <History className="size-3.5 shrink-0" />
                Out of date — the last render didn't replace this preview
              </div>
            )}
            {still && (
              <div role="note" className="flex items-center justify-center gap-2 bg-accent-soft px-3 py-1.5 text-center text-xs font-medium text-accent">
                <ImageIcon className="size-3.5 shrink-0" />
                {preview.title} has no animations, so Manim saved a still image
              </div>
            )}
          </div>
        )}

        {active && (
          <RenderingOverlay active={active} stepCount={props.stepCount} stopping={Boolean(props.stopping)} onCancel={props.onCancel} />
        )}
      </div>

      {preview && (
        <div className="flex h-7 shrink-0 items-center gap-2 border-t border-line px-3">
          {preview.stale && <span className="shrink-0 text-2xs font-medium text-warning">Out of date</span>}
          {still && <span className="shrink-0 text-2xs font-medium text-accent">Still image</span>}
          <span className="truncate font-mono text-xs text-fg-muted select-text" title={preview.location}>
            {preview.location}
          </span>
        </div>
      )}
    </section>
  );
}
