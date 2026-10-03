function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Find a line number in *message* that points into one of *filenames*.
 *
 * Handles Python tracebacks (`File ".../scene.py", line 12`) and Rich's
 * compact form (`/path/scene.py:12 in construct`). References to other files
 * (Manim's own sources, for example) are ignored on purpose.
 */
export function findLineReference(message: string, filenames: readonly string[]): number | null {
  for (const filename of filenames) {
    if (!filename) continue;
    const name = escapeRegExp(filename);
    const boundary = `(?:^|[\\s"'/\\\\(])`;
    const traceback = new RegExp(`${boundary}${name}"?,\\s+line\\s+(\\d+)`);
    const compact = new RegExp(`${boundary}${name}:(\\d+)\\b`);
    const match = traceback.exec(message) ?? compact.exec(message);
    if (match) return Number(match[1]);
  }
  return null;
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
