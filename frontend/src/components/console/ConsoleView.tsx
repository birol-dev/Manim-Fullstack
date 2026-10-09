import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ChevronRight, CornerDownRight, Terminal } from "lucide-react";

import { EmptyState } from "@/components/ui/panel";
import type { LogEntry, LogLevel } from "@/hooks/useLogs";
import { findLineReferenceMatch, type LineReference } from "@/lib/logs";
import { groupConsoleRows, stripBoxDrawing } from "@/lib/traceback";
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

/** Rich code row inside a traceback box: "│ ❱ 7 │ code │" (gutter = everything up to the second "│"). */
const RICH_CODE_GUTTER = /^│\s+(?:❱\s*)?\d+\s+│/;

interface ConsoleViewProps {
  logs: LogEntry[];
  /** Files whose line references become clickable. */
  linkFiles: string[];
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

/**
 * The clickable part of a row. In a user traceback frame's code rows that is
 * the code after the line-number gutter (or the whole indented line in a plain
 * Python traceback); elsewhere it is the `file:line` reference itself.
 */
function linkRange(text: string, line: number, userFrame: boolean, linkFiles: string[]): LineReference | null {
  const reference = findLineReferenceMatch(text, linkFiles);
  if (reference) return reference;
  if (!userFrame) return null;
  const gutter = RICH_CODE_GUTTER.exec(text);
  const start = gutter ? gutter[0].length : text.length - text.trimStart().length;
  const body = text.slice(start).replace(/\s*│?\s*$/, "");
  if (!body.trim()) return null;
  const lead = body.length - body.trimStart().length;
  return { line, start: start + lead, end: start + body.length };
}

function LogLine({
  entry,
  line,
  linkFiles,
  userFrame = false,
  failing = false,
  header = false,
  onJumpToLine,
}: {
  entry: LogEntry;
  line: number | null;
  linkFiles: string[];
  userFrame?: boolean;
  failing?: boolean;
  header?: boolean;
  onJumpToLine: (line: number) => void;
}) {
  const range = line !== null ? linkRange(entry.text, line, userFrame, linkFiles) : null;
  // Code rows of the user's frame jump to their own line; the "Line N" button (the keyboard and
  // screen reader control) stays on plain references and the frame header.
  const target = userFrame && !header ? line : (range?.line ?? line);
  const showButton = target !== null && range !== null && (!userFrame || header);
  // Rich draws tracebacks as a box; wrapping its rows shreds the border, so they scroll sideways instead.
  const boxed = /^[╭│╰]/.test(entry.text);
  return (
    <div
      className={cn(
        "group flex items-start gap-2",
        boxed ? "w-max min-w-full whitespace-pre" : "whitespace-pre-wrap break-words",
        LEVEL_STYLES[entry.level],
        userFrame && "text-fg",
        failing && "bg-danger-soft",
      )}
    >
      {range && target !== null ? (
        <span className="min-w-0 flex-1">
          {entry.text.slice(0, range.start)}
          {/* Mouse shortcut only; the "Line N" button is the keyboard and screen reader control. */}
          <span
            data-line-link
            title={`Jump to line ${target}`}
            onClick={(event) => {
              // Selecting the link's text to copy it shouldn't jump; a selection elsewhere doesn't matter.
              if (!selectingIn(event.currentTarget)) onJumpToLine(target);
            }}
            className="cursor-pointer underline decoration-dotted decoration-fg-subtle/50 underline-offset-2 hover:text-fg hover:decoration-accent"
          >
            {entry.text.slice(range.start, range.end)}
          </span>
          {entry.text.slice(range.end)}
        </span>
      ) : (
        <span className="min-w-0 flex-1">{entry.text}</span>
      )}
      {showButton && (
        <button
          type="button"
          onClick={() => onJumpToLine(target)}
          aria-label={`Go to line ${target}`}
          className="mt-0.5 inline-flex shrink-0 items-center gap-1 rounded border border-line-strong bg-raised px-1.5 font-sans text-2xs text-fg-muted transition-colors hover:border-accent hover:text-accent"
          title={`Jump to line ${target}`}
        >
          <CornerDownRight className="size-3" />
          Line {target}
        </button>
      )}
    </div>
  );
}

export function ConsoleView({ logs, linkFiles, onJumpToLine }: ConsoleViewProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  const [expanded, setExpanded] = useState<ReadonlySet<number>>(() => new Set());
  const rows = useMemo(() => groupConsoleRows(logs, linkFiles), [logs, linkFiles]);

  useLayoutEffect(() => {
    const element = scrollRef.current;
    if (element && stickToBottom.current) element.scrollTop = element.scrollHeight;
  }, [rows]);

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
      onCopy={(event) => {
        // Copy the traceback without Rich's box border characters.
        const selected = window.getSelection()?.toString() ?? "";
        const plain = stripBoxDrawing(selected);
        if (!selected || plain === selected) return;
        event.preventDefault();
        event.clipboardData.setData("text/plain", plain);
      }}
      tabIndex={0}
      className="h-full min-h-0 flex-1 overflow-auto overscroll-contain px-3 py-2 font-mono text-[12px] leading-[1.45] select-text outline-none"
    >
      {rows.map((row) => {
        if (row.kind === "line") {
          return (
            <LogLine
              key={row.entry.id}
              entry={row.entry}
              line={row.line}
              linkFiles={linkFiles}
              userFrame={row.userFrame}
              failing={row.failing}
              header={row.header}
              onJumpToLine={onJumpToLine}
            />
          );
        }
        const open = expanded.has(row.id);
        return (
          <div key={`hidden-${row.id}`}>
            <button
              type="button"
              aria-expanded={open}
              onClick={() =>
                setExpanded((previous) => {
                  const next = new Set(previous);
                  if (open) next.delete(row.id);
                  else next.add(row.id);
                  return next;
                })
              }
              className="sticky left-0 my-0.5 inline-flex items-center gap-1 rounded px-1 font-sans text-2xs text-fg-subtle transition-colors hover:bg-raised hover:text-fg-muted focus-visible:outline-1 focus-visible:outline-accent"
            >
              <ChevronRight className={cn("size-3 transition-transform", open && "rotate-90")} />
              {open
                ? `Hide ${row.frames} library ${row.frames === 1 ? "frame" : "frames"}`
                : `${row.frames} library ${row.frames === 1 ? "frame" : "frames"} hidden (Manim internals) · show`}
            </button>
            {open &&
              row.entries.map((entry) => (
                <LogLine key={entry.id} entry={entry} line={null} linkFiles={linkFiles} onJumpToLine={onJumpToLine} />
              ))}
          </div>
        );
      })}
    </div>
  );
}
