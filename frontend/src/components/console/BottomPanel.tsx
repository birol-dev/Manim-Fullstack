import { ChevronDown, ChevronUp, Eraser } from "lucide-react";

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

export function BottomPanel(props: BottomPanelProps) {
  const errorCount = props.logs.filter((entry) => entry.level === "error").length;

  return (
    <Tabs
      value={props.tab}
      onValueChange={(value) => props.onTabChange(value as BottomTab)}
      className="flex h-full min-h-0 flex-col bg-surface"
    >
      <div className="flex h-9 shrink-0 items-stretch justify-between border-b border-line pl-1 pr-1.5">
        <TabsList>
          <TabsTrigger value="console">
            Console <CountBadge count={errorCount} tone="danger" />
          </TabsTrigger>
          <TabsTrigger value="timeline">
            Timeline <CountBadge count={props.steps.length} />
          </TabsTrigger>
        </TabsList>

        <div className="flex items-center gap-1">
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

      <TabsContent value="console" className="min-h-0 flex-1">
        <ConsoleView logs={props.logs} linkFiles={props.linkFiles} onJumpToLine={props.onJumpToLine} />
      </TabsContent>
      <TabsContent value="timeline" className="min-h-0 flex-1">
        <TimelineView scene={props.scene} steps={props.steps} activeIndex={props.activeStep} onJumpToLine={props.onJumpToLine} />
      </TabsContent>
    </Tabs>
  );
}
