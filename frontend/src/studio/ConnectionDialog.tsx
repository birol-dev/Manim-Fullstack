import { useEffect, useState } from "react";
import { Check, Copy, RotateCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";

import { friendlyError, getConnection, type AIConnection } from "./api";
import { Spinner } from "./components";

/** Mounted only while open: credentials live only for the lifetime of the dialog. */
export function ConnectionDialog({ onClose }: { onClose: () => void }) {
  const [connection, setConnection] = useState<AIConnection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  const [showToken, setShowToken] = useState(false);
  useEffect(() => {
    let live = true;
    getConnection().then(
      (result) => live && setConnection(result),
      (error) => live && setError(friendlyError(error, "Couldn't load the connection details.")),
    );
    return () => { live = false; };
  }, [attempt]);

  const configurationFor = (token: string) => JSON.stringify({ mcpServers: { "manim-studio": { url: connection?.url, headers: { Authorization: `Bearer ${token}` } } } }, null, 2);
  const configuration = connection?.available ? configurationFor(connection.token) : null;
  const displayed = connection?.available ? configurationFor(showToken ? connection.token : `${connection.token.slice(0, 4)}•••`) : null;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(configuration!);
      setCopied(true);
      setCopyError(false);
    } catch {
      setCopyError(true);
    }
  };

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent className="max-w-xl">
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
        {configuration && <>
          <ol className="studio-connection-steps">
            <li>Copy the settings.</li>
            <li>Paste them into your AI app's MCP settings.</li>
            <li>Keep Manim Studio open while you use it.</li>
          </ol>
          <div className="studio-code-card">
            <div className="studio-code-header"><span>Settings</span><div className="flex gap-2">
              <Button variant="ghost" size="sm" aria-label={showToken ? "Hide token" : "Show token"} aria-pressed={showToken} onClick={() => setShowToken((value) => !value)}>{showToken ? "Hide" : "Show"}</Button>
              <Button variant="secondary" size="sm" onClick={copy}>{copied ? <Check /> : <Copy />}{copied ? "Copied" : "Copy configuration"}</Button>
            </div></div>
            <pre role="textbox" aria-label="MCP configuration" aria-readonly="true" tabIndex={0} className="studio-connection-code">{displayed}</pre>
          </div>
          {copyError && <p role="alert" className="text-xs text-danger">Couldn't copy automatically. Choose Show, then select the settings above and copy them.</p>}
        </>}
      </DialogContent>
    </Dialog>
  );
}
