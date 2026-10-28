/**
 * Turns a template's JSON Schema (Pydantic output with x-widget hints) into form field specs.
 * Pure functions only, so the mapping is easy to test.
 */
import type { JsonSchema, Params } from "./types";

export type WidgetKind =
  | "text"
  | "textarea"
  | "number"
  | "integer"
  | "duration"
  | "choice"
  | "toggle"
  | "color"
  | "image"
  | "icon"
  | "list"
  | "table"
  | "json";

const KNOWN_WIDGETS = new Set<WidgetKind>([
  "text",
  "textarea",
  "number",
  "integer",
  "duration",
  "choice",
  "toggle",
  "color",
  "image",
  "icon",
  "list",
  "table",
]);

export interface FieldSpec {
  key: string;
  widget: WidgetKind;
  title: string;
  description?: string;
  required: boolean;
  /** null is allowed (optional image, icon, color). */
  nullable: boolean;
  /** The JSON type after unwrapping refs and `anyOf: [X, null]`. */
  type?: string;
  default?: unknown;
  options?: Array<{ value: string; label: string }>;
  maxLength?: number;
  minimum?: number;
  maximum?: number;
  step?: number;
  unit?: string;
  placeholder?: string;
  minItems?: number;
  maxItems?: number;
  itemTitle?: string;
  /** Fields of one list/table row. */
  itemFields?: FieldSpec[];
  shape?: string;
  /** The description says `*word*` highlights words. */
  emphasis?: boolean;
}

type Defs = Record<string, JsonSchema>;

/** Follow a local `$ref` (`#/$defs/Name`). */
export function resolveRef(node: JsonSchema | undefined, defs: Defs): JsonSchema {
  let current: JsonSchema = node ?? {};
  for (let depth = 0; depth < 10 && current.$ref; depth += 1) {
    const name = current.$ref.split("/").pop() ?? "";
    const { $ref: _ref, ...rest } = current;
    void _ref;
    current = { ...(defs[name] ?? {}), ...rest };
  }
  // Older Pydantic wraps a ref with extra keys in allOf: [{$ref}].
  if (current.allOf?.length === 1 && !current.type) {
    const { allOf, ...rest } = current;
    return { ...resolveRef(allOf[0], defs), ...rest };
  }
  return current;
}

/** `anyOf: [X, {type: null}]` → X plus nullable. Keeps the outer title/description/x-* keys. */
export function unwrapNullable(node: JsonSchema, defs: Defs): { schema: JsonSchema; nullable: boolean } {
  const variants = node.anyOf ?? node.oneOf;
  if (variants?.length) {
    const nonNull = variants.filter((variant) => variant.type !== "null");
    const nullable = nonNull.length < variants.length;
    if (nonNull.length === 1) {
      const { anyOf: _a, oneOf: _o, ...outer } = node;
      void _a;
      void _o;
      return { schema: { ...resolveRef(nonNull[0], defs), ...outer }, nullable };
    }
    return { schema: node, nullable };
  }
  if (Array.isArray(node.type)) {
    const types = node.type.filter((type) => type !== "null");
    return { schema: { ...node, type: types.length === 1 ? types[0] : node.type }, nullable: types.length < node.type.length };
  }
  return { schema: node, nullable: false };
}

function primaryType(schema: JsonSchema): string | undefined {
  if (typeof schema.type === "string") return schema.type;
  if (schema.enum?.length) return typeof schema.enum[0] === "number" ? "number" : "string";
  if (schema.properties) return "object";
  return undefined;
}

/** The widget for a field: its x-widget when known, else a fallback by JSON type. */
export function widgetFor(schema: JsonSchema, type: string | undefined, items?: JsonSchema): WidgetKind {
  const hint = schema["x-widget"];
  if (typeof hint === "string" && KNOWN_WIDGETS.has(hint as WidgetKind)) return hint as WidgetKind;
  if (schema.enum?.length) return "choice";
  switch (type) {
    case "boolean":
      return "toggle";
    case "integer":
      return "integer";
    case "number":
      return "number";
    case "string":
      return "text";
    case "array":
      return items && (items.properties || primaryType(items) === "object") ? "list" : "json";
    default:
      return "json";
  }
}

function emphasisHint(description: string | undefined) {
  return !!description && /\*[^*\s][^*]*\*|\bstars?\b|asterisk/i.test(description);
}

function choiceOptions(schema: JsonSchema): FieldSpec["options"] {
  const labels = schema["x-labels"] ?? {};
  return (schema.enum ?? []).map((value) => {
    const key = String(value);
    return { value: key, label: labels[key] ?? key.charAt(0).toUpperCase() + key.slice(1).replace(/[_-]/g, " ") };
  });
}

