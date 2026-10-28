import { describe, expect, it } from "vitest";

import { emptyValue, fieldPaths, fieldsOf, formatDuration, initialParams, newItem, parseDuration } from "./schemaForm";
import { CHART_SCHEMA, COUNTDOWN_SCHEMA } from "./test/fixtures";

const byKey = (schema: typeof CHART_SCHEMA) => Object.fromEntries(fieldsOf(schema).map((field) => [field.key, field]));

describe("schema → form widgets", () => {
  it("maps the countdown template's x-widget hints", () => {
    const fields = fieldsOf(COUNTDOWN_SCHEMA);
    expect(fields.map((field) => [field.key, field.widget])).toEqual([
      ["seconds", "duration"],
      ["title", "text"],
      ["style", "choice"],
      ["warn_last", "toggle"],
      ["accent", "color"],
    ]);
    const [seconds, title, style, , accent] = fields;
    expect(seconds).toMatchObject({ title: "Timer length", minimum: 3, maximum: 3600, default: 300 });
    expect(title).toMatchObject({ maxLength: 60, description: "What the time is for. Leave empty for no title." });
    expect(style.options).toEqual([
      { value: "ring", label: "Ring" },
      { value: "bar", label: "Progress bar" },
      { value: "big", label: "Big numbers" },
    ]);
    // anyOf [string, null] keeps the outer title and becomes nullable.
    expect(accent).toMatchObject({ nullable: true, type: "string", title: "Timer color", default: null });
  });

  it("resolves $defs refs for list and table items", () => {
    const fields = byKey(CHART_SCHEMA);
    expect(fields.bars).toMatchObject({ widget: "table", minItems: 1, maxItems: 4, itemTitle: "Bar", required: true });
    expect(fields.bars.itemFields?.map((field) => [field.key, field.widget])).toEqual([
      ["label", "text"],
      ["value", "number"],
      ["highlight", "toggle"],
    ]);
    expect(fields.points).toMatchObject({ widget: "list", itemTitle: "Point", required: false });
    const [text, icon] = fields.points.itemFields!;
    expect(text).toMatchObject({ widget: "text", required: true, maxLength: 40 });
    expect(icon).toMatchObject({ widget: "icon", nullable: true });
  });

  it("reads image shape, textarea emphasis, units and steps", () => {
    const fields = byKey(CHART_SCHEMA);
    expect(fields.logo).toMatchObject({ widget: "image", shape: "logo", nullable: true });
    expect(fields.headline).toMatchObject({ widget: "textarea", emphasis: true, maxLength: 80 });
    expect(fieldsOf(COUNTDOWN_SCHEMA).find((field) => field.key === "title")?.emphasis).toBeUndefined();
    expect(fields.fancy).toMatchObject({ unit: "kg", step: 0.5 });
  });

  it("falls back by JSON type for missing or unknown widgets", () => {
    const fields = byKey(CHART_SCHEMA);
    expect(fields.count.widget).toBe("integer");
    expect(fields.mood.widget).toBe("choice");
    expect(fields.mood.options?.[0]).toEqual({ value: "a", label: "A" });
    expect(fields.fancy.widget).toBe("number"); // x-widget "sparkle" is unknown
    const odd = fieldsOf({
      type: "object",
      properties: {
        flag: { type: "boolean" },
        name: { type: "string" },
        tags: { type: "array", items: { type: "string" } },
        rows: { type: "array", items: { type: "object", properties: { a: { type: "number" } } } },
        blob: { type: "object", properties: {} },
        old: { allOf: [{ $ref: "#/$defs/Kind" }], title: "Kind of thing" },
      },
      $defs: { Kind: { enum: ["x", "y"], type: "string" } },
    });
    expect(odd.map((field) => [field.key, field.widget])).toEqual([
      ["flag", "toggle"],
      ["name", "text"],
      ["tags", "json"],
      ["rows", "list"],
      ["blob", "json"],
      ["old", "choice"],
    ]);
    expect(odd[1].title).toBe("Name"); // humanized key when there is no title
    expect(odd[5].title).toBe("Kind of thing");
  });

  it("builds new rows and initial params from defaults", () => {
    const fields = byKey(CHART_SCHEMA);
    expect(newItem(fields.bars.itemFields!)).toEqual({ label: "", value: 0, highlight: false });
    expect(newItem(fields.points.itemFields!)).toEqual({ text: "", icon: null });
    expect(emptyValue({ key: "n", widget: "integer", title: "N", required: false, nullable: false, minimum: 2 })).toBe(2);
    const defaults = { a: 1, list: [{ x: 1 }] };
    const params = initialParams(defaults, { b: 2 });
    expect(params).toEqual({ a: 1, list: [{ x: 1 }], b: 2 });
    (params.list as Array<{ x: number }>)[0].x = 5;
    expect(defaults.list[0].x).toBe(1); // a copy, not the catalog's object
  });

  it("lists every value path, including rows", () => {
    const fields = fieldsOf(CHART_SCHEMA);
    const paths = fieldPaths(fields, { bars: [{}, {}], points: [{}] });
    expect(paths).toContain("params.headline");
    expect(paths).toContain("params.bars.1");
    expect(paths).toContain("params.bars.1.value");
    expect(paths).toContain("params.points.0.icon");
    expect(paths).not.toContain("params.bars.2.value");
  });
});

describe("durations", () => {
  it("formats seconds as m:ss", () => {
    expect(formatDuration(300)).toBe("5:00");
    expect(formatDuration(65)).toBe("1:05");
    expect(formatDuration(3725)).toBe("1:02:05");
    expect(formatDuration(9.6)).toBe("0:10");
  });

  it("parses what people type", () => {
    expect(parseDuration("5:00")).toBe(300);
    expect(parseDuration("1:30")).toBe(90);
    expect(parseDuration("1:02:05")).toBe(3725);
    expect(parseDuration("90")).toBe(90);
    expect(parseDuration("5m")).toBe(300);
    expect(parseDuration("1m 30s")).toBe(90);
    expect(parseDuration("1,5 min")).toBe(90);
    expect(parseDuration("")).toBeNull();
    expect(parseDuration("soon")).toBeNull();
  });
});
