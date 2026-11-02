import { describe, expect, it } from "vitest";

import { fieldsOf, newItem } from "./schemaForm";
import { cellValue, isMultiCell, looksLikeHeader, parseLocaleNumber, parseTsv, pasteIntoRows } from "./table";
import { CHART_SCHEMA } from "./test/fixtures";

const columns = fieldsOf(CHART_SCHEMA).find((field) => field.key === "bars")!.itemFields!;
const makeRow = () => newItem(columns);

describe("parseLocaleNumber", () => {
  it.each([
    ["1,234.5", "en", 1234.5],
    ["1.234,5", "en", 1234.5],
    ["1.234,5", "de", 1234.5],
    ["1,234.5", "tr", 1234.5],
    ["1 234,5", "fr", 1234.5],
    ["1 234,5", "fr", 1234.5],
    ["1'234.5", "en", 1234.5],
    ["1,234,567", "en", 1234567],
    ["1.234.567", "de", 1234567],
    ["12,5", "en", 12.5],
    ["12.5", "de", 12.5],
    ["0,75", "en", 0.75],
    ["42", "en", 42],
    ["-3,5", "de", -3.5],
    ["−3.5", "en", -3.5],
    ["(12)", "en", -12],
    ["12%", "en", 12],
    ["$ 9.99", "en", 9.99],
    ["€1.234,50", "de", 1234.5],
    ["+7", "en", 7],
  ])("%s (%s) → %s", (input, locale, expected) => {
    expect(parseLocaleNumber(input, locale)).toBe(expected);
  });

  it("reads a lone separator before three digits by the locale", () => {
    expect(parseLocaleNumber("1,234", "en")).toBe(1234);
    expect(parseLocaleNumber("1,234", "de")).toBe(1.234);
    expect(parseLocaleNumber("1.234", "en")).toBe(1.234);
    expect(parseLocaleNumber("1.234", "tr")).toBe(1234);
    expect(parseLocaleNumber("0,123", "en")).toBe(0.123);
  });

  it("refuses things that aren't numbers", () => {
    for (const input of ["", "  ", "abc", "1,2,3", "1.2.3,4,5", "12a", "--1", null, undefined]) {
      expect(parseLocaleNumber(input as string, "en")).toBeNull();
    }
    expect(parseLocaleNumber(5, "en")).toBe(5);
    expect(parseLocaleNumber(Number.NaN, "en")).toBeNull();
  });
});

describe("parseTsv", () => {
  it("splits spreadsheet clipboard text into rows and cells", () => {
    expect(parseTsv("a\tb\r\nc\td\r\n")).toEqual([
      ["a", "b"],
      ["c", "d"],
    ]);
    expect(parseTsv("one\n\ntwo\n\n\n")).toEqual([["one"], [""], ["two"]]);
  });

  it("keeps quoted cells with tabs, newlines and quotes", () => {
    expect(parseTsv('"Line 1\nLine 2"\t"say ""hi"""\nx\t"a\tb"')).toEqual([
      ["Line 1\nLine 2", 'say "hi"'],
      ["x", "a\tb"],
    ]);
  });

  it("tells one cell from several", () => {
    expect(isMultiCell("hello")).toBe(false);
    expect(isMultiCell("hello\n")).toBe(false);
    expect(isMultiCell("a\tb")).toBe(true);
    expect(isMultiCell("a\nb")).toBe(true);
  });
});

describe("pasting into a table", () => {
  it("fills cells, adds rows and converts numbers with the locale", () => {
    const rows = [{ label: "x", value: 1, highlight: false }];
    const result = pasteIntoRows(rows, columns, "Q1\t1.234,5\tyes\nQ2\t2.000\tno\nQ3\t7\t", { row: 0, column: 0 }, { locale: "de", makeRow });
    expect(result.rows).toEqual([
      { label: "Q1", value: 1234.5, highlight: true },
      { label: "Q2", value: 2000, highlight: false },
      { label: "Q3", value: 7, highlight: false },
    ]);
    expect(result).toMatchObject({ skipped: [], dropped: 0, pasted: 3, header: false });
    expect(rows[0].label).toBe("x"); // the input isn't changed
  });

  it("skips a header row and respects maxItems", () => {
    const text = "Label\tValue\n2021\t1,000.5\n2022\t2,000\n2023\t3\n2024\t4\n2025\t5";
    const result = pasteIntoRows([], columns, text, { row: 0, column: 0 }, { locale: "en", maxItems: 4, makeRow });
    expect(result.header).toBe(true);
    expect(result.rows.map((row) => row.value)).toEqual([1000.5, 2000, 3, 4]);
    expect(result.dropped).toBe(1);
    expect(result.pasted).toBe(4);
  });

  it("detects a header by text above numbers", () => {
    expect(looksLikeHeader([["Year", "Total"], ["2021", "12"]], columns, "en")).toBe(true);
    expect(looksLikeHeader([["2020", "11"], ["2021", "12"]], columns, "en")).toBe(false);
    expect(looksLikeHeader([["only row", "x"]], columns, "en")).toBe(false);
  });

  it("starts at the pasted cell and reports cells it can't use", () => {
    const rows = [
      { label: "a", value: 1, highlight: false },
      { label: "b", value: 2, highlight: false },
    ];
    const result = pasteIntoRows(rows, columns, "9\tmaybe\tignored\nlots\ttrue", { row: 1, column: 1 }, { locale: "en", makeRow });
    expect(result.rows).toEqual([
      { label: "a", value: 1, highlight: false },
      { label: "b", value: 9, highlight: false },
      { label: "", value: 0, highlight: true },
    ]);
    expect(result.skipped).toEqual(["row 2, Highlight", "row 3, Value"]);
  });

  it("converts single cells by column type", () => {
    const [label, value, highlight] = columns;
    expect(cellValue(label, "  a very long label that is longer than allowed  ", "en")).toHaveLength(24);
    expect(cellValue(value, "1.5", "en")).toBe(1.5);
    expect(cellValue(value, "x", "en")).toBeUndefined();
    expect(cellValue(highlight, "Evet", "tr")).toBe(true);
    const mood = fieldsOf(CHART_SCHEMA).find((field) => field.key === "mood")!;
    expect(cellValue(mood, "C", "en")).toBe("c");
    expect(cellValue(mood, "z", "en")).toBeUndefined();
  });
});
