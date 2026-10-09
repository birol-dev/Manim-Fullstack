import { useEffect, useLayoutEffect, useRef } from "react";
import { CornerDownRight, FileCode2, Terminal } from "lucide-react";

import { EmptyState } from "@/components/ui/panel";
import type { LogEntry, LogLevel } from "@/hooks/useLogs";
import { findLineReferenceMatch } from "@/lib/logs";
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
  /** The script this output came from, when it isn't the open file. */
  otherFile?: string | null;
  onOpenFile?: (name: string) => void;
  onJumpToLine: (line: number) => void;
}

/** True while the user has text selected inside *element* (they're copying, not navigating). */
function selectingIn(element: Element): boolean {
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed || !selection.toString()) return false;
  for (let index = 0; index < selection.rangeCount; index += 1) {
    if (selection.getRangeAt(index).intersectsNode(element)) return true;
  }
  return false;
}

export function ConsoleView({ logs, linkFiles, otherFile = null, onOpenFile, onJumpToLine }: ConsoleViewProps) {
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
      {otherFile && (
        <div className="sticky -top-2 z-10 -mx-3 -mt-2 mb-1 flex items-center gap-2 border-b border-line bg-surface px-3 py-1 font-sans text-2xs text-fg-subtle">
          <FileCode2 className="size-3 shrink-0" />
          <span className="min-w-0 truncate">
            Output from <span className="font-mono text-fg-muted">{otherFile}</span>, not the open file
          </span>
          {onOpenFile && (
            <button
              type="button"
              onClick={() => onOpenFile(otherFile)}
              className="shrink-0 rounded border border-line-strong bg-raised px-1.5 text-fg-muted transition-colors hover:border-accent hover:text-accent"
            >
              Open {otherFile}
            </button>
          )}
        </div>
      )}
      {logs.map((entry) => {
        const reference = entry.level === "command" ? null : findLineReferenceMatch(entry.text, linkFiles);
        const line = reference?.line ?? null;
        return (
          <div key={entry.id} className={cn("group flex items-start gap-2 whitespace-pre-wrap break-words", LEVEL_STYLES[entry.level])}>
            {reference ? (
              <span className="min-w-0 flex-1">
                {entry.text.slice(0, reference.start)}
                {/* Mouse shortcut only; the "Line N" button is the keyboard and screen reader control. */}
                <span
                  data-line-link
                  onClick={(event) => {
                    // Selecting the link's text to copy it shouldn't jump; a selection elsewhere doesn't matter.
                    if (!selectingIn(event.currentTarget)) onJumpToLine(reference.line);
                  }}
                  className="cursor-pointer underline decoration-dotted decoration-fg-subtle/50 underline-offset-2 hover:decoration-accent"
                >
                  {entry.text.slice(reference.start, reference.end)}
                </span>
                {entry.text.slice(reference.end)}
              </span>
            ) : (
              <span className="min-w-0 flex-1">{entry.text}</span>
            )}
            {line !== null && (
              <button
                type="button"
                onClick={() => onJumpToLine(line)}
                aria-label={`Go to line ${line}`}
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
