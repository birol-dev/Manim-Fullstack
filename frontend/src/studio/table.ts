/** Spreadsheet helpers for the table widget: pasted rows and locale-formatted numbers. */
import type { FieldSpec } from "./schemaForm";
import type { Params } from "./types";

/** Locales that write 1.234,5 (comma decimals). Everything else is read as 1,234.5. */
const COMMA_DECIMAL = new Set(["tr", "de", "fr", "es", "it", "pt", "nl", "pl", "ru", "sv", "da", "nb", "fi", "cs", "id", "ro", "hu", "el", "uk"]);

export function usesCommaDecimal(locale: string | undefined): boolean {
  return COMMA_DECIMAL.has((locale ?? "en").slice(0, 2).toLowerCase());
}

/**
 * A number as people type or paste it: "1,234.5", "1.234,5", "1 234,5", "12%", "$ 9.99", "(5)", "−3".
 * A lone separator followed by exactly three digits ("1,234", "1.234") is a thousands
 * separator unless the locale writes decimals that way. Returns null when it isn't a number.
 */
export function parseLocaleNumber(input: string | number | null | undefined, locale = "en"): number | null {
  if (typeof input === "number") return Number.isFinite(input) ? input : null;
  if (input == null) return null;
  let text = String(input).trim();
  if (!text) return null;
  let negative = false;
  if (/^\(.*\)$/.test(text)) {
    negative = true;
    text = text.slice(1, -1);
  }
  // Currency, percent and spaces (incl. no-break and thin spaces) and Swiss apostrophes.
  text = text.replace(/[\s\u00a0\u202f'\u2019]/g, "").replace(/[%$\u20ac\u00a3\u00a5\u20ba\u20b9]|TL|EUR|USD/gi, "");
  text = text.replace(/^[\u2212\u2013]/, "-");
  if (text.startsWith("-")) {
    negative = !negative;
    text = text.slice(1);
  } else if (text.startsWith("+")) {
    text = text.slice(1);
  }
  if (!/^[\d.,]+$/.test(text) || !/\d/.test(text)) return null;

  const commas = (text.match(/,/g) ?? []).length;
  const dots = (text.match(/\./g) ?? []).length;
  let normalized: string;
  if (commas && dots) {
    const decimal = text.lastIndexOf(",") > text.lastIndexOf(".") ? "," : ".";
    const thousands = decimal === "," ? "." : ",";
    if ((decimal === "," ? commas : dots) > 1) return null;
    normalized = text.split(thousands).join("").replace(decimal, ".");
  } else if (commas || dots) {
    const sep = commas ? "," : ".";
    const count = commas || dots;
    const groups = text.split(sep);
    if (count > 1) {
      // Several of one separator can only group thousands: 1,234,567 / 1.234.567.
      if (!groups.slice(1).every((group) => group.length === 3) || !groups[0]) return null;
      normalized = groups.join("");
    } else {
      const [whole, fraction] = groups;
      const looksGrouped = fraction.length === 3 && whole.length >= 1 && whole.length <= 3 && whole !== "0";
      const localeDecimal = usesCommaDecimal(locale) ? "," : ".";
      if (looksGrouped && sep !== localeDecimal) normalized = whole + fraction;
      else normalized = `${whole || "0"}.${fraction}`;
    }
  } else {
    normalized = text;
  }
  const value = Number(normalized);
  if (!Number.isFinite(value)) return null;
  return negative ? -value : value;
}

/** Tab-separated text (what Excel, Numbers and Google Sheets put on the clipboard) → rows of cells. */
export function parseTsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  const source = text.replace(/\r\n?/g, "\n");
  for (let i = 0; i < source.length; i += 1) {
    const ch = source[i];
    if (quoted) {
      if (ch === '"') {
        if (source[i + 1] === '"') {
          cell += '"';
          i += 1;
        } else {
          quoted = false;
        }
      } else {
        cell += ch;
      }
    } else if (ch === '"' && cell === "") {
      quoted = true;
    } else if (ch === "\t") {
      row.push(cell);
      cell = "";
    } else if (ch === "\n") {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
    } else {
      cell += ch;
    }
  }
  if (cell !== "" || row.length) {
    row.push(cell);
    rows.push(row);
  }
  // Spreadsheets end the copy with a newline; drop fully empty trailing rows.
  while (rows.length && rows[rows.length - 1].every((value) => value.trim() === "")) rows.pop();
  return rows.map((cells) => cells.map((value) => value.trim()));
}

/** Clipboard text that is more than one cell. */
export function isMultiCell(text: string): boolean {
  const trimmed = text.replace(/\r?\n$/, "");
  return trimmed.includes("\t") || trimmed.includes("\n");
}

const isNumeric = (field: FieldSpec) => field.widget === "number" || field.widget === "integer" || field.widget === "duration";

/** Convert one pasted cell for its column; undefined means "can't use this". */
export function cellValue(field: FieldSpec, raw: string, locale: string): unknown {
  if (isNumeric(field)) {
    const number = parseLocaleNumber(raw, locale);
    if (number === null) return raw.trim() === "" && field.nullable ? null : undefined;
    if (field.widget === "integer" && !Number.isInteger(number)) return undefined;
    return number;
  }
  if (field.widget === "toggle") {
    const value = raw.trim().toLowerCase();
    if (["1", "yes", "true", "y", "x", "✓", "evet", "ja", "oui", "sí", "si"].includes(value)) return true;
    if (["0", "no", "false", "n", "", "hayır", "nein", "non"].includes(value)) return false;
    return undefined;
  }
  if (field.widget === "choice") {
    const value = raw.trim().toLowerCase();
    const match = field.options?.find((option) => option.value.toLowerCase() === value || option.label.toLowerCase() === value);
    return match ? match.value : undefined;
  }
  if (field.nullable && raw.trim() === "") return null;
  const text = raw.trim();
  return field.maxLength ? text.slice(0, field.maxLength) : text;
}

/**
 * A first pasted row that is a header: its cells match the column titles, or it has text where
 * the next row has numbers.
 */
export function looksLikeHeader(rows: string[][], columns: FieldSpec[], locale: string): boolean {
  if (rows.length < 2) return false;
  const [first, second] = rows;
  const titles = columns.map((column) => column.title.trim().toLowerCase());
  const keys = columns.map((column) => column.key.toLowerCase());
  if (first.some((cell) => cell && (titles.includes(cell.toLowerCase()) || keys.includes(cell.toLowerCase())))) return true;
  return columns.some(
    (column, index) =>
      isNumeric(column) &&
      first[index] !== undefined &&
      first[index] !== "" &&
      parseLocaleNumber(first[index], locale) === null &&
      parseLocaleNumber(second[index] ?? "", locale) !== null,
  );
}

export interface PasteResult {
  rows: Params[];
  /** Cells that couldn't be used (wrong type), as "row 2, Value". */
  skipped: string[];
  /** Pasted rows beyond the table's limit. */
  dropped: number;
  /** Pasted rows that went into the table. */
  pasted: number;
  /** The first pasted row was a header and was left out. */
  header: boolean;
}

/**
 * Paste *text* into *rows* at (row, column): fills cells to the right and below, adds rows as
 * needed (up to maxItems), converts numbers with the locale and skips a header row.
 */
export function pasteIntoRows(
  rows: Params[],
  columns: FieldSpec[],
  text: string,
  at: { row: number; column: number },
  options: { locale: string; maxItems?: number; makeRow: () => Params },
): PasteResult {
  let grid = parseTsv(text);
  const header = at.row === 0 && at.column === 0 && looksLikeHeader(grid, columns, options.locale);
  if (header) grid = grid.slice(1);
  const next = rows.map((row) => ({ ...row }));
  const skipped: string[] = [];
  const max = options.maxItems ?? Infinity;
  let dropped = 0;
  grid.forEach((cells, offset) => {
    const target = at.row + offset;
    if (target >= max) {
      dropped += 1;
      return;
    }
    while (next.length <= target) next.push(options.makeRow());
    cells.forEach((raw, columnOffset) => {
      const column = columns[at.column + columnOffset];
      if (!column) return;
      const value = cellValue(column, raw, options.locale);
      if (value === undefined) skipped.push(`row ${target + 1}, ${column.title}`);
      else next[target][column.key] = value;
    });
  });
  return { rows: next, skipped, dropped, pasted: grid.length - dropped, header };
}

/** A number for display in a table cell, in the video's locale. */
export function formatCellNumber(value: unknown, locale: string): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return value == null ? "" : String(value);
  try {
    return new Intl.NumberFormat(locale, { maximumFractionDigits: 6, useGrouping: false }).format(value);
  } catch {
    return String(value);
  }
}
