/** The big live preview, with a storyboard view (a contact sheet of moments from the video). */
import { AlertTriangle, Image as ImageIcon, LayoutGrid, Pause, Play, RotateCw, X } from "lucide-react";
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

import { apiUrl } from "@/lib/api";
import { cn } from "@/lib/utils";

import { previewProblem } from "./api";
import { Segments, Spinner } from "./components";
import { fieldErrorsOf } from "./errors";
import { useSmoothImage } from "./hooks";
import { ASPECTS } from "./options";
import { formatDuration } from "./schemaForm";
import { fitStoryboard, spokenDuration } from "./storyboard";
import type { Aspect, PreviewRequest, PreviewResponse } from "./types";
import { useMotionPreview } from "./useMotionPreview";

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
  motionRequest?: PreviewRequest;
  motionSession?: string;
}

function Stage({ feed, ratio, transparent, label, children }: { feed: PreviewFeed; ratio: number; transparent: boolean; label: string; children?: ReactNode }) {
  const url = feed.response ? apiUrl(feed.response.url) : null;
  const shown = useSmoothImage(url);
  const fieldProblems = fieldErrorsOf(feed.error).length > 0;
  const otherError = feed.error && !fieldProblems ? previewProblem(feed.error) : null;
  const busy = feed.pending || (!!url && shown !== url);
  return (
    <div className="studio-preview-stage relative flex min-h-0 flex-1 items-center justify-center">
      <div
        className={cn(
          "studio-preview-frame",
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
            className="studio-updating-chip"
          >
            <Spinner className="size-3.5" /> Updating
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
        {children}
      </div>
    </div>
  );
}

function StoryboardStage({ count, ratio, caption, children, pending }: { count: number; ratio: number; caption: string; children: ReactNode; pending: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  useEffect(() => {
    const stage = ref.current;
    if (!stage) return;
    const observer = new ResizeObserver(([entry]) => {
      setSize({ width: entry.contentRect.width, height: entry.contentRect.height });
    });
    observer.observe(stage);
    return () => observer.disconnect();
  }, []);
  const fit = fitStoryboard(count, ratio, size.width, size.height);
  return (
    <div ref={ref} className="studio-storyboard-stage">
      {pending && <span className="studio-updating-chip" role="status"><Spinner /> Updating</span>}
      <div className="studio-storyboard-content">
        <div className="studio-storyboard-grid" style={{ "--storyboard-columns": fit.columns, width: fit.width } as CSSProperties}>
          {children}
        </div>
        <p className="studio-preview-caption">{caption}</p>
      </div>
    </div>
  );
}

function MotionVideo({ url, posterUrl, initialDuration, onError }: { url: string; posterUrl?: string; initialDuration: number; onError: () => void }) {
  const ref = useRef<HTMLVideoElement>(null);
  const [paused, setPaused] = useState(false);
  const [position, setPosition] = useState(0);
  const [duration, setDuration] = useState(initialDuration);
  const toggle = () => {
    const video = ref.current;
    if (!video) return;
    if (video.paused) void video.play().catch(() => setPaused(true));
    else video.pause();
  };
  return <div className="studio-motion-video" tabIndex={0} aria-label="Animation preview" onKeyDown={(event) => {
    if (event.code === "Space" && !event.repeat && event.target === event.currentTarget) { event.preventDefault(); toggle(); }
  }}>
    <video ref={ref} src={apiUrl(url)} poster={posterUrl ? apiUrl(posterUrl) : undefined} autoPlay loop muted playsInline onError={onError}
      onPlay={() => setPaused(false)} onPause={() => setPaused(true)}
      onLoadedMetadata={() => { setDuration(ref.current?.duration || 0); void ref.current?.play().catch(() => setPaused(true)); }}
      onTimeUpdate={() => setPosition(ref.current?.currentTime || 0)} aria-label="Your animation" />
    <div className="studio-motion-controls">
      <button type="button" onClick={toggle} aria-label={paused ? "Play animation" : "Pause animation"}>{paused ? <Play /> : <Pause />}</button>
      <input type="range" aria-label="Preview position" min={0} max={duration || 1} step={0.05} value={position} onChange={(event) => {
        const time = Number(event.target.value);
        if (ref.current) ref.current.currentTime = time;
        setPosition(time);
      }} />
      <span>{formatDuration(Math.floor(position))} / {formatDuration(Math.floor(duration))}</span>
    </div>
  </div>;
}

function MotionOverlay({ request, session, ready, posterUrl }: { request: PreviewRequest; session: string; ready: boolean; posterUrl?: string }) {
  const motion = useMotionPreview(request, session);
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const url = motion.response?.url;
  if (url && failedUrl !== url) return <>
    <MotionVideo key={url} url={url} posterUrl={posterUrl} initialDuration={motion.response?.duration ?? 0} onError={() => setFailedUrl(url)} />
    {motion.response?.truncated && <span className="studio-motion-cap">First 20 seconds</span>}
  </>;
  if (motion.pending) return <>
    <span className="studio-motion-dim" aria-hidden />
    <div className="studio-motion-controls studio-motion-making">
      <Spinner /><span role="status">Making a quick preview…</span>
      <div className="studio-motion-progress" role="progressbar" aria-label="Making a quick preview"><span /></div>
      <button type="button" aria-label="Cancel preview" onClick={motion.cancel}><X aria-hidden /></button>
    </div>
  </>;
  if (motion.error || url && failedUrl === url) return <div className="studio-motion-controls studio-motion-error" role="alert">
    <span>Couldn't play this preview. Please try again.</span>
    <button type="button" onClick={() => { setFailedUrl(null); void motion.start(); }}><RotateCw /> Try again</button>
  </div>;
  return <button type="button" className="studio-motion-controls studio-motion-play" disabled={!ready} aria-label="Play animation" onClick={() => void motion.start()}><Play aria-hidden fill="currentColor" /><span>Play</span></button>;
}

export function PreviewPanel({ view, onViewChange, poster, storyboard, aspect, transparent, length, motionRequest, motionSession = "editor" }: PreviewPanelProps) {
  const format = ASPECTS.find((item) => item.value === aspect) ?? ASPECTS[0];
  const sheet = storyboard.response;
  const sheetRatio = sheet && sheet.width && sheet.height ? sheet.width / sheet.height : 16 / 9;
  const info = sheet?.storyboard;
  const videoLength = length ?? info?.length ?? 0;
  const caption = `${format.value} · ${spokenDuration(videoLength)}`;
  return (
    <section aria-label="Preview" className="studio-preview-panel">
      <div className="studio-preview-toolbar">
        <Segments
          size="sm"
          value={view}
          onChange={onViewChange}
          aria-label="Preview view"
          className="studio-preview-view"
          options={[
            { value: "poster", label: <><ImageIcon className="size-3.5" /> Preview</> },
            { value: "storyboard", label: <><LayoutGrid className="size-3.5" /> Storyboard</> },
          ]}
        />
      </div>
      {view === "poster" ? (
        <Stage feed={poster} ratio={format.w / format.h} transparent={transparent} label="Preview of your video">
          {motionRequest && <MotionOverlay request={motionRequest} session={motionSession} ready={!poster.pending && !poster.error} posterUrl={poster.response?.url} />}
        </Stage>
      ) : (
        <>
          {sheet && info?.times?.length ? (
            <StoryboardStage count={info.times.length} ratio={format.w / format.h} caption={caption} pending={storyboard.pending}>
                {info.times.map((time, index) => {
                  const columns = info.columns;
                  const rows = Math.ceil(info.frames / columns);
                  const frameSize = Array.isArray(info.frame_size) ? info.frame_size as number[] : null;
                  const frameWidth = frameSize?.[0] ?? sheet.width / columns;
                  const frameHeight = frameSize?.[1] ?? sheet.height / rows;
                  const gapX = (sheet.width - columns * frameWidth) / (columns + 1);
                  const gapY = (sheet.height - rows * frameHeight) / (rows + 1);
                  const x = gapX + (index % columns) * (frameWidth + gapX);
                  const y = gapY + Math.floor(index / columns) * (frameHeight + gapY);
                  return <figure key={index}>
                    <div
                      role="img"
                      aria-label={index === 0 ? "Storyboard: moments from your video" : `Moment at ${formatDuration(time)}`}
                      className="studio-storyboard-frame"
                      style={{
                        aspectRatio: String(frameWidth / frameHeight),
                        backgroundImage: `url("${apiUrl(sheet.url)}")`,
                        backgroundSize: `${sheet.width / frameWidth * 100}% ${sheet.height / frameHeight * 100}%`,
                        backgroundPosition: `${sheet.width > frameWidth ? x / (sheet.width - frameWidth) * 100 : 0}% ${sheet.height > frameHeight ? y / (sheet.height - frameHeight) * 100 : 0}%`,
                      }}
                    />
                    <figcaption>{(videoLength ?? 0) < 60 ? `${Math.round(time * 10) / 10} s` : formatDuration(time)}</figcaption>
                  </figure>;
                })}
            </StoryboardStage>
          ) : <Stage feed={storyboard} ratio={sheetRatio} transparent={transparent} label="Storyboard: moments from your video" />}
        </>
      )}
      {view === "storyboard" && !!sheet && !!info?.times?.length ? (
        !!storyboard.error && <p role="alert" className="text-xs text-danger">{previewProblem(storyboard.error)} <button type="button" onClick={storyboard.retry}>Try again</button></p>
      ) : <p className="studio-preview-caption">{caption}</p>}
    </section>
  );
}
