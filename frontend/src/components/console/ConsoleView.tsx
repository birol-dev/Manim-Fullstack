import { useEffect, useLayoutEffect, useRef } from "react";
import { CornerDownRight, Terminal } from "lucide-react";

import { EmptyState } from "@/components/ui/panel";
import type { LogEntry, LogLevel } from "@/hooks/useLogs";
import { findLineReference } from "@/lib/logs";
import { cn } from "@/lib/utils";

const LEVEL_STYLES: Record<LogLevel, string> = {
  command: "text-accent",
  info: "text-fg-muted",
  success: "text-success",
  warning: "text-warning",
  error: "text-danger",
  stdout: "text-fg-muted",
  stderr: "text-fg-subtle",
};

interface ConsoleViewProps {
  logs: LogEntry[];
  /** Files whose line references become clickable. */
  linkFiles: string[];
  onJumpToLine: (line: number) => void;
}

export function ConsoleView({ logs, linkFiles, onJumpToLine }: ConsoleViewProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);

  useLayoutEffect(() => {
    const element = scrollRef.current;
    if (element && stickToBottom.current) element.scrollTop = element.scrollHeight;
  }, [logs]);

  // A cleared console starts following new output again.
  useEffect(() => {
    if (logs.length === 0) stickToBottom.current = true;
  }, [logs.length]);

  if (logs.length === 0) {
    return (
      <EmptyState
        className="h-full py-4"
        icon={<Terminal />}
        title="No output yet"
        description="Manim's logs stream here while a scene renders. Errors link back to the line that caused them."
      />
    );
  }

  return (
    <div
      ref={scrollRef}
      role="log"
      aria-label="Render output"
      onScroll={(event) => {
        const element = event.currentTarget;
        stickToBottom.current = element.scrollHeight - element.scrollTop - element.clientHeight < 24;
      }}
      tabIndex={0}
      className="h-full min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 py-2 font-mono text-[12px] leading-[1.45] select-text outline-none"
    >
      {logs.map((entry) => {
        const line = entry.level === "command" ? null : findLineReference(entry.text, linkFiles);
        return (
          <div key={entry.id} className={cn("group flex items-start gap-2 whitespace-pre-wrap break-words", LEVEL_STYLES[entry.level])}>
            {line !== null ? (
              <button
                type="button"
                onClick={() => onJumpToLine(line)}
                className="min-w-0 flex-1 text-left underline decoration-dotted decoration-fg-subtle/50 underline-offset-2 hover:decoration-accent"
              >
                {entry.text}
              </button>
            ) : (
              <span className="min-w-0 flex-1">{entry.text}</span>
            )}
            {line !== null && (
              <button
                type="button"
                onClick={() => onJumpToLine(line)}
                className="mt-0.5 inline-flex shrink-0 items-center gap-1 rounded border border-line-strong bg-raised px-1.5 font-sans text-2xs text-fg-muted transition-colors hover:border-accent hover:text-accent"
                title={`Jump to line ${line}`}
              >
                <CornerDownRight className="size-3" />
                Line {line}
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
