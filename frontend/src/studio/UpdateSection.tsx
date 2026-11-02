/** About → updates: the version, one plain button, and nothing installs by itself. */
import { useEffect, useState } from "react";

import { Progress } from "@/components/ui/progress";
import { requestJson } from "@/lib/api";

import { friendlyError } from "./api";
import { checkForUpdate, downloadUpdate, getSetupStatus, installUpdate, useUpdateStatus, type UpdateStatus } from "./setup";

const SOURCE_DETAIL = "You're running from source. Use git pull to update.";

/** The app's version: the setup status knows it; an older server still answers /api/health. */
function useAppVersion() {
  const [version, setVersion] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    getSetupStatus().then(
      (status) => {
        if (!live) return;
        if (typeof status.version === "string" && status.version) setVersion(status.version);
        else requestJson<{ version?: unknown }>("/api/health").then((data) => {
          if (live && data && typeof data.version === "string") setVersion(data.version);
        }, () => {});
      },
      () => requestJson<{ version?: unknown }>("/api/health").then((data) => {
        if (live && data && typeof data.version === "string") setVersion(data.version);
      }, () => {}),
    );
    return () => { live = false; };
  }, []);
  return version;
}

export function UpdateSection() {
  const version = useAppVersion();
  const { status, error, setStatus } = useUpdateStatus();
  const [auto, setAuto] = useState(true);
  const [working, setWorking] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    requestJson<{ update_check?: unknown }>("/api/studio/preferences", { cache: "no-store" }).then(
      (stored) => { if (live && stored) setAuto(stored.update_check !== false); },
      () => { /* The switch keeps its default until the server answers. */ },
    );
    return () => { live = false; };
  }, []);

  const changeAuto = async (value: boolean) => {
    setAuto(value);
    setProblem(null);
    try {
      await requestJson("/api/studio/preferences", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ update_check: value }),
      });
    } catch (failure) {
      setAuto(!value);
      setProblem(friendlyError(failure, "That choice couldn't be saved. Try again."));
    }
  };

  const run = async (action: () => Promise<UpdateStatus>) => {
    setWorking(true);
    setProblem(null);
    try {
      const next = await action();
      if (next) setStatus(next);
    } catch (failure) {
      setProblem(friendlyError(failure, "That didn't work. Try again."));
    } finally {
      setWorking(false);
    }
  };

  const state = status?.state ?? "idle";
  const busy = working || state === "checking" || state === "downloading";
  const label = state === "ready"
    ? "Restart and update"
    : state === "available"
      ? "Download update"
      : state === "checking"
        ? "Checking…"
        : state === "downloading"
          ? "Downloading…"
          : state === "failed"
            ? "Try again"
            : "Check for updates";
  const action = state === "ready" ? installUpdate : state === "available" ? downloadUpdate : checkForUpdate;
  const shownProblem = problem ?? (state === "failed" ? status?.message || status?.detail : null);
  const quiet = status?.detail && state !== "failed" && !problem ? status.detail : null;
  const sourceMode = state === "unavailable" && status?.detail === SOURCE_DETAIL;

  return <div className="mt-8 flex flex-col gap-4">
    {version && <p className="text-[13px] text-fg-subtle">Version <span>{version}</span></p>}

    {state === "available" && status?.version && <div className="flex flex-col gap-1.5">
      <p className="text-sm font-medium text-fg">Version {status.version} is available</p>
      {status.notes && <p className="whitespace-pre-line text-xs leading-relaxed text-fg-muted">{status.notes}</p>}
    </div>}

    {state === "downloading" && <div className="flex max-w-sm flex-col gap-2">
      <p className="text-sm text-fg">Downloading version {status?.version ?? "the update"}…</p>
      <Progress value={status?.progress ?? 0} aria-label="Update download progress" className="h-1.5" />
      <p className="text-xs text-fg-subtle">{status?.progress != null ? `${Math.round(status.progress)}%` : "Getting ready…"}</p>
    </div>}

    {state === "ready" && <p className="text-sm text-fg">Version {status?.version ?? "the update"} is ready to install.</p>}

    {status && !sourceMode && <button
      type="button"
      className="inline-flex h-9 w-fit items-center rounded-full bg-[var(--color-ink)] px-4 text-[13px] font-medium text-[var(--color-ink-fg)] transition-colors hover:bg-[var(--color-ink-hover)] disabled:cursor-default disabled:opacity-50"
      onClick={() => { void run(action); }}
      disabled={busy || !status}
    >{label}</button>}

    {shownProblem && <p role="alert" className="max-w-prose text-[13px] leading-relaxed text-danger">{shownProblem}</p>}
    {quiet && <p className="max-w-prose text-xs leading-relaxed text-fg-subtle">{quiet}</p>}
    {!status && error !== null && <p className="text-xs text-fg-subtle">Couldn't check for updates. Try again later.</p>}

    <label className="flex w-fit items-center gap-2 text-[13px] text-fg-muted">
      <input
        type="checkbox"
        className="size-4 accent-[var(--color-ink)]"
        checked={auto}
        onChange={(event) => { void changeAuto(event.target.checked); }}
      />
      Check for updates automatically
    </label>
  </div>;
}
