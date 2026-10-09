import { ChevronDown, ChevronUp, Eraser, FileCode2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip } from "@/components/ui/tooltip";
import type { LogEntry } from "@/hooks/useLogs";
import type { AnimationStep } from "@/lib/types";
import { ConsoleView } from "./ConsoleView";
import { TimelineView } from "./TimelineView";

export type BottomTab = "console" | "timeline";

interface BottomPanelProps {
  tab: BottomTab;
  onTabChange: (tab: BottomTab) => void;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  logs: LogEntry[];
  linkFiles: string[];
  /** Set when the console shows another file's output. */
  logsFile: string | null;
  onOpenLogsFile: (name: string) => void;
  onClearLogs: () => void;
  scene: string;
  steps: AnimationStep[];
  activeStep: number | null;
  /** Overall render progress, or null when idle. */
  renderPercent: number | null;
  onJumpToLine: (line: number) => void;
}

function CountBadge({ count, tone = "neutral" }: { count: number; tone?: "neutral" | "danger" }) {
  if (count === 0) return null;
  return (
    <span
      className={
        tone === "danger"
          ? "rounded-full bg-danger-soft px-1.5 text-2xs font-medium leading-4 text-danger"
          : "rounded-full bg-overlay px-1.5 text-2xs font-medium leading-4 text-fg-muted"
      }
    >
      {count}
    </span>
  );
}

/**
 * "Output from X, not the open file", as a chip in the panel header instead of
 * a full row above the log (that row cost the preview ~30 px at 1024x700).
 */
function OtherFileChip({ file, onOpen }: { file: string; onOpen: (name: string) => void }) {
  return (
    <div
      role="note"
      title={`Output from ${file}, not the open file`}
      className="flex h-6 min-w-0 items-center gap-1.5 self-center rounded-md border border-line-strong bg-raised pl-1.5 pr-0.5 text-2xs text-fg-muted"
    >
      <FileCode2 className="size-3 shrink-0" />
      <span className="min-w-0 truncate">
        Output from <span className="font-mono text-fg">{file}</span>
        <span className="@max-[640px]/bottom:sr-only">, not the open file</span>
      </span>
      <button
        type="button"
        onClick={() => onOpen(file)}
        aria-label={`Open ${file}`}
        className="shrink-0 rounded px-1 font-medium text-accent transition-colors hover:bg-overlay focus-visible:outline-1 focus-visible:outline-accent"
      >
        Open
      </button>
    </div>
  );
}

export function BottomPanel(props: BottomPanelProps) {
  const errorCount = props.logs.filter((entry) => entry.level === "error").length;

  return (
    <Tabs
      value={props.tab}
      onValueChange={(value) => props.onTabChange(value as BottomTab)}
      className="@container/bottom flex h-full min-h-0 flex-col bg-surface"
    >
      <div className="flex h-9 shrink-0 items-stretch justify-between gap-2 border-b border-line pl-1 pr-1.5">
        <TabsList className="shrink-0">
          <TabsTrigger value="console">
            Console <CountBadge count={errorCount} tone="danger" />
          </TabsTrigger>
          <TabsTrigger value="timeline">
            Timeline <CountBadge count={props.steps.length} />
          </TabsTrigger>
        </TabsList>

        <div className="flex min-w-0 items-center gap-1">
          {props.logsFile && props.tab === "console" && <OtherFileChip file={props.logsFile} onOpen={props.onOpenLogsFile} />}
          {props.renderPercent !== null && (
            <div className="mr-2 flex items-center gap-2" aria-label="Render progress">
              <Progress value={props.renderPercent} striped className="w-28" />
              <span className="w-8 text-right text-2xs tabular-nums text-fg-muted">{props.renderPercent}%</span>
            </div>
          )}
          {props.tab === "console" && props.logs.length > 0 && (
            <Tooltip content="Clear console">
              <Button variant="ghost" size="icon-xs" aria-label="Clear console" onClick={props.onClearLogs}>
                <Eraser />
              </Button>
            </Tooltip>
          )}
          <Tooltip content={props.collapsed ? "Expand panel" : "Collapse panel"}>
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label={props.collapsed ? "Expand panel" : "Collapse panel"}
              onClick={props.onToggleCollapsed}
            >
              {props.collapsed ? <ChevronUp /> : <ChevronDown />}
            </Button>
          </Tooltip>
        </div>
      </div>

      <TabsContent value="console" className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <ConsoleView
          logs={props.logs}
          linkFiles={props.linkFiles}
          onJumpToLine={props.onJumpToLine}
        />
      </TabsContent>
      <TabsContent value="timeline" className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <TimelineView scene={props.scene} steps={props.steps} activeIndex={props.activeStep} onJumpToLine={props.onJumpToLine} />
      </TabsContent>
    </Tabs>
  );
}
