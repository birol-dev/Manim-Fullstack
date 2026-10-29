/** Export dialog (make a file from the video) and the list of recent exports. */
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { ArrowRight, Check, Download, FileImage, FileVideo, Film, FolderDown, Image as ImageIcon, ImagePlay, Layers, RotateCw, XCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";
import { apiUrl } from "@/lib/api";
import { cn } from "@/lib/utils";

import { cancelExport, friendlyError, getExport, previewProblem, startExport, type ExportRequest } from "./api";
import { Spinner } from "./components";
import { fieldErrorsOf, friendlyFieldMessage } from "./errors";
import { useExports } from "./hooks";
import {
  ACTIVE_EXPORT,
  EXPORT_FORMATS,
  exportStatusLabel,
  formatBytes,
  formatLabel,
  formatSeconds,
  friendlyExportMessage,
  qualityLabel,
  QUALITIES,
  timeAgo,
  toDate,
} from "./options";
import type { ExportFormat, ExportJob, ExportQuality, FieldError } from "./types";

const POLL_MS = 700;

function DownloadLink({ job, size = "md", className, secondary = false }: { job: ExportJob; size?: "sm" | "md"; className?: string; secondary?: boolean }) {
  if (!job.url) return null;
  return (
    <Button asChild variant={secondary ? "secondary" : "primary"} size={size} className={className}>
      <a href={apiUrl(job.url)} download={job.filename ?? true}>
        <Download />
        Download
      </a>
    </Button>
  );
}

function Result({ job, posterUrl }: { job: ExportJob; posterUrl?: string }) {
  if (!job.url) return null;
  const url = apiUrl(job.url);
  if (job.format === "mp4" || job.format === "webm") {
    return <video src={url} poster={posterUrl ? apiUrl(posterUrl) : undefined} controls loop playsInline className="max-h-72 w-full rounded-lg bg-black" aria-label="Your exported video" />;
  }
  if (job.format === "gif" || job.format === "png") {
    return <img src={url} alt="Your export" className="studio-checker max-h-72 w-full rounded-lg object-contain" />;
  }
  return <p className="rounded-lg border border-line bg-raised px-3 py-6 text-center text-sm text-fg-muted">MOV files can't play in the browser. Download it to watch.</p>;
}

function exportStage(job: ExportJob): string {
  if (job.status === "queued" || /starting/i.test(job.message ?? "")) return "Starting";
  if (/encod|convert|mux/i.test(job.message ?? "")) return "Encoding";
  if (/rendering the image/i.test(job.message ?? "")) return "Drawing the picture";
  if (/render|animation/i.test(job.message ?? "")) return "Rendering";
  return friendlyExportMessage(job.message).replace(/\d+(?:\.\d+)?%/g, "").trim() || "Rendering";
}

function Choice<T extends string>({
  name,
  value,
  options,
  onChange,
  legend,
}: {
  name: string;
  value: T;
  options: Array<{ value: T; label: string; hint: string }>;
  onChange: (value: T) => void;
  legend: string;
}) {
  const files = name === "export-format";
  const qualityLabels: Record<string, [string, string]> = { draft: ["Draft", "480p"], "720p": ["HD", "720p"], "1080p": ["Full HD", "1080p"], "1080p60": ["Smooth", "1080p · 60 fps"], "4k": ["Ultra HD", "4K"] };
  return (
    <fieldset className="studio-export-choices">
      <legend className="mb-1.5 text-[13px] font-medium text-fg">{legend}</legend>
      <div className={files ? "studio-file-grid" : "studio-quality-segments"}>
      {options.map((option) => (
        <label
          key={option.value}
          className={cn(
            files ? "studio-file-choice" : "studio-quality-choice",
            value === option.value && "studio-export-choice-selected",
          )}
        >
          <input
            type="radio"
            name={name}
            value={option.value}
            checked={value === option.value}
            aria-label={option.label}
            onChange={() => onChange(option.value)}
            className="sr-only"
          />
          {files ? <>
            {option.value === "mp4" ? <Film aria-hidden /> : option.value === "gif" ? <ImagePlay aria-hidden /> : option.value === "png" ? <ImageIcon aria-hidden /> : <Layers aria-hidden />}
            <span className="studio-file-copy"><span className="studio-file-name">{option.label}</span><span className="studio-file-hint">{option.hint}</span></span>
            <span className="studio-file-check" aria-hidden>{value === option.value && <Check />}</span>
          </> : <>
            <span>{qualityLabels[option.value]?.[0] ?? option.label}</span>
            <small>{qualityLabels[option.value]?.[1]}</small>
          </>}
        </label>
      ))}
      </div>
      {!files && <p className="studio-quality-hint">{options.find((option) => option.value === value)?.hint}</p>}
    </fieldset>
  );
}

interface ExportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** What to export, read when the export starts. */
  request: () => Omit<ExportRequest, "format" | "quality">;
  transparentBackground: boolean;
  onFieldErrors: (errors: FieldError[]) => void;
  /** An export started, changed state or finished (refresh lists). */
  onActivity?: () => void;
  posterUrl?: string;
  onStart?: () => void;
  /** This finished result is visible, so it no longer needs a new-export badge. */
  onSeen?: (id: string) => void;
}

