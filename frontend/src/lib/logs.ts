function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export interface LineReference {
  line: number;
  /** Character range of the reference (e.g. `scene.py", line 12`) in the message. */
  start: number;
  end: number;
}

/**
 * Find a line reference in *message* that points into one of *filenames*.
 *
 * Handles Python tracebacks (`File ".../scene.py", line 12`) and Rich's
 * compact form (`/path/scene.py:12 in construct`). References to other files
 * (Manim's own sources, for example) are ignored on purpose.
 */
export function findLineReferenceMatch(message: string, filenames: readonly string[]): LineReference | null {
  for (const filename of filenames) {
    if (!filename) continue;
    const name = escapeRegExp(filename);
    const boundary = `(?:^|[\\s"'/\\\\(])`;
    const traceback = new RegExp(`${boundary}(${name}"?,\\s+line\\s+(\\d+))`);
    const compact = new RegExp(`${boundary}(${name}:(\\d+))\\b`);
    const match = traceback.exec(message) ?? compact.exec(message);
    if (match) {
      const start = match.index + match[0].length - match[1].length;
      return { line: Number(match[2]), start, end: start + match[1].length };
    }
  }
  return null;
}

/** Line number of the first reference into one of *filenames* in *message*. */
export function findLineReference(message: string, filenames: readonly string[]): number | null {
  return findLineReferenceMatch(message, filenames)?.line ?? null;
}

const EXCEPTION_LINE = /^\s*(?:[│|]\s*)?([A-Z]\w*(?:Error|Exception|Exit|Interrupt)(?::.*)?)\s*(?:[│|]\s*)?$/;

export interface ErrorLocation {
  line: number;
  message: string;
}

/**
 * The last line in *texts* that points into one of *filenames*, plus the
 * exception message printed after it (e.g. "NameError: name 'x' is not defined").
 */
export function findErrorLocation(texts: readonly string[], filenames: readonly string[]): ErrorLocation | null {
  let line: number | null = null;
  let lineIndex = -1;
  for (let index = texts.length - 1; index >= 0; index -= 1) {
    line = findLineReference(texts[index], filenames);
    if (line !== null) {
      lineIndex = index;
      break;
    }
  }
  if (line === null) return null;

  let message = "Error";
  for (let index = texts.length - 1; index > lineIndex; index -= 1) {
    const match = EXCEPTION_LINE.exec(texts[index]);
    if (match) {
      message = match[1].trim();
      break;
    }
  }
  return { line, message };
}

/**
 * The server's queued notice ("Waiting for another render to finish… (position 2 in queue)")
 * with the live *position*. The line is logged once; later "queued" events only move the overlay
 * and status bar, so the console showed a stale position.
 */
export function withQueuePosition(text: string, position: number | null | undefined): string {
  if (!position) return text;
  const live = `(position ${position} in queue)`;
  return /\(position \d+ in queue\)/.test(text) ? text.replace(/\(position \d+ in queue\)/, live) : `${text} ${live}`;
}

/** Console text for the Copy button: every line, without Rich's box drawing. */
export function consoleCopyText(lines: ReadonlyArray<{ text: string }>, strip: (text: string) => string): string {
  return strip(lines.map((line) => line.text).join("\n"));
}

/** Prefix of the server's queued notice (kept in sync with useRenderSession's QUEUED_MESSAGE_PREFIX). */
const QUEUED_NOTICE = "Waiting for another render";

/** Id of the latest queued notice in the console, or null. */
export function latestQueuedLineId(lines: ReadonlyArray<{ id: number; level: string; text: string }>): number | null {
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    if (lines[index].level === "info" && lines[index].text.startsWith(QUEUED_NOTICE)) return lines[index].id;
  }
  return null;
}
