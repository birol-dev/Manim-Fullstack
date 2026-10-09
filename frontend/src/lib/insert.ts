/**
 * Where a block of Python statements (from the Shape builder, LaTeX, or Assets
 * panels) goes in a script. Pure functions over the editor's lines so they can
 * be tested without Monaco.
 */

const INDENT = "    ";

/** *line* without a trailing `# comment` (quotes are respected). */
export function stripComment(line: string): string {
  let quote: string | null = null;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    if (quote) {
      if (char === "\\") index += 1;
      else if (char === quote) quote = null;
    } else if (char === '"' || char === "'") {
      quote = char;
    } else if (char === "#") {
      return line.slice(0, index);
    }
  }
  return line;
}

function leading(line: string): string {
  return line.match(/^\s*/)?.[0] ?? "";
}

/** Blank or only a comment: says nothing about the block structure. */
function isTrivia(line: string): boolean {
  return stripComment(line).trim() === "";
}

/** The line starts an indented block (`def f():`, `for x in y:  # note`). */
export function opensBlock(line: string): boolean {
  return stripComment(line).trimEnd().endsWith(":");
}

export function indentBlock(block: string, indent: string): string {
  return block
    .split("\n")
    .map((line) => (line ? indent + line : line))
    .join("\n");
}

/** What the code at *indent*, just below line *fromLine* (1-based), is nested in. */
function enclosingScope(lines: string[], fromLine: number, indent: string): "def" | "class" | "module" {
  let width = indent.length;
  for (let line = fromLine; line >= 1 && width > 0; line -= 1) {
    const text = lines[line - 1];
    if (isTrivia(text)) continue;
    const own = leading(text).length;
    if (own >= width) continue;
    if (/^\s*(?:async\s+)?def\s/.test(text)) return "def";
    if (/^\s*class\s/.test(text)) return "class";
    width = own; // e.g. a for-loop: keep looking for what contains it
  }
  return "module";
}

/** End line (1-based, inclusive) of the block opened at *start*, ignoring trailing blank lines. */
function blockEnd(lines: string[], start: number): number {
  const width = leading(lines[start - 1]).length;
  let end = start;
  for (let line = start + 1; line <= lines.length; line += 1) {
    const text = lines[line - 1];
    if (!text.trim()) continue;
    if (!isTrivia(text) && leading(text).length <= width) break;
    end = line;
  }
  return end;
}

/** The construct() method a statement should go into: the one in the class around the cursor, else the first. */
function findConstruct(lines: string[], cursorLine: number): number | null {
  const isConstruct = (text: string) => /^\s*(?:async\s+)?def\s+construct\s*\(/.test(text);
  for (let line = Math.min(cursorLine, lines.length); line >= 1; line -= 1) {
    if (!/^\s*class\s/.test(lines[line - 1])) continue;
    const end = blockEnd(lines, line);
    // Past the class, unless only blank lines follow it up to the cursor.
    if (cursorLine > end && lines.slice(end, cursorLine).some((other) => other.trim())) break;
    for (let inner = line + 1; inner <= end; inner += 1) if (isConstruct(lines[inner - 1])) return inner;
    break;
  }
  const first = lines.findIndex(isConstruct);
  return first === -1 ? null : first + 1;
}

export interface BlockInsertPlan {
  /** 1-based line the edit applies to. */
  line: number;
  /** true: replace that (blank) line's content; false: add the text as new lines after it. */
  replace: boolean;
  /** Already indented. */
  text: string;
}

/**
 * Plan inserting *block* (unindented statements) for a cursor on *cursorLine*.
 *
 * - On a code line: below it, at its indentation, one level deeper if it opens a
 *   block (a trailing comment after the colon is fine).
 * - On a comment line: below it, at the comment's indentation.
 * - On a blank line: on that line, indented like the code above it.
 * - Statements only make sense inside a method; if the cursor is at module or
 *   class level, the block goes at the end of construct() instead.
 */
export function planBlockInsert(lines: string[], cursorLine: number, block: string): BlockInsertPlan {
  const text = lines[cursorLine - 1] ?? "";
  let plan: BlockInsertPlan;
  let scopeFrom: number;
  let indent: string;

  if (text.trim()) {
    indent = leading(text) + (!isTrivia(text) && opensBlock(text) ? INDENT : "");
    plan = { line: cursorLine, replace: false, text: indentBlock(block, indent) };
    scopeFrom = cursorLine;
  } else {
    indent = "";
    for (let line = cursorLine - 1; line >= 1; line -= 1) {
      const above = lines[line - 1];
      if (isTrivia(above)) continue;
      indent = leading(above) + (opensBlock(above) ? INDENT : "");
      break;
    }
    plan = { line: cursorLine, replace: true, text: indentBlock(block, indent) };
    scopeFrom = cursorLine - 1;
  }

  if (enclosingScope(lines, scopeFrom, indent) === "def") return plan;

  const construct = findConstruct(lines, cursorLine);
  if (construct === null) return plan;
  const end = blockEnd(lines, construct);
  let bodyIndent = leading(lines[construct - 1]) + INDENT;
  for (let line = construct + 1; line <= end; line += 1) {
    if (!isTrivia(lines[line - 1])) {
      bodyIndent = leading(lines[line - 1]);
      break;
    }
  }
  return { line: end, replace: false, text: indentBlock(block, bodyIndent) };
}
