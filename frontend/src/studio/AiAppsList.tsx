/** Every AI app on this computer, one row each; the manual route stays collapsed below. */
import { useRef, useState } from "react";
import { RotateCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";

import { friendlyError, STUDIO_OFFLINE } from "./api";
import { Spinner } from "./components";
import { ManualSetup } from "./ConnectionDialog";
import { connectAIApp, disconnectAIApp, type AIApp, type SetupStatus } from "./setup";
import "./settings.css";

/** What useSetupStatus returns, so the onboarding page can pass it straight through. */
export interface AiAppsListProps {
  status: SetupStatus | null;
  error: unknown;
  refresh: () => Promise<SetupStatus | null>;
}

function without<T>(record: Record<string, T>, key: string): Record<string, T> {
  const next = { ...record };
  delete next[key];
  return next;
}

/** A plain line for a load that failed; the server's own text can be technical. */
function checkFailure(error: unknown): string {
  return error instanceof ApiError && error.status === 0
    ? STUDIO_OFFLINE
    : "The app couldn't look for AI apps. Try again.";
}

function stateLine(app: AIApp): string {
  if (app.error) return "Its settings file can't be read right now.";
  if (app.needs_repair) return "Connected, but it points to an older copy of Manim Studio.";
  if (app.connected && !app.detected) return "Connected, but the app doesn't seem to be on this computer any more.";
  if (app.connected) return "Manim Studio is in its settings.";
  if (app.detected) return "Found on this computer.";
  return "Not found on this computer.";
}

function EmptyPicture() {
  return <svg viewBox="0 0 48 48" fill="none" aria-hidden>
    <rect x="6" y="9" width="36" height="25" rx="9" stroke="currentColor" strokeWidth="1.6" />
    <path d="M17 34l-4 7 10-7" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
    <circle cx="17" cy="21.5" r="2" fill="currentColor" />
    <circle cx="24" cy="21.5" r="2" fill="currentColor" />
    <circle cx="31" cy="21.5" r="2" fill="currentColor" />
  </svg>;
}

export function AiAppsList({ status, error, refresh }: AiAppsListProps) {
  const [busy, setBusy] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [problems, setProblems] = useState<Record<string, string>>({});
  const [hints, setHints] = useState<Record<string, string>>({});
  const [manual, setManual] = useState(false);
  const manualRef = useRef<HTMLDetailsElement>(null);
  const manualSummary = useRef<HTMLElement>(null);

  const recheck = async () => {
    setRefreshing(true);
    try {
      await refresh();
    } finally {
      setRefreshing(false);
    }
  };
  const act = async (app: AIApp, action: (id: string) => Promise<AIApp>) => {
    setBusy(app.id);
    setProblems((current) => without(current, app.id));
    try {
      const updated = await action(app.id);
      const hint = updated?.restart_hint;
      if (hint) setHints((current) => ({ ...current, [app.id]: hint }));
      else setHints((current) => without(current, app.id));
      await refresh();
    } catch (failure) {
      setProblems((current) => ({ ...current, [app.id]: friendlyError(failure, "Couldn't change that connection. Try again.") }));
    } finally {
      setBusy(null);
    }
  };
  const openManual = () => {
    setManual(true);
    if (manualRef.current) manualRef.current.open = true;
    manualSummary.current?.focus();
    manualRef.current?.scrollIntoView({ block: "nearest" });
  };

  const apps = status?.ai_apps ?? [];
  const here = apps.filter((app) => app.detected || app.connected);
  const elsewhere = apps.filter((app) => !app.detected && !app.connected);

  const actions = (app: AIApp) => {
    if (problems[app.id] || app.error) {
      return <Button size="sm" variant="secondary" disabled={refreshing} onClick={() => { if (app.error) void recheck(); else void act(app, connectAIApp); }}>
        <RotateCw /> Try again
      </Button>;
    }
    if (app.needs_repair) {
      return <>
        <Button size="sm" variant="primary" disabled={busy !== null} onClick={() => void act(app, connectAIApp)}>
          {busy === app.id ? "Fixing…" : "Fix connection"}
        </Button>
        <Button size="sm" variant="ghost" disabled={busy !== null} onClick={() => void act(app, disconnectAIApp)}>Disconnect</Button>
      </>;
    }
    if (app.connected) {
      return <>
        <span className="studio-settings-state-pill">
          <span className="studio-settings-dot" data-tone="ok" aria-hidden />
          Connected
        </span>
        <Button size="sm" variant="ghost" disabled={busy !== null} onClick={() => void act(app, disconnectAIApp)}>
          {busy === app.id ? "Disconnecting…" : "Disconnect"}
        </Button>
      </>;
    }
    return <Button size="sm" variant="primary" disabled={busy !== null} onClick={() => void act(app, connectAIApp)}>
      {busy === app.id ? "Connecting…" : "Connect"}
    </Button>;
  };

  const row = (app: AIApp, quiet: boolean) => (
    <li key={app.id} className={quiet ? "studio-settings-app studio-settings-app-quiet" : "studio-settings-app"} aria-busy={busy === app.id}>
      <div className="studio-settings-app-copy">
        <span className="studio-settings-app-name">{app.label}</span>
        <span className="studio-settings-app-state">{stateLine(app)}</span>
        {hints[app.id] && <span role="status" className="studio-settings-app-hint">{hints[app.id]}</span>}
        {(problems[app.id] || app.error) && <p role="alert" className="studio-settings-app-error">{problems[app.id] ?? app.error}</p>}
      </div>
      {!quiet && <div className="studio-settings-app-actions">{actions(app)}</div>}
    </li>
  );

  return <>
    {!status && !error && <p role="status" className="studio-settings-loading"><Spinner /> Checking your AI apps…</p>}
    {!status && error && <div role="alert" className="studio-settings-load-error">
      <p>{checkFailure(error)}</p>
      <Button size="sm" variant="secondary" disabled={refreshing} onClick={() => void recheck()}><RotateCw /> Try again</Button>
    </div>}
    {status && here.length === 0 && <div className="studio-empty studio-settings-empty">
      <span className="studio-empty-picture"><EmptyPicture /></span>
      <p className="studio-empty-title">No AI apps found</p>
      <p className="studio-empty-line">Install Claude, Cursor or another AI app, then come back.</p>
      <div className="studio-empty-actions">
        <Button variant="primary" size="md" disabled={refreshing} onClick={() => void recheck()}>{refreshing ? <><Spinner /> Checking…</> : "Check again"}</Button>
        <button type="button" className="studio-settings-link" onClick={openManual}>Set it up by hand</button>
      </div>
    </div>}
    {status && here.length > 0 && <ul className="studio-settings-apps">{here.map((app) => row(app, false))}</ul>}
    {status && elsewhere.length > 0 && <section className="studio-settings-quiet-group" aria-labelledby="studio-settings-elsewhere">
      <h3 id="studio-settings-elsewhere">Not on this computer</h3>
      <ul className="studio-settings-apps">{elsewhere.map((app) => row(app, true))}</ul>
    </section>}
    <details
      ref={manualRef}
      className="studio-settings-manual"
      open={manual}
      onToggle={(event) => setManual(event.currentTarget.open)}
    >
      <summary ref={manualSummary}>Manual setup</summary>
      {manual && <div className="studio-settings-manual-body"><ManualSetup /></div>}
    </details>
  </>;
}
