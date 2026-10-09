import { findLineReference } from "./logs";

/** Minimal shape of a console line (matches useLogs' LogEntry). */
export interface ConsoleLine {
  id: number;
  level: string;
  text: string;
}

export type ConsoleRow<T extends ConsoleLine> =
  | {
      kind: "line";
      entry: T;
      /** Editor line this row jumps to, or null when it isn't a reference into the user's script. */
      line: number | null;
      /** Part of a traceback frame in the user's own script. */
      userFrame: boolean;
      /** The `❱ 7 │ …` row Rich marks as the failing line. */
      failing: boolean;
      /** First row of a user frame (where the "Line N" chip goes). */
      header?: boolean;
    }
  | {
      kind: "hidden";
      /** Stable key: id of the first hidden entry. */
      id: number;
      entries: T[];
      frames: number;
    };

const RICH_START = /^╭─+.*Traceback \(most recent call last\)/;
const RICH_END = /^╰─+/;
/** A Rich frame header: "│ /path/to/file.py:123 in render  │" (may wrap onto the next row). */
const RICH_FRAME = /^│\s+(?:[A-Za-z]:)?[^\s│]*\.py(?::\d*)?(?:\s|$)/;
/** Rich code row: "│ ❱ 7 │ code │" or "│   6 │ code │". */
const RICH_CODE = /^│\s+(❱)?\s*(\d+)\s+│/;
/** Installed packages: never the user's script, even when a file shares its name (manim/scene/scene.py). */
const LIBRARY_PATH = /site-packages|dist-packages|[\\/]lib[\\/]python\d/;
const PY_START = /^Traceback \(most recent call last\):/;
const PY_FRAME = /^\s+File "([^"]+)", line (\d+)/;

/** Rich wraps long frame headers mid-token ("commands.py:12" + "2 in render"); undo that. */
function joinWrappedHeader(first: string, next: string | undefined): string {
  const head = first.replace(/^│\s?/, "").replace(/\s*│\s*$/, "");
  if (!next || RICH_FRAME.test(next) || RICH_CODE.test(next)) return head;
  const tail = next.replace(/^│\s?/, "").replace(/\s*│\s*$/, "");
  if (!tail.trim()) return head;
  // The wrap happens at the box edge, so the two halves join without a space.
  return `${head}${tail.trimStart()}`;
}

interface Frame<T> {
  entries: T[];
  user: boolean;
  /** Line number from the header when it points into a user script. */
  line: number | null;
}

function lineRow<T extends ConsoleLine>(entry: T, linkFiles: readonly string[]): ConsoleRow<T> {
  const line = entry.level === "command" || LIBRARY_PATH.test(entry.text) ? null : findLineReference(entry.text, linkFiles);
  return { kind: "line", entry, line, userFrame: false, failing: false };
}

function frameRows<T extends ConsoleLine>(frames: Frame<T>[]): ConsoleRow<T>[] {
  const rows: ConsoleRow<T>[] = [];
  let hidden: T[] = [];
  let hiddenFrames = 0;
  const flushHidden = () => {
    if (hidden.length === 0) return;
    rows.push({ kind: "hidden", id: hidden[0].id, entries: hidden, frames: hiddenFrames });
    hidden = [];
    hiddenFrames = 0;
  };
  for (const frame of frames) {
    if (!frame.user) {
      hidden.push(...frame.entries);
      hiddenFrames += 1;
      continue;
    }
    flushHidden();
    frame.entries.forEach((entry, position) => {
      const code = RICH_CODE.exec(entry.text);
      const own = code ? Number(code[2]) : null;
      const blank = !entry.text.replace(/[│\s]/g, "");
      rows.push({
        kind: "line",
        entry,
        // Code rows jump to their own line; the header and plain-Python code rows to the frame's line.
        line: blank ? null : (own ?? frame.line),
        userFrame: true,
        failing: Boolean(code?.[1]),
        header: position === 0,
      });
    });
  }
  flushHidden();
  return rows;
}

/**
 * Group console output for display: inside a Rich or plain Python traceback,
 * runs of frames outside the user's scripts (Manim internals, site-packages)
 * collapse into one "hidden" row, while the user's frames stay visible and
 * every row in them links to a line. The header and the final error line are
 * always kept.
 */
export function groupConsoleRows<T extends ConsoleLine>(logs: readonly T[], linkFiles: readonly string[]): ConsoleRow<T>[] {
  const rows: ConsoleRow<T>[] = [];
  let index = 0;
  while (index < logs.length) {
    const entry = logs[index];
    const rich = RICH_START.test(entry.text);
    const plain = PY_START.test(entry.text.trimStart());
    if (!rich && !plain) {
      rows.push(lineRow(entry, linkFiles));
      index += 1;
      continue;
    }

    rows.push(lineRow(entry, linkFiles));
    index += 1;
    const frames: Frame<T>[] = [];
    const preamble: T[] = [];
    while (index < logs.length) {
      const current = logs[index];
      const text = current.text;
      if (rich ? RICH_END.test(text) : !/^\s/.test(text)) break; // plain: the unindented error line ends it
      const isHeader = rich ? RICH_FRAME.test(text) && !RICH_CODE.test(text) : PY_FRAME.test(text);
      if (isHeader) {
        const line = findLineReference(rich ? joinWrappedHeader(text, logs[index + 1]?.text) : text, linkFiles);
        const user = line !== null && !LIBRARY_PATH.test(text);
        frames.push({ entries: [current], user, line: user ? line : null });
      } else if (frames.length > 0) {
        frames[frames.length - 1].entries.push(current);
      } else {
        preamble.push(current);
      }
      index += 1;
    }
    preamble.forEach((item) => rows.push(lineRow(item, linkFiles)));
    // Only collapse when there is a user frame to show; otherwise every frame is a hint.
    if (frames.some((frame) => frame.user)) {
      rows.push(...frameRows(frames));
    } else {
      for (const frame of frames) frame.entries.forEach((item) => rows.push(lineRow(item, linkFiles)));
    }
  }
  return rows;
}
