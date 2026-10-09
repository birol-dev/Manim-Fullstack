/**
 * Where a block of Python statements (from the Shape builder, LaTeX, or Assets
 * panels) goes in a script. Pure functions over the editor's lines so they can
 * be tested without Monaco.
 *
 * A small tokenizer (strings incl. triple quotes and f-strings, comments,
 * brackets, backslash continuations) finds the *logical* statement around the
 * cursor, so a block never lands inside a multi-line call, a continued line,
 * or a string.
 */

const DEFAULT_INDENT = "    ";

// ---- Tokenizer ---------------------------------------------------------------

type Context =
  | { kind: "code"; depth: number; /** f-string replacement field ({...}): ends at the matching "}". */ field: boolean }
  | { kind: "string"; quote: string; triple: boolean; fstring: boolean };

/** What the tokenizer knows about one physical line. */
export interface LineInfo {
  /** The line continues a statement that started on an earlier line (open bracket, string, or `\`). */
  continues: boolean;
  /** The statement is still open at the end of this line. */
  open: boolean;
  /** The line starts inside a (triple-quoted) string. */
  startsInString: boolean;
  /** Last character of code on the line outside strings and comments, at bracket depth 0 ("" if none). */
  lastCode: string;
  /** Only whitespace and/or a comment, and not inside a statement. */
  trivia: boolean;
}

const STRING_PREFIX = /(?:^|[^\w])([rRbBuUfF]{1,2})$/;

/** Tokenize *lines* and describe each one. Unterminated single-quoted strings end at the line end, like Python's error recovery. */
export function scanLines(lines: readonly string[]): LineInfo[] {
  const stack: Context[] = [{ kind: "code", depth: 0, field: false }];
  const infos: LineInfo[] = [];
  let continued = false;

  for (const text of lines) {
    const startsInString = stack.some((context) => context.kind === "string");
    const continues = continued || stack.length > 1 || (stack[0] as { depth: number }).depth > 0;
    let lastCode = "";
    let sawCode = false;
    let backslash = false;

    for (let index = 0; index < text.length; index += 1) {
      const char = text[index];
      const top = stack[stack.length - 1];
      if (top.kind === "string") {
        if (char === "\\") {
          if (index === text.length - 1) backslash = true; // string continues on the next line
          index += 1;
          continue;
        }
        if (top.fstring && (char === "{" || char === "}")) {
          if (text[index + 1] === char) {
            index += 1; // {{ or }} is a literal brace
          } else if (char === "{") {
            stack.push({ kind: "code", depth: 0, field: true });
          }
          continue;
        }
        if (char === top.quote) {
          if (!top.triple) {
            stack.pop();
          } else if (text[index + 1] === char && text[index + 2] === char) {
            stack.pop();
            index += 2;
          }
        }
        continue;
      }

      // Code.
      if (char === "#") break;
      if (char === " " || char === "\t" || char === "\f") continue;
      if (char === "\\" && text.slice(index + 1).trim() === "") {
        backslash = true;
        break;
      }
      sawCode = true;
      if (char === '"' || char === "'") {
        const prefix = STRING_PREFIX.exec(text.slice(Math.max(0, index - 3), index))?.[1] ?? "";
        const triple = text[index + 1] === char && text[index + 2] === char;
        stack.push({ kind: "string", quote: char, triple, fstring: /f/i.test(prefix) });
        if (triple) index += 2;
        if (stack.length === 2 && top.depth === 0) lastCode = char;
        continue;
      }
      if (char === "(" || char === "[" || char === "{") {
        top.depth += 1;
      } else if (char === ")" || char === "]" || char === "}") {
        if (top.field && top.depth === 0 && char === "}") {
          stack.pop(); // back into the f-string
          continue;
        }
        top.depth = Math.max(0, top.depth - 1);
      }
      if (stack.length === 1 && (top.depth === 0 || "([{".includes(char))) lastCode = char;
    }

    // A single-quoted string can't span lines without a backslash; recover like Python.
    while (stack.length > 1) {
      const top = stack[stack.length - 1];
      if (top.kind === "string" && (top.triple || backslash)) break;
      if (top.kind === "code" && top.field) {
        // An f-string field only spans lines inside a triple-quoted f-string.
        const outer = stack[stack.length - 2];
        if (outer.kind === "string" && outer.triple) break;
      }
      stack.pop();
    }

    const root = stack[0] as { depth: number };
    const inString = stack.length > 1;
    continued = backslash && !inString;
    infos.push({
      continues,
      open: continued || inString || root.depth > 0,
      startsInString,
      lastCode,
      trivia: !continues && !sawCode,
    });
  }
  return infos;
}

