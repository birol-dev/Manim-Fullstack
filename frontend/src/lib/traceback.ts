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
/**
 * Rich code row: "│ ❱ 7 │   code │", "│   6 │   code │", or, for a line with no
 * indentation (Rich only draws the "│" guide for indented code), "│   2 class A(Scene): │".
 * Layout: the box edge, a space, the ❱ marker or a space, then the right-aligned
 * line number. A wrapped frame header tail ("│ 2 in render") has no marker column,
 * so it doesn't match.
 */
const RICH_CODE = /^│ (❱|\s)\s*(\d+)(?: │| |$)/;

export interface RichCodeRow {
  line: number;
  failing: boolean;
  /** Length of the gutter (box edge, marker, number, and the indent guide when present). */
  gutter: number;
}

/** Parse a Rich traceback code row, or null when *text* isn't one. */
export function parseRichCodeRow(text: string): RichCodeRow | null {
  const match = RICH_CODE.exec(text);
  if (!match) return null;
  return { line: Number(match[2]), failing: match[1] === "❱", gutter: match[0].length };
}
/**
 * Installed packages: never the user's script, even when a file shares its name
 * (manim/scene/scene.py). Covers raw paths and the server's redacted forms
 * ("<site-packages>/manim/...", "<python-lib>/...", "<venv>/...").
 */
const LIBRARY_PATH = /site-packages|dist-packages|[\\/]lib[\\/]python\d|<python-lib>|<venv>/;
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
      const code = position === 0 ? null : parseRichCodeRow(entry.text);
      const blank = !entry.text.replace(/[│\s]/g, "");
      rows.push({
        kind: "line",
        entry,
        // Code rows jump to their own line; the header and plain-Python code rows to the frame's line.
        line: blank ? null : (code?.line ?? frame.line),
        userFrame: true,
        failing: Boolean(code?.failing),
        header: position === 0,
      });
    });
  }
  flushHidden();
  return rows;
}

interface Segment<T extends ConsoleLine> {
  rows: ConsoleRow<T>[];
  /** Index just past the segment. */
  next: number;
  /**
   * More output can't change these rows: a plain line, or a traceback whose end
   * was seen. A traceback still streaming in is regrouped when lines arrive.
   */
  closed: boolean;
}

/** Group the segment starting at *index*: one plain line, or a whole traceback. */
function groupSegment<T extends ConsoleLine>(logs: readonly T[], index: number, linkFiles: readonly string[]): Segment<T> {
  const entry = logs[index];
  const rich = RICH_START.test(entry.text);
  const plain = PY_START.test(entry.text.trimStart());
  if (!rich && !plain) return { rows: [lineRow(entry, linkFiles)], next: index + 1, closed: true };

  const rows: ConsoleRow<T>[] = [lineRow(entry, linkFiles)];
  let cursor = index + 1;
  const frames: Frame<T>[] = [];
  const preamble: T[] = [];
  let closed = false;
  while (cursor < logs.length) {
    const current = logs[cursor];
    const text = current.text;
    if (rich ? RICH_END.test(text) : !/^\s/.test(text)) {
      closed = true; // plain: the unindented error line ends it
      break;
    }
    const isHeader = rich ? RICH_FRAME.test(text) && !RICH_CODE.test(text) : PY_FRAME.test(text);
    if (isHeader) {
      const line = findLineReference(rich ? joinWrappedHeader(text, logs[cursor + 1]?.text) : text, linkFiles);
      const user = line !== null && !LIBRARY_PATH.test(text);
      frames.push({ entries: [current], user, line: user ? line : null });
    } else if (frames.length > 0) {
      frames[frames.length - 1].entries.push(current);
    } else {
      preamble.push(current);
    }
    cursor += 1;
  }
  preamble.forEach((item) => rows.push(lineRow(item, linkFiles)));
  // Only collapse when there is a user frame to show; otherwise every frame is a hint.
  if (frames.some((frame) => frame.user)) {
    rows.push(...frameRows(frames));
  } else {
    for (const frame of frames) frame.entries.forEach((item) => rows.push(lineRow(item, linkFiles)));
  }
  return { rows, next: cursor, closed };
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
  for (let index = 0; index < logs.length; ) {
    const segment = groupSegment(logs, index, linkFiles);
    rows.push(...segment.rows);
    index = segment.next;
  }
  return rows;
}

