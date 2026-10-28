/** Export dialog (make a file from the video) and the list of recent exports. */
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, Download, FileImage, FileVideo, RotateCw, XCircle } from "lucide-react";

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
} from "./options";
import type { ExportFormat, ExportJob, ExportQuality, FieldError } from "./types";

const POLL_MS = 700;

function DownloadLink({ job, size = "md", className }: { job: ExportJob; size?: "sm" | "md"; className?: string }) {
  if (!job.url) return null;
  return (
    <Button asChild variant="primary" size={size} className={className}>
      <a href={apiUrl(job.url)} download={job.filename ?? true}>
        <Download />
        Download
      </a>
    </Button>
  );
}

function Result({ job }: { job: ExportJob }) {
  if (!job.url) return null;
  const url = apiUrl(job.url);
  if (job.format === "mp4" || job.format === "webm") {
    return <video src={url} controls loop playsInline className="max-h-72 w-full rounded-lg bg-black" aria-label="Your exported video" />;
  }
  if (job.format === "gif" || job.format === "png") {
    return <img src={url} alt="Your export" className="studio-checker max-h-72 w-full rounded-lg object-contain" />;
  }
  return <p className="rounded-lg border border-line bg-raised px-3 py-6 text-center text-sm text-fg-muted">MOV files can't play in the browser. Download it to watch.</p>;
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
  return (
    <fieldset className="flex flex-col gap-1.5">
      <legend className="mb-1.5 text-[13px] font-medium text-fg">{legend}</legend>
      {options.map((option) => (
        <label
          key={option.value}
          className={cn(
            "flex cursor-pointer items-start gap-2.5 rounded-lg border px-3 py-2 transition-colors focus-within:ring-2 focus-within:ring-accent/40",
            value === option.value ? "border-accent bg-accent-soft" : "border-line-strong hover:border-[#3d3d47]",
          )}
        >
          <input
            type="radio"
            name={name}
            value={option.value}
            checked={value === option.value}
            onChange={() => onChange(option.value)}
            className="mt-0.5 size-4 accent-[var(--color-accent)]"
          />
          <span className="flex min-w-0 flex-col">
            <span className="text-[13px] font-medium text-fg">{option.label}</span>
            <span className="text-xs leading-relaxed text-fg-subtle">{option.hint}</span>
          </span>
        </label>
      ))}
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
}

export function ExportDialog({ open, onOpenChange, request, transparentBackground, onFieldErrors, onActivity }: ExportDialogProps) {
  const [format, setFormat] = useState<ExportFormat>("mp4");
  const [quality, setQuality] = useState<ExportQuality>("1080p");
  const [job, setJob] = useState<ExportJob | null>(null);
  const [starting, setStarting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const cancellingRef = useRef(false);
  const [problem, setProblem] = useState<{ message: string; fields: FieldError[] } | null>(null);
  const [connection, setConnection] = useState(true);
  const openRef = useRef(open);
  const activityRef = useRef(onActivity);
  useEffect(() => {
    openRef.current = open;
    activityRef.current = onActivity;
  });

  const jobId = job?.id ?? null;
  const active = !!job && ACTIVE_EXPORT.has(job.status);
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

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {!job ? "Export" : active ? "Making your file…" : job.status === "done" ? "Your file is ready" : job.status === "cancelled" ? "Export cancelled" : "That didn't work"}
          </DialogTitle>
          <DialogDescription>
            {!job
              ? "Choose what kind of file you need."
              : active
                ? "You can close this window. The export keeps going and shows up in Exports."
                : job.status === "done"
                  ? [formatLabel(job.format), qualityLabel(job.quality), formatBytes(job.size), job.duration ? formatSeconds(job.duration) : ""]
                      .filter(Boolean)
                      .join(" · ")
                  : job.status === "failed"
                    ? "Something went wrong while making the file."
                    : "Nothing was saved."}
          </DialogDescription>
        </DialogHeader>

        {showChoices && (
          <div className="-mx-1 flex max-h-[60vh] flex-col gap-5 overflow-y-auto px-1">
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

        {job && active && (
          <div className="flex flex-col gap-2" aria-live="polite">
            {job.progress != null ? (
              <Progress value={job.progress} striped aria-label="Export progress" />
            ) : (
              <div className="relative h-1.5 overflow-hidden rounded-full bg-line" role="progressbar" aria-label="Export progress">
                <div className="absolute inset-y-0 w-1/3 animate-indeterminate rounded-full bg-accent" />
              </div>
            )}
            <p className="flex items-center gap-2 text-sm text-fg-muted">
              <Spinner className="size-3.5" />
              {exportStatusLabel(job)}
              {friendlyExportMessage(job.message) ? (
                <span className="truncate text-xs text-fg-subtle">· {friendlyExportMessage(job.message)}</span>
              ) : null}
            </p>
            {!connection && <p className="text-xs text-warning">Lost touch with the server. Still trying…</p>}
          </div>
        )}

        {job?.status === "done" && <Result job={job} />}
        {job?.status === "failed" && (job.error || job.message) && (
          <details className="rounded-lg border border-danger/30 bg-danger-soft px-3 py-2 text-xs text-fg-muted">
            <summary className="cursor-pointer">Details</summary>
            <p className="mt-1 max-h-40 overflow-y-auto whitespace-pre-wrap break-words font-mono text-2xs">{job.error || job.message}</p>
          </details>
        )}

        <DialogFooter>
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
        "flex size-9 shrink-0 items-center justify-center rounded-lg",
        job.status === "done" ? "bg-accent-soft text-accent" : job.status === "failed" ? "bg-danger-soft text-danger" : "bg-raised text-fg-muted",
      )}
    >
      {job.status === "done" ? <CheckCircle2 className="size-4" /> : <Icon className="size-4" />}
    </span>
  );
}

export function ExportRow({ job, onCancel }: { job: ExportJob; onCancel?: (job: ExportJob) => void }) {
  const active = ACTIVE_EXPORT.has(job.status);
  return (
    <li className="flex items-center gap-3 rounded-lg border border-line px-3 py-2">
      <JobIcon job={job} />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="truncate text-[13px] font-medium text-fg">{job.title || "Untitled video"}</span>
        <span className="truncate text-xs text-fg-subtle">
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
      {job.status === "done" && <DownloadLink job={job} size="sm" />}
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
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Exports</DialogTitle>
          <DialogDescription>Files you've made, newest first.</DialogDescription>
        </DialogHeader>
        <div className="-mx-1 max-h-[60vh] overflow-y-auto px-1">
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
      </DialogContent>
    </Dialog>
  );
}
