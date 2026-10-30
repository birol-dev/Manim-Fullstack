/** What this computer needs to make videos, one plain row at a time, plus the data folder. */
import { useState } from "react";
import { RotateCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";

import { friendlyError, STUDIO_OFFLINE } from "./api";
import { Spinner } from "./components";
import { installComponent, revealDataFolder, type SetupComponent, type SetupStatus } from "./setup";
import "./settings.css";

/** What useSetupStatus returns, so the onboarding page can pass it straight through. */
export interface SystemListProps {
  status: SetupStatus | null;
  error: unknown;
  refresh: () => Promise<SetupStatus | null>;
}

function without<T>(record: Record<string, T>, key: string): Record<string, T> {
  const next = { ...record };
  delete next[key];
  return next;
}

function checkFailure(error: unknown): string {
  return error instanceof ApiError && error.status === 0
    ? STUDIO_OFFLINE
    : "The app couldn't check this computer. Try again.";
}

function stateText(component: SetupComponent): string {
  if (component.status === "ready") return "Ready";
  if (component.status === "installing") {
    return component.progress == null ? "Installing…" : `Installing… ${Math.round(component.progress)}%`;
  }
  return component.detail ?? (component.status === "failed" ? "It didn't install." : "Not installed.");
}

function tone(component: SetupComponent): "ok" | "bad" | "busy" | "wait" {
  if (component.status === "ready") return "ok";
  if (component.status === "failed") return "bad";
  if (component.status === "installing") return "busy";
  return "wait";
}

export function SystemList({ status, error, refresh }: SystemListProps) {
  const [busy, setBusy] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [problems, setProblems] = useState<Record<string, string>>({});
  const [revealing, setRevealing] = useState(false);
  const [revealProblem, setRevealProblem] = useState<string | null>(null);

  const recheck = async () => {
    setRefreshing(true);
    try {
      await refresh();
    } finally {
      setRefreshing(false);
    }
  };
  const install = async (component: SetupComponent) => {
    setBusy(component.id);
    setProblems((current) => without(current, component.id));
    try {
      await installComponent(component.id);
      await refresh();
    } catch (failure) {
      setProblems((current) => ({ ...current, [component.id]: friendlyError(failure, "Couldn't install that. Try again.") }));
    } finally {
      setBusy(null);
    }
  };
  const reveal = async () => {
    setRevealing(true);
    setRevealProblem(null);
    try {
      await revealDataFolder();
    } catch (failure) {
      setRevealProblem(friendlyError(failure, "Couldn't open the folder. Try again."));
    } finally {
      setRevealing(false);
    }
  };

  const components = status?.components ?? [];
  const requiredReady = components.filter((component) => component.required).every((component) => component.status === "ready");

  const action = (component: SetupComponent) => {
    if (!component.can_install || component.status === "installing") return null;
    const label = component.status === "failed" ? "Try again" : "Install";
    return <Button size="sm" variant="secondary" disabled={busy !== null} onClick={() => void install(component)}>
      {busy === component.id ? <><Spinner /> Starting…</> : label}
    </Button>;
  };

  return <>
    {!status && !error && <p role="status" className="studio-settings-loading"><Spinner /> Checking this computer…</p>}
    {!status && error && <div role="alert" className="studio-settings-load-error">
      <p>{checkFailure(error)}</p>
      <Button size="sm" variant="secondary" disabled={refreshing} onClick={() => void recheck()}><RotateCw /> Try again</Button>
    </div>}
    {status && <>
      <p className="studio-settings-system-summary">
        <span className="studio-settings-dot" data-tone={requiredReady ? "ok" : "bad"} aria-hidden />
        {requiredReady ? "Everything you need is ready." : "Something you need isn't ready yet."}
      </p>
      <ul className="studio-settings-system">
        {components.map((component) => <li key={component.id} className="studio-settings-system-row" aria-busy={component.status === "installing" || busy === component.id}>
          <span className="studio-settings-dot studio-settings-system-dot" data-tone={tone(component)} aria-hidden />
          <div className="studio-settings-system-copy">
            <span className="studio-settings-system-name">
              {component.label}
              {component.required && <span className="studio-settings-needed">Needed</span>}
            </span>
            <span className="studio-settings-system-purpose">{component.purpose}</span>
            <span className="studio-settings-system-state">{stateText(component)}</span>
            {component.status === "installing" && <div
              className="studio-settings-progress"
              data-unknown={component.progress == null ? "true" : undefined}
              role="progressbar"
              aria-label={`Installing ${component.label}`}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={component.progress ?? undefined}
            >
              <span style={component.progress == null ? undefined : { width: `${component.progress}%` }} />
            </div>}
            {problems[component.id] && <p role="alert" className="studio-settings-app-error">{problems[component.id]}</p>}
          </div>
          <div className="studio-settings-system-actions">{action(component)}</div>
        </li>)}
      </ul>
      <div className="studio-settings-folder">
        <div className="studio-settings-folder-copy">
          <h3>Your files</h3>
          <p className="studio-settings-folder-path">{status.data_folder}</p>
        </div>
        <Button variant="secondary" size="md" disabled={revealing} onClick={() => void reveal()}>
          {revealing ? "Opening…" : "Show folder"}
        </Button>
      </div>
      {revealProblem && <div role="alert" className="studio-settings-load-error">
        <p>{revealProblem}</p>
        <Button size="sm" variant="secondary" disabled={revealing} onClick={() => void reveal()}><RotateCw /> Try again</Button>
      </div>}
    </>}
  </>;
}
