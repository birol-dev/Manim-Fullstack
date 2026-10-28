/** The big live preview, with a storyboard view (a contact sheet of moments from the video). */
import { AlertTriangle, Film, Image as ImageIcon, RotateCw } from "lucide-react";

import { apiUrl } from "@/lib/api";
import { cn } from "@/lib/utils";

import { previewProblem } from "./api";
import { Segments, Spinner } from "./components";
import { fieldErrorsOf } from "./errors";
import { useSmoothImage } from "./hooks";
import { ASPECTS, formatSeconds } from "./options";
import { formatDuration } from "./schemaForm";
import type { Aspect, PreviewResponse } from "./types";

export type PreviewView = "poster" | "storyboard";

export interface PreviewFeed {
  response: PreviewResponse | null;
  pending: boolean;
  error: unknown;
  retry: () => void;
}

interface PreviewPanelProps {
  view: PreviewView;
  onViewChange: (view: PreviewView) => void;
  poster: PreviewFeed;
  storyboard: PreviewFeed;
  aspect: Aspect;
  transparent: boolean;
  /** Seconds, for the caption. */
  length: number | null;
}

function Stage({ feed, ratio, transparent, label }: { feed: PreviewFeed; ratio: number; transparent: boolean; label: string }) {
  const url = feed.response ? apiUrl(feed.response.url) : null;
  const shown = useSmoothImage(url);
  const fieldProblems = fieldErrorsOf(feed.error).length > 0;
  const otherError = feed.error && !fieldProblems ? previewProblem(feed.error) : null;
  const busy = feed.pending || (!!url && shown !== url);
  return (
    <div className="studio-preview-stage relative flex min-h-0 flex-1 items-center justify-center">
      <div
        className={cn(
          "relative overflow-hidden rounded-xl shadow-[0_20px_60px_-20px_rgb(0_0_0/0.7)] ring-1 ring-line-strong",
          transparent ? "studio-checker" : "bg-raised",
        )}
        style={{ aspectRatio: String(ratio), width: `min(100cqw, calc(100cqh * ${ratio}))` }}
      >
        {shown ? (
          <img src={shown} alt={label} className="absolute inset-0 size-full object-contain" draggable={false} />
        ) : (
          <div className="studio-shimmer absolute inset-0 flex items-center justify-center">
            {!feed.error && (
              <span className="flex items-center gap-2 rounded-full bg-canvas/70 px-3 py-1.5 text-sm text-fg-muted">
                <Spinner /> Getting your preview ready…
              </span>
            )}
          </div>
        )}
        {busy && shown && (
          <span
            role="status"
            className="absolute right-2 top-2 flex items-center gap-1.5 rounded-full bg-canvas/75 px-2.5 py-1 text-xs text-fg-muted backdrop-blur-sm"
          >
            <Spinner className="size-3.5" /> Updating…
          </span>
        )}
        {(fieldProblems || otherError) && !busy && (
          <div className="absolute inset-x-2 bottom-2 flex items-center gap-2 rounded-lg border border-warning/30 bg-canvas/85 px-3 py-2 text-xs text-fg-muted backdrop-blur-sm">
            <AlertTriangle aria-hidden className="size-4 shrink-0 text-warning" />
            <span className="min-w-0 flex-1">
              {fieldProblems ? "Some fields need a fix before the preview can update. They're marked in red." : otherError}
            </span>
            {otherError && (
              <button type="button" onClick={feed.retry} className="flex shrink-0 items-center gap-1 rounded-md px-2 py-1 font-medium text-fg hover:bg-raised">
                <RotateCw className="size-3.5" /> Try again
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export function PreviewPanel({ view, onViewChange, poster, storyboard, aspect, transparent, length }: PreviewPanelProps) {
  const format = ASPECTS.find((item) => item.value === aspect) ?? ASPECTS[0];
  const sheet = storyboard.response;
  const sheetRatio = sheet && sheet.width && sheet.height ? sheet.width / sheet.height : 16 / 9;
  const info = sheet?.storyboard;
  const videoLength = info?.length ?? length;
  return (
    <section aria-label="Preview" className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Segments
          size="sm"
          value={view}
          onChange={onViewChange}
          aria-label="Preview view"
          className="w-auto"
          options={[
            { value: "poster", label: <><ImageIcon className="size-3.5" /> Preview</> },
            { value: "storyboard", label: <><Film className="size-3.5" /> Storyboard</> },
          ]}
        />
        <p className="text-xs text-fg-subtle">
          {format.label} {format.value}
          {videoLength ? ` · ${formatSeconds(videoLength)}` : ""}
        </p>
      </div>
      {view === "poster" ? (
        <Stage feed={poster} ratio={format.w / format.h} transparent={transparent} label="Preview of your video" />
      ) : (
        <>
          <Stage feed={storyboard} ratio={sheetRatio} transparent={transparent} label="Storyboard: moments from your video" />
          {info?.times?.length ? (
            <p className="text-center text-xs text-fg-subtle">
              {info.times.length} moments, at{" "}
              {info.times.map((time) => ((videoLength ?? 0) < 60 ? `${Math.round(time * 10) / 10} s` : formatDuration(time))).join(", ")}
            </p>
          ) : (
            <p className="text-center text-xs text-fg-subtle">A few moments from your video, from start to finish.</p>
          )}
        </>
      )}
    </section>
  );
}
