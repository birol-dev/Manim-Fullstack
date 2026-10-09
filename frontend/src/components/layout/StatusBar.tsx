import { AlertTriangle, CheckCircle2, CircleSlash, Globe, HardDrive, Loader2, XCircle } from "lucide-react";

import { Tooltip } from "@/components/ui/tooltip";
import type { BackendStatus } from "@/hooks/useDiagnostics";
import type { ActiveRender, ConnectionState, RenderOutcome } from "@/hooks/useRenderSession";
import { formatDuration } from "@/lib/format";
import type { Diagnostics, StorageMode } from "@/lib/types";
import { cn } from "@/lib/utils";

interface StatusBarProps {
  backend: BackendStatus;
  connection: ConnectionState;
  active: ActiveRender | null;
  /** Overall progress of the active render (0–100), if known. */
  renderPercent: number | null;
  lastOutcome: RenderOutcome | null;
  storageMode: StorageMode;
  cursor: { line: number; column: number } | null;
  diagnostics: Diagnostics | null;
  onOpenSetup: () => void;
  onShowConsole: () => void;
}

const PROFILE_LABELS: Record<string, string> = { eco: "Eco", balanced: "Balanced", workstation: "Workstation" };

function Item({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex h-full items-center gap-1.5 px-2 [&_svg]:size-3", className)} {...props} />;
}

function ConnectionIndicator({ backend, connection }: Pick<StatusBarProps, "backend" | "connection">) {
  let tone = "bg-success";
  let label = "Connected";
  if (backend === "offline") {
    tone = "bg-danger";
    label = "Server offline — retrying";
  } else if (backend === "loading" || connection === "connecting") {
    tone = "bg-warning animate-pulse";
    label = "Connecting…";
  } else if (connection === "closed") {
    tone = "bg-warning";
    label = "Reconnecting…";
  }
  return (
    <Item>
      <span className={cn("size-1.5 rounded-full", tone)} />
      {label}
    </Item>
  );
}

function RenderIndicator({
  active,
  renderPercent,
  lastOutcome,
  onShowConsole,
}: Pick<StatusBarProps, "active" | "renderPercent" | "lastOutcome" | "onShowConsole">) {
  if (active) {
    const percent = active.progress ? renderPercent : null;
    return (
      <Item className="text-fg">
        <Loader2 className="animate-spin text-accent" />
        {active.queued ? "Queued" : "Rendering"} {active.request.scene}
        {percent !== null && <span className="tabular-nums text-fg-muted">{percent}%</span>}
      </Item>
    );
  }
  if (!lastOutcome) return null;
  if (lastOutcome.success) {
    return (
      <Item>
        <CheckCircle2 className="text-success" />
        Rendered {lastOutcome.request.scene} in {formatDuration(Math.round(lastOutcome.durationMs / 100) / 10)}
      </Item>
    );
  }
  const cancelled = lastOutcome.status === "cancelled";
  return (
    <button type="button" onClick={onShowConsole} className="flex h-full items-center gap-1.5 px-2 hover:bg-raised hover:text-fg [&_svg]:size-3">
      {cancelled ? <CircleSlash className="text-fg-subtle" /> : <XCircle className="text-danger" />}
      {cancelled ? "Render cancelled" : "Render failed — show console"}
    </button>
  );
}

export function StatusBar(props: StatusBarProps) {
  const { storageMode, cursor, diagnostics, onOpenSetup } = props;
  const latexMissing = diagnostics !== null && !diagnostics.dependencies.latex_available;

  return (
    <footer className="flex h-6 shrink-0 items-center justify-between border-t border-line bg-surface text-2xs text-fg-subtle">
      <div className="flex h-full min-w-0 items-center">
        <ConnectionIndicator backend={props.backend} connection={props.connection} />
        <RenderIndicator
          active={props.active}
          renderPercent={props.renderPercent}
          lastOutcome={props.lastOutcome}
          onShowConsole={props.onShowConsole}
        />
      </div>

      <div className="flex h-full items-center">
        {cursor && (
          <Item className="tabular-nums">
            Ln {cursor.line}, Col {cursor.column}
          </Item>
        )}
        <Item>
          {storageMode === "browser" ? <Globe /> : <HardDrive />}
          {storageMode === "browser" ? "Browser storage" : "Workspace folder"}
        </Item>
        {diagnostics && (
          <Tooltip content={diagnostics.description} side="top">
            <Item className="cursor-default">
              {PROFILE_LABELS[diagnostics.profile] ?? diagnostics.profile} profile · {diagnostics.preview_quality}
            </Item>
          </Tooltip>
        )}
        {latexMissing && (
          <button
            type="button"
            onClick={onOpenSetup}
            className="flex h-full items-center gap-1.5 px-2 text-warning hover:bg-raised [&_svg]:size-3"
          >
            <AlertTriangle />
            LaTeX not installed
          </button>
        )}
      </div>
    </footer>
  );
}
