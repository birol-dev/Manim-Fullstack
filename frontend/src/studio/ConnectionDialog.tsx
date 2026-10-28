import { useEffect, useState } from "react";
import { Check, Copy, RotateCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";

import { friendlyError, getConnection, type AIConnection } from "./api";
import { inputClass, Spinner } from "./components";

/** Mounted only while open: credentials live only for the lifetime of the dialog. */
export function ConnectionDialog({ onClose }: { onClose: () => void }) {
  const [connection, setConnection] = useState<AIConnection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  useEffect(() => {
    let live = true;
    getConnection().then(
      (result) => live && setConnection(result),
      (error) => live && setError(friendlyError(error, "Couldn't load the connection details.")),
    );
    return () => { live = false; };
  }, [attempt]);

  const configuration = connection?.available ? JSON.stringify({
    mcpServers: { composer: { url: connection.url, headers: { Authorization: `Bearer ${connection.token}` } } },
  }, null, 2) : null;

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
          <DialogTitle>Connect to AI</DialogTitle>
          <DialogDescription>Add this local HTTP MCP connection to your AI app's configuration.</DialogDescription>
        </DialogHeader>
        {!connection && !error && <p role="status" className="flex items-center gap-2 text-sm text-fg-muted"><Spinner /> Loading connection…</p>}
        {error && <div role="alert" className="flex flex-col items-start gap-2 text-sm text-danger">
          <p>{error}</p>
          <Button size="sm" variant="secondary" onClick={() => { setError(null); setAttempt((value) => value + 1); }}><RotateCw /> Try again</Button>
        </div>}
        {connection && !connection.available && <p role="status" className="text-sm text-fg-muted">AI connections aren't available right now. Close this dialog and try again after the app has started.</p>}
        {configuration && <>
          <textarea readOnly aria-label="MCP configuration" value={configuration} rows={13} className={`${inputClass} resize-none py-3 font-mono text-xs`} />
          <Button variant="primary" size="md" onClick={copy}>{copied ? <Check /> : <Copy />}{copied ? "Copied" : "Copy configuration"}</Button>
          {copyError && <p role="alert" className="text-xs text-danger">Couldn't copy automatically. Select the configuration above and copy it.</p>}
          <p className="text-xs leading-relaxed text-fg-muted">Your AI can find templates, create and edit projects, preview them, and manage exports. Use Reload saved in an open project to see its changes.</p>
        </>}
        <p className="text-xs leading-relaxed text-fg-subtle">Keep this app open while using the connection. The connection is local to this computer.</p>
      </DialogContent>
    </Dialog>
  );
}