export function ExportDialog({ open, onOpenChange, request, transparentBackground, onFieldErrors, onActivity, posterUrl, onStart, onSeen }: ExportDialogProps) {
  const [format, setFormat] = useState<ExportFormat>("mp4");
  const [quality, setQuality] = useState<ExportQuality>("1080p");
  const [job, setJob] = useState<ExportJob | null>(null);
  const [jobPoster, setJobPoster] = useState<string | undefined>(undefined);
  const [starting, setStarting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const cancellingRef = useRef(false);
  const [problem, setProblem] = useState<{ message: string; fields: FieldError[] } | null>(null);
  const [connection, setConnection] = useState(true);
  const openRef = useRef(open);
  const activityRef = useRef(onActivity);
  const seenRef = useRef(onSeen);
  useEffect(() => {
    openRef.current = open;
    activityRef.current = onActivity;
    seenRef.current = onSeen;
  });

  const jobId = job?.id ?? null;
  const jobStatus = job?.status;
  const active = !!job && ACTIVE_EXPORT.has(job.status);
  useEffect(() => {
    if (open && jobId && jobStatus === "done") seenRef.current?.(jobId);
  }, [open, jobId, jobStatus]);
  useEffect(() => {
    if (!jobId || !active || cancelling) return;
    let live = true;
    let failures = 0;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const next = await getExport(jobId);
        if (!live || cancellingRef.current) return;
        failures = 0;
        setConnection(true);
        setJob(next);
        if (!ACTIVE_EXPORT.has(next.status)) {
          activityRef.current?.();
          if (!openRef.current && next.status === "done") {
            toast.success(`${next.title || "Your video"} is ready`, {
              action: next.url ? { label: "Download", onClick: () => window.open(apiUrl(next.url!), "_blank") } : undefined,
            });
          } else if (!openRef.current && next.status === "failed") {
            toast.error("An export didn't work", { description: "Open Exports for details." });
          }
          return;
        }
      } catch {
        if (!live) return;
        failures += 1;
        if (failures >= 3) setConnection(false);
      }
      timer = setTimeout(tick, POLL_MS);
    };
    timer = setTimeout(tick, POLL_MS);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [jobId, active, cancelling]);

  const start = async () => {
    setStarting(true);
    setProblem(null);
    try {
      setJobPoster(posterUrl);
      onStart?.();
      const created = await startExport({ ...request(), format, quality });
      setJob(created);
      onActivity?.();
    } catch (error) {
      const fields = fieldErrorsOf(error);
      if (fields.length) onFieldErrors(fields);
      setProblem({
        message: fields.length ? "Some fields need a fix first. They're marked in red in the form." : previewProblem(error),
        fields,
      });
    } finally {
      setStarting(false);
    }
  };

  const cancel = async () => {
    if (!job || cancellingRef.current) return;
    cancellingRef.current = true;
    setCancelling(true);
    try {
      const next = await cancelExport(job.id);
      setJob(next);
      onActivity?.();
    } catch (error) {
      toast.error(friendlyError(error, "Couldn't cancel the export."));
    } finally {
      cancellingRef.current = false;
      setCancelling(false);
    }
  };

  const chosen = EXPORT_FORMATS.find((item) => item.value === format)!;
  const showChoices = !job;
  // A finished result belongs to the content it was made from: closing the dialog lets the next
  // Export start fresh (the file stays in Exports). A running export is still shown on reopen.
  const changeOpen = (next: boolean) => {
    if (!next && job && !ACTIVE_EXPORT.has(job.status)) {
      setJob(null);
      setProblem(null);
    }
    onOpenChange(next);
  };

  return (
    <Dialog open={open} onOpenChange={changeOpen}>
      <DialogContent className="studio-export-dialog">
        <DialogHeader className="studio-export-header">
          <DialogTitle>
            {!job ? "Export" : active ? `Making your ${job.format === "gif" ? "GIF" : job.format === "png" ? "picture" : "video"}…` : job.status === "done" ? "Your file is ready" : job.status === "cancelled" ? "Export cancelled" : "That didn't work"}
          </DialogTitle>
          <DialogDescription>
            {!job
              ? "Choose what kind of file you need."
              : active
                ? "You can close this. It keeps going in Your exports."
                : job.status === "done"
                  ? [formatLabel(job.format), qualityLabel(job.quality), formatBytes(job.size), job.duration ? formatSeconds(job.duration) : ""]
                      .filter(Boolean)
                      .join(" · ")
                  : job.status === "failed"
                    ? "Something went wrong while making the file."
                    : "Nothing was saved."}
          </DialogDescription>
        </DialogHeader>

        <div className="studio-export-body">
        {showChoices && (
          <div className="studio-export-options">
            <Choice name="export-format" legend="File type" value={format} options={EXPORT_FORMATS} onChange={setFormat} />
            {format === "mp4" && transparentBackground && <p className="text-xs text-warning">A see-through background needs MOV. This export will be a MOV file. Choose Theme under Look for an MP4.</p>}
            {chosen.transparent && !transparentBackground && (
              <p className="-mt-3 text-xs text-fg-subtle">
                Tip: set Background to <span className="font-medium text-fg-muted">None</span> under Look to make the background see-through.
              </p>
            )}
            {format !== "png" && <Choice name="export-quality" legend="Quality" value={quality} options={QUALITIES} onChange={setQuality} />}
            {format === "png" && (
              <Choice name="export-quality" legend="Size" value={quality} options={QUALITIES.filter((item) => item.value !== "1080p60")} onChange={setQuality} />
            )}
          </div>
        )}

        {problem && (
          <div role="alert" className="rounded-lg border border-danger/30 bg-danger-soft px-3 py-2 text-xs text-fg-muted">
            <p>{problem.message}</p>
            {problem.fields.length > 0 && (
              <ul className="mt-1 list-disc pl-4">
                {problem.fields.slice(0, 5).map((field) => (
                  <li key={field.field + field.message}>{friendlyFieldMessage(field.message)}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        {job && (active || job.status === "done") && (
          <div className="studio-export-result">
            <div className="studio-result-well" data-state={active ? "making" : "done"} aria-busy={active}>
              {active ? <>
                {jobPoster ? <img src={apiUrl(jobPoster)} alt="Preview of your export" className="studio-export-pending-poster" /> : <div className="studio-shimmer absolute inset-0" />}
                <span className="studio-export-percentage" role="status">{job.progress != null ? `${Math.round(job.progress)}%` : "Getting ready"}</span>
                {job.progress != null ? <Progress value={job.progress} striped aria-label="Export progress" className="studio-export-well-progress" /> : (
                  <div className="studio-export-well-progress bg-line" role="progressbar" aria-label="Export progress"><div className="absolute inset-y-0 w-1/3 animate-indeterminate bg-accent" /></div>
                )}
              </> : <Result job={job} posterUrl={jobPoster} />}
            </div>
            <div className="studio-export-detail">
              {active ? <>
                <p className="flex items-center gap-2 text-sm text-fg-muted" role="status"><Spinner className="size-3.5" />{exportStage(job)}</p>
                {!connection && <p className="text-xs text-warning">Lost touch with the server. Still trying…</p>}
              </> : <p className="studio-file-meta">{job.filename}</p>}
            </div>
          </div>
        )}
        {job?.status === "failed" && (job.error || job.message) && (
          <details className="rounded-lg border border-danger/30 bg-danger-soft px-3 py-2 text-xs text-fg-muted">
            <summary className="cursor-pointer">Details</summary>
            <p className="mt-1 max-h-40 overflow-y-auto whitespace-pre-wrap break-words font-mono text-2xs">{job.error || job.message}</p>
          </details>
        )}
        </div>

        <DialogFooter className="studio-export-footer">
          {!job && (
            <>
              <Button variant="ghost" size="md" onClick={() => onOpenChange(false)}>
                Close
              </Button>
              <Button variant="primary" size="md" onClick={start} disabled={starting}>
                {starting ? <Spinner /> : <Download />}
                {format === "png" ? "Make picture" : format === "gif" ? "Make GIF" : "Make video"}
              </Button>
            </>
          )}
          {job && active && (
            <Button variant="danger-ghost" size="md" onClick={cancel} disabled={cancelling}>
              {cancelling ? <Spinner /> : <XCircle />}
              {cancelling ? "Cancelling…" : "Cancel export"}
            </Button>
          )}
          {job && !active && (
            <>
              <Button variant="ghost" size="md" onClick={() => setJob(null)}>
                {job.status === "done" ? "Make another" : (
                  <>
                    <RotateCw /> Try again
                  </>
                )}
              </Button>
              {job.status === "done" && <DownloadLink job={job} />}
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function JobIcon({ job }: { job: ExportJob }) {
  const Icon = job.format === "png" || job.format === "gif" ? FileImage : FileVideo;
  return (
    <span
      className={cn(
        "studio-export-icon",
        job.status === "failed" && "text-danger",
      )}
    >
      <Icon aria-hidden className="size-4" />
    </span>
  );
}

export function ExportRow({ job, onCancel }: { job: ExportJob; onCancel?: (job: ExportJob) => void }) {
  const active = ACTIVE_EXPORT.has(job.status);
  return (
    <li className="studio-export-row">
      <JobIcon job={job} />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="studio-export-title truncate text-fg">{job.title || "Untitled video"}</span>
        <span className="studio-export-meta truncate">
          {[formatLabel(job.format), qualityLabel(job.quality), job.status === "done" ? formatBytes(job.size) : exportStatusLabel(job), timeAgo(job.created)]
            .filter(Boolean)
            .join(" · ")}
        </span>
        {active && <Progress value={job.progress ?? 0} striped aria-label={`${job.title || "Export"} progress`} className="h-1" />}
        {job.status === "failed" && (
          <span className="truncate text-xs text-danger" title={job.error || job.message || undefined}>
            Something went wrong while making this file.
          </span>
        )}
      </div>
      {job.status === "done" && <DownloadLink job={job} size="sm" secondary />}
      {active && onCancel && (
        <Button variant="danger-ghost" size="sm" onClick={() => onCancel(job)}>
          Cancel
        </Button>
      )}
    </li>
  );
}

export function ExportsPanel({ open, onOpenChange, refreshKey }: { open: boolean; onOpenChange: (open: boolean) => void; refreshKey?: number }) {
  const { jobs, error, cancel, retry } = useExports(open, refreshKey);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent variant="sheet" className="studio-exports-panel">
        <DialogHeader className="shrink-0">
          <DialogTitle>Exports</DialogTitle>
          <DialogDescription>Files you've made, newest first.</DialogDescription>
        </DialogHeader>
        <div className="studio-exports-scroll">
          {!!error && <div role="alert" className="mb-3 flex flex-col items-start gap-2 text-sm text-danger">
            <p>Couldn't refresh exports. {friendlyError(error)}</p>
            <Button variant="secondary" size="sm" onClick={retry}><RotateCw /> Try again</Button>
          </div>}
          {jobs === null ? (
            <p className="flex items-center gap-2 py-6 text-sm text-fg-muted">
              <Spinner /> Loading…
            </p>
          ) : error && jobs.length === 0 ? null : jobs.length === 0 ? (
            <p className="py-6 text-sm text-fg-muted">Nothing yet. Use Export in a video to make a file.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {jobs.map((job) => (
                <ExportRow key={job.id} job={job} onCancel={cancel} />
              ))}
            </ul>
          )}
        </div>
        <DialogFooter className="shrink-0"><Button variant="ghost" size="md" onClick={() => onOpenChange(false)}>Close</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** The library uses the same rows and cancellation behavior as the editor's sheet. */
export function ExportsPage({ exports: { jobs, error, cancel, retry } }: { exports: ReturnType<typeof useExports> }) {
  return <section className="studio-gallery-section" aria-label="Exported files">
    <p className="studio-results-count">Files you've made, newest first.</p>
    {!!error && <div role="alert" className="studio-inline-error"><span>Couldn't refresh exports. {friendlyError(error)}</span><Button variant="secondary" size="sm" onClick={retry}><RotateCw /> Try again</Button></div>}
    {jobs === null && !error ? <p role="status" className="flex items-center gap-2 py-6 text-sm text-fg-muted"><Spinner /> Loading exports…</p> : jobs?.length ? <ul className="studio-exports-list">{[...jobs].sort((a, b) => (toDate(b.created)?.getTime() ?? 0) - (toDate(a.created)?.getTime() ?? 0)).map((job) => <ExportRow key={job.id} job={job} onCancel={cancel} />)}</ul> : !error && <div className="studio-empty-state">
      <FolderDown aria-hidden /><h2>No exports yet</h2><p>Open a video and use Export to make your first file.</p><Button asChild size="md"><a href="#/videos">Go to your videos <ArrowRight /></a></Button>
    </div>}
  </section>;
}