// ---- Helpers -------------------------------------------------------------------

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
  return line.match(/^[ \t]*/)?.[0] ?? "";
}

/** Indent width with tabs counted to the next multiple of 8, as Python does. */
function indentWidth(line: string): number {
  let width = 0;
  for (const char of leading(line)) width = char === "\t" ? width + 8 - (width % 8) : width + 1;
  return width;
}

/** The line starts an indented block (`def f():`, `for x in y:  # note`). */
export function opensBlock(line: string): boolean {
  return scanLines([line])[0].lastCode === ":";
}

/**
 * One indentation level in this file: a tab if its blocks are tab-indented,
 * otherwise the most common step between nested lines (2, 4, 8 spaces...).
 */
export function detectIndentUnit(lines: readonly string[], infos: readonly LineInfo[] = scanLines(lines)): string {
  let tabs = 0;
  let spaces = 0;
  const steps = new Map<number, number>();
  let previous = 0;
  lines.forEach((text, index) => {
    const info = infos[index];
    if (info.continues || info.trivia || !text.trim()) return;
    const lead = leading(text);
    if (lead.startsWith("\t")) tabs += 1;
    else if (lead) spaces += 1;
    const width = lead.length;
    if (!lead.includes("\t") && width > previous) steps.set(width - previous, (steps.get(width - previous) ?? 0) + 1);
    previous = lead.includes("\t") ? previous : width;
  });
  if (tabs > spaces) return "\t";
  let best = 0;
  let count = 0;
  for (const [step, seen] of steps) {
    if (seen > count || (seen === count && step < best)) {
      best = step;
      count = seen;
    }
  }
  return best > 0 && best <= 8 ? " ".repeat(best) : DEFAULT_INDENT;
}

/** Indent every line of *block* by *indent*; its own 4-space levels become *unit*. */
export function indentBlock(block: string, indent: string, unit: string = DEFAULT_INDENT): string {
  return block
    .split("\n")
    .map((line) => {
      if (!line) return line;
      const own = line.match(/^(?: {4})*/)?.[0] ?? "";
      return indent + unit.repeat(own.length / 4) + line.slice(own.length);
    })
    .join("\n");
}

/** First and last line (1-based) of the logical statement that physical *line* belongs to. */
function statementAround(infos: readonly LineInfo[], line: number): { start: number; end: number } {
  let start = line;
  while (start > 1 && infos[start - 1].continues) start -= 1;
  let end = line;
  while (end < infos.length && infos[end - 1].open) end += 1;
  return { start, end };
}

