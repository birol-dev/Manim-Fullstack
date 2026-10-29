import { useEffect, useRef, useState } from "react";
import { Check, Copy, RotateCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";

import { friendlyError, getConnection, type AIConnection } from "./api";
import { Spinner } from "./components";
import {
  appInfo,
  appSnippet,
  buildSetupPrompt,
  httpConfig,
  readSetupApp,
  rememberSetupApp,
  SETUP_APPS,
  type SetupApp,
} from "./connection";
import "./connection.css";

type CopyState = "idle" | "copied" | "error";

/** One copy button's feedback: "Copied" for two seconds, or an error when the clipboard refuses. */
function useCopyFeedback() {
  const [state, setState] = useState<CopyState>("idle");
  const timer = useRef<number | null>(null);
  useEffect(() => () => {
    if (timer.current !== null) window.clearTimeout(timer.current);
  }, []);
  const copy = async (text: string) => {
    if (timer.current !== null) window.clearTimeout(timer.current);
    try {
      await navigator.clipboard.writeText(text);
      setState("copied");
      timer.current = window.setTimeout(() => setState("idle"), 2000);
    } catch {
      setState("error");
    }
  };
  return { state, copy };
}

/** Mounted only while open: credentials live only for the lifetime of the dialog. */
export function ConnectionDialog({ onClose }: { onClose: () => void }) {
  const [connection, setConnection] = useState<AIConnection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [app, setApp] = useState<SetupApp>(readSetupApp);
  const [showToken, setShowToken] = useState(false);
  const promptCopy = useCopyFeedback();
  const snippetCopy = useCopyFeedback();
  const configCopy = useCopyFeedback();
  useEffect(() => {
    let live = true;
    getConnection().then(
      (result) => live && setConnection(result),
      (error) => live && setError(friendlyError(error, "Couldn't load the connection details.")),
    );
    return () => { live = false; };
  }, [attempt]);

  // An older server may answer {available: false} without any credentials at all.
  const active = connection?.available ? connection : null;
  const stdio = active?.stdio ?? null;
  const snippet = active ? appSnippet(app, active) : "";
  const webConfig = active ? httpConfig(active) : "";
  const shownWebConfig = active ? httpConfig({ ...active, token: showToken ? active.token : `${active.token.slice(0, 4)}•••` }) : "";
  const copyProblem = promptCopy.state === "error" || snippetCopy.state === "error" || configCopy.state === "error";
  const chooseApp = (value: string) => {
    const next = value as SetupApp;
    setApp(next);
    rememberSetupApp(next);
  };

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent className="studio-connection-dialog">
        <DialogHeader>
          <DialogTitle>Connect your AI assistant</DialogTitle>
          <DialogDescription>Let an AI app make and edit videos here for you. Works with AI apps that support MCP connections.</DialogDescription>
        </DialogHeader>
        {!connection && !error && <p role="status" className="flex items-center gap-2 text-sm text-fg-muted"><Spinner /> Loading connection…</p>}
        {error && <div role="alert" className="flex flex-col items-start gap-2 text-sm text-danger">
          <p>{error}</p>
          <Button size="sm" variant="secondary" onClick={() => { setError(null); setAttempt((value) => value + 1); }}><RotateCw /> Try again</Button>
        </div>}
        {connection && !connection.available && <p role="status" className="text-sm text-fg-muted">AI connections aren't available right now. Close this dialog and try again after the app has started.</p>}
        {active && <div className="studio-connection-body">
          <div className="studio-connection-primary">
            <Button variant="primary" size="md" className="w-full" onClick={() => promptCopy.copy(buildSetupPrompt(active))}>
              {promptCopy.state === "copied" ? <Check /> : <Copy />}
              {promptCopy.state === "copied" ? "Copied" : "Copy setup prompt"}
            </Button>
            <p className="text-xs text-fg-muted">Paste it into your AI assistant's chat — it can set the connection up for you.</p>
          </div>
          {stdio ? <>
            <ol className="studio-connection-steps">
              <li>Copy the setup prompt.</li>
              <li>Paste it into your AI assistant and send it.</li>
              <li>{stdio.background ? "Works even when Manim Studio is closed — your AI app starts it in the background." : "Keep Manim Studio open while you use it."}</li>
            </ol>
            <div className="studio-connection-apps">
              <label htmlFor="studio-connection-app">App</label>
              <select id="studio-connection-app" className="studio-connection-select" value={app} onChange={(event) => chooseApp(event.target.value)}>
                {SETUP_APPS.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
              </select>
            </div>
            <div className="studio-code-card">
              <div className="studio-code-header"><span>{appInfo(app).label} settings</span>
                <Button variant="secondary" size="sm" onClick={() => snippetCopy.copy(snippet)}>
                  {snippetCopy.state === "copied" ? <Check /> : <Copy />}
                  {snippetCopy.state === "copied" ? "Copied" : "Copy"}
                </Button>
              </div>
              <pre role="textbox" aria-label={`${appInfo(app).label} configuration`} aria-readonly="true" tabIndex={0} className="studio-connection-code">{snippet}</pre>
            </div>
            <p className="text-xs text-fg-muted">{appInfo(app).where}</p>
            <details className="studio-connection-advanced">
              <summary>Connect by web address</summary>
              <p className="text-xs text-fg-muted">Use this only if your AI app can't start programs. Manim Studio must stay open while you use it.</p>
              <div className="studio-code-card">
                <div className="studio-code-header"><span>Web address</span><div className="flex gap-2">
                  <Button variant="ghost" size="sm" aria-label={showToken ? "Hide token" : "Show token"} aria-pressed={showToken} onClick={() => setShowToken((value) => !value)}>{showToken ? "Hide" : "Show"}</Button>
                  <Button variant="secondary" size="sm" onClick={() => configCopy.copy(webConfig)}>
                    {configCopy.state === "copied" ? <Check /> : <Copy />}
                    {configCopy.state === "copied" ? "Copied" : "Copy configuration"}
                  </Button>
                </div></div>
                <pre role="textbox" aria-label="Web address configuration" aria-readonly="true" tabIndex={0} className="studio-connection-code">{shownWebConfig}</pre>
              </div>
            </details>
          </> : <>
            <ol className="studio-connection-steps">
              <li>Copy the settings.</li>
              <li>Paste them into your AI app's MCP settings.</li>
              <li>Keep Manim Studio open while you use it.</li>
            </ol>
            <div className="studio-code-card">
              <div className="studio-code-header"><span>Settings</span><div className="flex gap-2">
                <Button variant="ghost" size="sm" aria-label={showToken ? "Hide token" : "Show token"} aria-pressed={showToken} onClick={() => setShowToken((value) => !value)}>{showToken ? "Hide" : "Show"}</Button>
                <Button variant="secondary" size="sm" onClick={() => configCopy.copy(webConfig)}>
                  {configCopy.state === "copied" ? <Check /> : <Copy />}
                  {configCopy.state === "copied" ? "Copied" : "Copy configuration"}
                </Button>
              </div></div>
              <pre role="textbox" aria-label="MCP configuration" aria-readonly="true" tabIndex={0} className="studio-connection-code">{shownWebConfig}</pre>
            </div>
          </>}
          {copyProblem && <p role="alert" className="text-xs text-danger">Couldn't copy automatically. Select the text above and copy it.</p>}
        </div>}
      </DialogContent>
    </Dialog>
  );
}
