/**
 * "Your video is ready", wherever the person is in the app.
 *
 * One listener watches the export list and announces each export once when it finishes
 * (the export dialog announces through the same helper, so nothing is said twice). A list
 * made with Make many is announced once, when its last row finishes. While the window is
 * in the background, the title says how many videos are ready until it comes back.
 */
import { useEffect, useRef } from "react";
import { toast } from "sonner";

import { apiUrl } from "@/lib/api";

import { useExports } from "./hooks";
import { ACTIVE_EXPORT } from "./options";
import type { ExportJob } from "./types";

const announced = new Set<string>();
/** Exports an open export dialog is following: it announces those itself. */
const watched = new Set<string>();
let unseenTitleCount = 0;
let baseTitle: string | null = null;

function backgrounded(): boolean {
  return typeof document !== "undefined" && (document.hidden || !document.hasFocus());
}

function badgeTitle(count: number) {
  if (typeof document === "undefined" || count <= 0) return;
  if (baseTitle === null) baseTitle = document.title;
  unseenTitleCount += count;
  document.title = `(${unseenTitleCount}) ${unseenTitleCount === 1 ? "Video ready" : "Videos ready"} · ${baseTitle}`;
}

function clearBadge() {
  if (baseTitle === null || typeof document === "undefined") return;
  document.title = baseTitle;
  baseTitle = null;
  unseenTitleCount = 0;
}

/** An export dialog follows this export and will announce it (or show it) itself. */
export function watchExport(id: string): () => void {
  watched.add(id);
  return () => { watched.delete(id); };
}

/** The person saw this result already (an open dialog showed it): don't announce it. */
export function markAnnounced(id: string) {
  announced.add(id);
}

/** Announce one finished export, once (also used by the export dialog). */
export function announceExport(job: ExportJob) {
  if (announced.has(job.id) || ACTIVE_EXPORT.has(job.status)) return;
  announced.add(job.id);
  if (job.status === "done") {
    toast.success(`${job.title || "Your video"} is ready`, {
      action: job.url ? { label: "Download", onClick: () => window.open(apiUrl(job.url!), "_blank") } : undefined,
    });
    if (backgrounded()) badgeTitle(1);
  } else if (job.status === "failed") {
    toast.error("An export didn't work", { description: "Open Exports for details." });
  }
}

function announceList(rows: ExportJob[]) {
  const fresh = rows.filter((job) => !announced.has(job.id));
  if (!fresh.length) return;
  for (const job of rows) announced.add(job.id);
  const done = rows.filter((job) => job.status === "done").length;
  const failed = rows.filter((job) => job.status === "failed").length;
  const name = rows[0]?.batch_title || "Your list";
  if (failed) {
    toast.error(`${name} is finished`, {
      description: `${done} ready, ${failed} didn't work. Open Exports to try those again.`,
    });
  } else if (done) {
    toast.success(`${name} is ready`, { description: `${done} video${done === 1 ? "" : "s"} made.` });
  }
  if (done && backgrounded()) badgeTitle(done);
}

/** Forget what was announced (tests). */
export function resetExportNoticesForTests() {
  announced.clear();
  watched.clear();
  clearBadge();
}

/** Mounted once for the whole studio. Renders nothing. */
export function ExportNotices() {
  const { jobs } = useExports(true);
  const previous = useRef<Map<string, string> | null>(null);

  useEffect(() => {
    const reset = () => { if (!backgrounded()) clearBadge(); };
    window.addEventListener("focus", reset);
    document.addEventListener("visibilitychange", reset);
    return () => {
      window.removeEventListener("focus", reset);
      document.removeEventListener("visibilitychange", reset);
    };
  }, []);

  useEffect(() => {
    if (!Array.isArray(jobs)) return;
    const before = previous.current;
    previous.current = new Map(jobs.map((job) => [job.id, job.status]));
    if (before === null) return; // the first listing is the baseline: old exports aren't news
    const finishedNow = jobs.filter((job) => !ACTIVE_EXPORT.has(job.status)
      && (before.get(job.id) === undefined || ACTIVE_EXPORT.has(before.get(job.id)!)));
    const lists = new Set<string>();
    for (const job of finishedNow) {
      if (job.batch_id) lists.add(job.batch_id);
      else if (job.status !== "cancelled" && !watched.has(job.id)) announceExport(job);
    }
    for (const batchId of lists) {
      const rows = jobs.filter((job) => job.batch_id === batchId);
      if (rows.some((job) => ACTIVE_EXPORT.has(job.status))) continue; // wait for the last row
      announceList(rows.filter((job) => job.status !== "cancelled"));
    }
  }, [jobs]);

  return null;
}
