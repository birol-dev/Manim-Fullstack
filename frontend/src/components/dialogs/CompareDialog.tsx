import { useRef, useState } from "react";
import { Pause, Play, RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiUrl } from "@/lib/api";
import type { MediaFile } from "@/lib/types";

interface CompareDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  videos: MediaFile[];
}

const DRIFT_TOLERANCE_S = 0.08;

function label(video: MediaFile) {
  return [video.scene, video.quality, video.script && `${video.script}.py`].filter(Boolean).join(" · ");
}

function formatTime(seconds: number) {
  return `${seconds.toFixed(1)}s`;
}

interface ComparePaneProps {
  side: "A" | "B";
  path: string;
  videos: MediaFile[];
  videoRef: React.RefObject<HTMLVideoElement | null>;
  onChange: (path: string) => void;
  onLoadedMetadata: () => void;
  onTimeUpdate?: () => void;
  onEnded?: () => void;
}

function ComparePane({ side, path, videos, videoRef, onChange, onLoadedMetadata, onTimeUpdate, onEnded }: ComparePaneProps) {
  const video = videos.find((item) => item.path === path);
  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-2">
      <Select value={path} onValueChange={onChange}>
        <SelectTrigger aria-label={`Video ${side}`} className="h-8">
          <span className="flex min-w-0 items-center gap-2">
            <span className="font-semibold text-accent">{side}</span>
            <span className="truncate">
              <SelectValue />
            </span>
          </span>
        </SelectTrigger>
        <SelectContent>
          {videos.map((item) => (
            <SelectItem key={item.path} value={item.path}>
              {label(item)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <div className="flex min-h-0 flex-1 items-center justify-center overflow-hidden rounded-lg border border-line bg-black">
        {video && (
          <video
            ref={videoRef}
            key={video.path}
            src={apiUrl(video.url)}
            muted
            playsInline
            preload="auto"
            onLoadedMetadata={onLoadedMetadata}
            onTimeUpdate={onTimeUpdate}
            onEnded={onEnded}
            className="max-h-full max-w-full"
          />
        )}
      </div>
    </div>
  );
}

function CompareBody({ videos }: { videos: MediaFile[] }) {
  const [pathA, setPathA] = useState(videos[0]?.path ?? "");
  const [pathB, setPathB] = useState(videos[1]?.path ?? videos[0]?.path ?? "");
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const videoA = useRef<HTMLVideoElement>(null);
  const videoB = useRef<HTMLVideoElement>(null);

  const both = () => [videoA.current, videoB.current].filter((video): video is HTMLVideoElement => video !== null);

  const pause = () => {
    both().forEach((video) => video.pause());
    setPlaying(false);
  };

  const togglePlay = () => {
    if (playing) return pause();
    if (duration && time >= duration - 0.05) seek(0);
    both().forEach((video) => void video.play().catch(() => {}));
    setPlaying(true);
  };

  const seek = (value: number) => {
    setTime(value);
    both().forEach((video) => {
      video.currentTime = Math.min(value, Number.isFinite(video.duration) ? video.duration : value);
    });
  };

  const finished = (video: HTMLVideoElement | null) =>
    !video || video.ended || (Number.isFinite(video.duration) && video.currentTime >= video.duration - 0.05);

  // Runs on either clip's timeupdate. The readout follows whichever clip is further
  // along, so it keeps counting when the shorter clip (A or B) has ended.
  const sync = () => {
    const a = videoA.current;
    const b = videoB.current;
    const playing = both();
    if (playing.length === 0) return;
    setTime(Math.max(...playing.map((video) => video.currentTime)));
    // Once the shorter clip ends, leave it on its last frame and let the longer one continue.
    if (!a || !b || a.ended || b.ended || !Number.isFinite(b.duration) || a.currentTime > b.duration) return;
    if (Math.abs(b.currentTime - a.currentTime) > DRIFT_TOLERANCE_S) b.currentTime = a.currentTime;
  };

  const noteEnded = () => {
    if (finished(videoA.current) && finished(videoB.current)) setPlaying(false);
  };

  const updateDuration = () => {
    const durations = both().map((video) => (Number.isFinite(video.duration) ? video.duration : 0));
    setDuration(Math.max(0, ...durations));
  };

  const chooseA = (path: string) => {
    pause();
    setTime(0);
    setPathA(path);
  };

  const chooseB = (path: string) => {
    pause();
    setTime(0);
    setPathB(path);
  };

  return (
    <>
      <div className="flex min-h-0 flex-1 gap-3">
        <ComparePane
          side="A"
          path={pathA}
          videos={videos}
          videoRef={videoA}
          onChange={chooseA}
          onLoadedMetadata={updateDuration}
          onTimeUpdate={sync}
          onEnded={noteEnded}
        />
        <ComparePane
          side="B"
          path={pathB}
          videos={videos}
          videoRef={videoB}
          onChange={chooseB}
          onLoadedMetadata={updateDuration}
          onTimeUpdate={sync}
          onEnded={noteEnded}
        />
      </div>
      <div className="flex shrink-0 items-center gap-3">
        <Button variant="primary" size="icon" aria-label={playing ? "Pause" : "Play both"} onClick={togglePlay}>
          {playing ? <Pause className="fill-current" /> : <Play className="fill-current" />}
        </Button>
        <Button variant="ghost" size="icon" aria-label="Back to start" onClick={() => seek(0)}>
          <RotateCcw />
        </Button>
        <input
          type="range"
          aria-label="Playback position"
          min={0}
          max={duration || 0}
          step={0.01}
          value={Math.min(time, duration || 0)}
          onChange={(event) => seek(Number(event.target.value))}
          className="h-1 flex-1 cursor-pointer accent-[var(--color-accent)]"
        />
        <span className="w-24 text-right font-mono text-2xs tabular-nums text-fg-muted">
          {formatTime(time)} / {formatTime(duration)}
        </span>
      </div>
    </>
  );
}

export function CompareDialog({ open, onOpenChange, videos }: CompareDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="h-[min(760px,calc(100dvh-2rem))] max-w-6xl">
        <DialogHeader>
          <DialogTitle>Compare renders</DialogTitle>
          <DialogDescription>Two renders, played in lockstep. Pick any pair from your workspace.</DialogDescription>
        </DialogHeader>
        {open && <CompareBody videos={videos} />}
      </DialogContent>
    </Dialog>
  );
}