// ---- Copying ----------------------------------------------------------------
const BOX_EDGE = /[│┃║]/;
const BOX_RULE_LINE = /^\s*[╭╰┏┗╔╚┌└]?[─━═\s]*(.*?)[─━═\s]*[╮╯┓┛╗╝┐┘]?\s*$/;
const BOX_CHARS = /[\u2500-\u257F]/g;

/**
 * Plain text for a copied console selection: Rich's traceback box (│ ╭ ╮ ╰ ╯ ─
 * and friends) is removed, so pasting a traceback into an issue or a chat gives
 * readable lines. Top/bottom rules keep their title ("Traceback (most recent
 * call last)"); code rows keep their indentation and the ❱ marker.
 */
export function stripBoxDrawing(text: string): string {
  if (!/[\u2500-\u257F]/.test(text)) return text;
  const out: string[] = [];
  for (const raw of text.split(/\r?\n/)) {
    const isRule = /^\s*[╭╰┏┗╔╚┌└─━═]/.test(raw) && !/^\s*[│┃║]/.test(raw);
    if (isRule) {
      const title = (BOX_RULE_LINE.exec(raw)?.[1] ?? "").replace(BOX_CHARS, "").trim();
      if (title) out.push(title);
      continue;
    }
    let line = raw;
    // Outer border: "│ " at the start and " │" at the end of a boxed row.
    line = line.replace(new RegExp(`^(\\s*)${BOX_EDGE.source} ?`), "$1");
    line = line.replace(new RegExp(` ?${BOX_EDGE.source}\\s*$`), "");
    // Inner separators and indent guides become spaces, so indentation survives.
    line = line.replace(BOX_CHARS, " ").replace(/\s+$/, "");
    out.push(line);
  }
  // Rows that were only border (e.g. "│      │") are empty now; drop runs of them at the ends.
  while (out.length && !out[0].trim()) out.shift();
  while (out.length && !out[out.length - 1].trim()) out.pop();
  return out.join("\n");
}

interface CachedSegment<T extends ConsoleLine> {
  firstId: number;
  lastId: number;
  length: number;
  rows: ConsoleRow<T>[];
}

/**
 * groupConsoleRows for a log that grows at the end (and drops lines at the
 * front once it is full). Closed segments are reused, so a new line costs one
 * segment's work instead of a pass over the whole log (up to 2,000 lines).
 * Gives the same rows as groupConsoleRows.
 */
export function createConsoleGrouper<T extends ConsoleLine>() {
  let segments: CachedSegment<T>[] = [];
  let linkKey = "";
  let scanned = 0;

  return {
    group(logs: readonly T[], linkFiles: readonly string[]): ConsoleRow<T>[] {
      scanned = 0;
      const key = linkFiles.join("\n");
      if (key !== linkKey) {
        segments = [];
        linkKey = key;
      }
      // Lines dropped at the front: forget segments that lost lines (a cut traceback regroups as plain lines).
      const firstId = logs[0]?.id;
      let drop = 0;
      while (drop < segments.length && (firstId === undefined || segments[drop].firstId < firstId)) drop += 1;
      if (drop > 0) segments = segments.slice(drop);

      // Keep cached segments while they line up with the log.
      const kept: CachedSegment<T>[] = [];
      let index = 0;
      for (const segment of segments) {
        const last = index + segment.length - 1;
        if (logs[index]?.id !== segment.firstId || logs[last]?.id !== segment.lastId) break;
        kept.push(segment);
        index += segment.length;
      }
      segments = kept;

      while (index < logs.length) {
        const segment = groupSegment(logs, index, linkFiles);
        scanned += segment.next - index;
        if (segment.closed) {
          segments.push({ firstId: logs[index].id, lastId: logs[segment.next - 1].id, length: segment.next - index, rows: segment.rows });
          index = segment.next;
          continue;
        }
        // A traceback still streaming: show it, but group it again next time.
        return segments.flatMap((cached) => cached.rows).concat(segment.rows);
      }
      return segments.flatMap((cached) => cached.rows);
    },
    /** Lines grouped by the last call (for tests). */
    get scanned() {
      return scanned;
    },
  };
}