function humanize(key: string) {
  const words = key.replace(/[_-]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function fieldSpec(key: string, raw: JsonSchema, defs: Defs, required: boolean): FieldSpec {
  const { schema, nullable } = unwrapNullable(resolveRef(raw, defs), defs);
  const type = primaryType(schema);
  const items = schema.items ? resolveRef(schema.items, defs) : undefined;
  const widget = widgetFor(schema, type, items);
  const spec: FieldSpec = {
    key,
    widget,
    title: schema.title || humanize(key),
    description: schema.description,
    required,
    nullable,
    type,
    default: schema.default,
  };
  if (widget === "choice") spec.options = choiceOptions(schema);
  if (typeof schema.maxLength === "number") spec.maxLength = schema.maxLength;
  const minimum = schema.minimum ?? schema.exclusiveMinimum;
  const maximum = schema.maximum ?? schema.exclusiveMaximum;
  if (typeof minimum === "number") spec.minimum = minimum;
  if (typeof maximum === "number") spec.maximum = maximum;
  if (typeof schema["x-step"] === "number") spec.step = schema["x-step"];
  if (typeof schema["x-unit"] === "string") spec.unit = schema["x-unit"];
  if (typeof schema["x-placeholder"] === "string") spec.placeholder = schema["x-placeholder"];
  if (typeof schema["x-shape"] === "string") spec.shape = schema["x-shape"];
  if (widget === "list" || widget === "table") {
    spec.minItems = schema.minItems;
    spec.maxItems = schema.maxItems;
    spec.itemTitle = schema["x-item-title"] || "Item";
    spec.itemFields = items ? fieldsOf(items, defs) : [];
  }
  if ((widget === "text" || widget === "textarea") && emphasisHint(schema.description)) spec.emphasis = true;
  return spec;
}

/** Form fields for an object schema, in declaration order. */
export function fieldsOf(schema: JsonSchema, defs: Defs = schema.$defs ?? schema.definitions ?? {}): FieldSpec[] {
  const resolved = resolveRef(schema, defs);
  const required = new Set(resolved.required ?? []);
  return Object.entries(resolved.properties ?? {}).map(([key, prop]) => fieldSpec(key, prop, defs, required.has(key)));
}

function clone<T>(value: T): T {
  return value === undefined ? value : (JSON.parse(JSON.stringify(value)) as T);
}

/** An empty value for a field (a new list row uses these). */
export function emptyValue(field: FieldSpec): unknown {
  if (field.default !== undefined) return clone(field.default);
  if (field.nullable) return null;
  switch (field.widget) {
    case "toggle":
      return false;
    case "number":
    case "integer":
    case "duration":
      return field.minimum ?? 0;
    case "choice":
      return field.options?.[0]?.value ?? "";
    case "list":
    case "table":
      return Array.from({ length: field.minItems ?? 0 }, () => newItem(field.itemFields ?? []));
    case "json":
      return field.type === "array" ? [] : field.type === "object" ? {} : "";
    default:
      return "";
  }
}

export function newItem(fields: FieldSpec[]): Params {
  return Object.fromEntries(fields.map((field) => [field.key, emptyValue(field)]));
}

/** Template defaults, then the card's (or project's) params on top. */
export function initialParams(defaults: Params | undefined, overrides: Params | undefined): Params {
  return { ...clone(defaults ?? {}), ...clone(overrides ?? {}) };
}

/** Every value path a form shows (params.title, params.items.0.value, ...), for error matching. */
export function fieldPaths(fields: FieldSpec[], values: Params, prefix = "params"): string[] {
  const paths: string[] = [];
  for (const field of fields) {
    const path = `${prefix}.${field.key}`;
    paths.push(path);
    if ((field.widget === "list" || field.widget === "table") && Array.isArray(values[field.key])) {
      (values[field.key] as Params[]).forEach((item, index) => {
        paths.push(`${path}.${index}`);
        paths.push(...fieldPaths(field.itemFields ?? [], item ?? {}, `${path}.${index}`));
      });
    }
  }
  return paths;
}

export function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds)) return "";
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  const ss = String(secs).padStart(2, "0");
  return hours ? `${hours}:${String(minutes).padStart(2, "0")}:${ss}` : `${minutes}:${ss}`;
}

/** "5:00", "1:02:03", "90", "90s", "5m", "1m 30s", "1,5 min" → seconds, or null. */
export function parseDuration(text: string): number | null {
  const value = text.trim().toLowerCase();
  if (!value) return null;
  if (/^\d+(:\d{1,2}){1,2}$/.test(value)) {
    return value.split(":").reduce((total, part) => total * 60 + Number(part), 0);
  }
  const units = /^(?:(\d+(?:[.,]\d+)?)\s*h)?\s*(?:(\d+(?:[.,]\d+)?)\s*m(?:in)?)?\s*(?:(\d+(?:[.,]\d+)?)\s*s(?:ec)?)?$/.exec(value);
  if (units && (units[1] || units[2] || units[3])) {
    const num = (part?: string) => (part ? Number(part.replace(",", ".")) : 0);
    return num(units[1]) * 3600 + num(units[2]) * 60 + num(units[3]);
  }
  if (/^\d+(?:[.,]\d+)?$/.test(value)) return Number(value.replace(",", "."));
  return null;
}