const DEF = /^\s*(?:async\s+)?def\s/;
const CLASS = /^\s*class\s/;
const CONSTRUCT = /^\s*(?:async\s+)?def\s+construct\s*\(/;

/** What the code at *indent*, just below line *fromLine* (1-based), is nested in. */
function enclosingScope(lines: readonly string[], infos: readonly LineInfo[], fromLine: number, indent: string): "def" | "class" | "module" {
  let width = indentWidth(indent);
  for (let line = fromLine; line >= 1 && width > 0; line -= 1) {
    const info = infos[line - 1];
    if (info.trivia || info.continues || !lines[line - 1].trim()) continue;
    const own = indentWidth(lines[line - 1]);
    if (own >= width) continue;
    if (DEF.test(lines[line - 1])) return "def";
    if (CLASS.test(lines[line - 1])) return "class";
    width = own; // e.g. a for-loop: keep looking for what contains it
  }
  return "module";
}

/** End line (1-based, inclusive) of the block opened by the statement starting at *start*, ignoring trailing blank lines. */
function blockEnd(lines: readonly string[], infos: readonly LineInfo[], start: number): number {
  const width = indentWidth(lines[start - 1]);
  let end = statementAround(infos, start).end;
  for (let line = end + 1; line <= lines.length; line += 1) {
    const info = infos[line - 1];
    if (!lines[line - 1].trim() && !info.continues) continue;
    if (!info.continues && !info.trivia && indentWidth(lines[line - 1]) <= width) break;
    end = line;
  }
  return end;
}

/** The construct() method a statement should go into: the one in the class around the cursor, else the first. */
function findConstruct(lines: readonly string[], infos: readonly LineInfo[], cursorLine: number): number | null {
  const isStatement = (line: number) => !infos[line - 1].continues;
  for (let line = Math.min(cursorLine, lines.length); line >= 1; line -= 1) {
    if (!isStatement(line) || !CLASS.test(lines[line - 1])) continue;
    const end = blockEnd(lines, infos, line);
    // Past the class, unless only blank lines follow it up to the cursor.
    if (cursorLine > end && lines.slice(end, cursorLine).some((other) => other.trim())) break;
    for (let inner = line + 1; inner <= end; inner += 1) if (isStatement(inner) && CONSTRUCT.test(lines[inner - 1])) return inner;
    break;
  }
  const first = lines.findIndex((text, index) => isStatement(index + 1) && CONSTRUCT.test(text));
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

/** Inserting isn't possible here; *reason* says why (shown to the user). */
export interface BlockInsertRefusal {
  refused: string;
}

/**
 * Plan inserting *block* (unindented statements, nested with 4 spaces) for a
 * cursor on *cursorLine*.
 *
 * - On a code line: below the whole statement it belongs to (a multi-line call,
 *   a `\` continuation, a docstring...), at the statement's indentation, one
 *   level deeper if the statement opens a block.
 * - On a comment line: below it, at the comment's indentation.
 * - On a blank line: on that line, indented like the statement above it.
 * - Statements only make sense inside a method; if the cursor is at module or
 *   class level, the block goes at the end of construct() instead.
 * - Indentation follows the file (tabs, or its own number of spaces).
 * - Never inside a string: a cursor in an unterminated string is refused.
 */
export function planBlockInsert(lines: readonly string[], cursorLine: number, block: string): BlockInsertPlan | BlockInsertRefusal {
  const infos = scanLines(lines);
  const unit = detectIndentUnit(lines, infos);
  const line = Math.min(Math.max(cursorLine, 1), Math.max(lines.length, 1));
  const text = lines[line - 1] ?? "";
  const info = infos[line - 1];
  let plan: BlockInsertPlan;
  let scopeFrom: number;
  let indent: string;

  if (info && (text.trim() || info.continues || info.open)) {
    const statement = statementAround(infos, line);
    const last = infos[statement.end - 1];
    if (last.open) {
      return {
        refused:
          last.startsInString || infos.slice(statement.start - 1).some((other) => other.startsInString)
            ? "The cursor is inside a string that never ends. Close it, then insert again."
            : "The cursor is inside a statement that never ends (an open bracket or a trailing \\). Finish it, then insert again.",
      };
    }
    const head = lines[statement.start - 1];
    indent = leading(head) + (!infos[statement.start - 1].trivia && last.lastCode === ":" ? unit : "");
    plan = { line: statement.end, replace: false, text: indentBlock(block, indent, unit) };
    scopeFrom = statement.end;
  } else {
    indent = "";
    for (let above = line - 1; above >= 1; above -= 1) {
      if (infos[above - 1].trivia || !lines[above - 1].trim()) continue;
      const statement = statementAround(infos, above);
      indent = leading(lines[statement.start - 1]) + (infos[statement.end - 1].lastCode === ":" ? unit : "");
      break;
    }
    plan = { line, replace: true, text: indentBlock(block, indent, unit) };
    scopeFrom = line - 1;
  }

  if (enclosingScope(lines, infos, scopeFrom, indent) === "def") return plan;

  const construct = findConstruct(lines, infos, line);
  if (construct === null) return plan;
  const end = blockEnd(lines, infos, construct);
  let bodyIndent = leading(lines[construct - 1]) + unit;
  const headerEnd = statementAround(infos, construct).end;
  for (let inner = headerEnd + 1; inner <= end; inner += 1) {
    if (!infos[inner - 1].trivia && !infos[inner - 1].continues && lines[inner - 1].trim()) {
      bodyIndent = leading(lines[inner - 1]);
      break;
    }
  }
  return { line: end, replace: false, text: indentBlock(block, bodyIndent, unit) };
}

export function isInsertRefusal(plan: BlockInsertPlan | BlockInsertRefusal): plan is BlockInsertRefusal {
  return "refused" in plan;
}
