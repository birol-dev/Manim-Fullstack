import type { Catalog, JsonSchema, TemplateInfo } from "../types";

/** The countdown template's schema as the backend produces it (registry.catalog()). */
export const COUNTDOWN_SCHEMA: JsonSchema = {
  additionalProperties: false,
  properties: {
    seconds: {
      default: 300,
      description: "How long the timer runs, in seconds (5 minutes = 300).",
      maximum: 3600,
      minimum: 3,
      title: "Timer length",
      type: "number",
      "x-widget": "duration",
    },
    title: {
      default: "Quiet reading time",
      description: "What the time is for. Leave empty for no title.",
      maxLength: 60,
      title: "Title",
      type: "string",
      "x-widget": "text",
    },
    style: {
      default: "ring",
      enum: ["ring", "bar", "big"],
      title: "Style",
      type: "string",
      "x-labels": { bar: "Progress bar", big: "Big numbers", ring: "Ring" },
      "x-widget": "choice",
    },
    warn_last: { default: true, title: "Highlight the last 10 seconds", type: "boolean", "x-widget": "toggle" },
    accent: {
      anyOf: [{ type: "string" }, { type: "null" }],
      default: null,
      description: "Leave empty to use the theme color.",
      title: "Timer color",
      "x-widget": "color",
    },
  },
  title: "Params",
  type: "object",
};

/** A made-up template using the other widgets: lists, tables, images, icons, textarea. */
export const CHART_SCHEMA: JsonSchema = {
  $defs: {
    Bar: {
      additionalProperties: false,
      properties: {
        label: { default: "", maxLength: 24, title: "Label", type: "string", "x-widget": "text" },
        value: { default: 0, title: "Value", type: "number", "x-widget": "number" },
        highlight: { default: false, title: "Highlight", type: "boolean", "x-widget": "toggle" },
      },
      title: "Bar",
      type: "object",
    },
    Point: {
      additionalProperties: false,
      properties: {
        text: { title: "Text", type: "string", maxLength: 40 },
        icon: { anyOf: [{ type: "string" }, { type: "null" }], default: null, title: "Icon", "x-widget": "icon" },
      },
      required: ["text"],
      title: "Point",
      type: "object",
    },
  },
  properties: {
    headline: {
      default: "Our *best* year",
      description: "Put *stars* around words to highlight them.",
      maxLength: 80,
      title: "Headline",
      type: "string",
      "x-widget": "textarea",
    },
    bars: {
      default: [
        { label: "2023", value: 10, highlight: false },
        { label: "2024", value: 20, highlight: true },
      ],
      items: { $ref: "#/$defs/Bar" },
      maxItems: 4,
      minItems: 1,
      title: "Bars",
      type: "array",
      "x-item-title": "Bar",
      "x-widget": "table",
    },
    points: {
      default: [{ text: "Fast", icon: "clock" }],
      items: { $ref: "#/$defs/Point" },
      maxItems: 3,
      minItems: 1,
      title: "Points",
      type: "array",
      "x-item-title": "Point",
      "x-widget": "list",
    },
    logo: {
      anyOf: [{ type: "string" }, { type: "null" }],
      default: null,
      title: "Logo",
      "x-shape": "logo",
      "x-widget": "image",
    },
    count: { default: 3, title: "How many", type: "integer", minimum: 1, maximum: 9 },
    mood: { default: "a", enum: ["a", "b", "c", "d", "e"], title: "Mood", type: "string" },
    fancy: { default: 2.5, title: "Fancy", type: "number", "x-widget": "sparkle", "x-unit": "kg", "x-step": 0.5 },
  },
  required: ["bars"],
  title: "Params",
  type: "object",
};

function template(id: string, schema: JsonSchema, extra: Partial<TemplateInfo>): TemplateInfo {
  return {
    id,
    version: 1,
    title: id,
    summary: "",
    category: "timers",
    aspects: ["16:9", "9:16", "1:1", "4:5"],
    default_aspect: "16:9",
    min_length: 3,
    max_length: 60,
    default_length: 8,
    loopable: false,
    length_from_params: false,
    tags: [],
    schema,
    defaults: {},
    presets: [],
    ...extra,
  };
}

export const CATALOG: Catalog = {
  sections: [
    {
      id: "timers",
      title: "Timers & countdowns",
      cards: [
        {
          id: "classroom-timer",
          template: "countdown",
          title: "Classroom timer",
          summary: "5 minutes with a calm ring.",
          category: "timers",
          params: { seconds: 300, title: "Quiet reading time", style: "ring" },
          settings: { theme: "clean", energy: "calm" },
          tags: [],
        },
        {
          id: "launch-countdown",
          template: "countdown",
          title: "10…1 countdown",
          summary: "Big numbers for a launch or New Year.",
          category: "timers",
          params: { seconds: 10, title: "", style: "big" },
          settings: { theme: "pop" },
          tags: [],
        },
      ],
    },
    {
      id: "numbers",
      title: "Show numbers",
      cards: [
        {
          id: "sales",
          template: "chart",
          title: "Sales chart",
          summary: "Bars that grow.",
          category: "numbers",
          params: {},
          settings: {},
          tags: ["bars", "revenue"],
        },
      ],
    },
  ],
  templates: [
    template("countdown", COUNTDOWN_SCHEMA, {
      title: "Countdown timer",
      tags: ["timer", "classroom"],
      length_from_params: true,
      min_length: 5,
      max_length: 3600,
      default_length: 300,
      defaults: { seconds: 300, title: "Quiet reading time", style: "ring", warn_last: true, accent: null },
      presets: [],
    }),
    template("chart", CHART_SCHEMA, {
      title: "Bar chart",
      category: "numbers",
      defaults: {
        headline: "Our *best* year",
        bars: [
          { label: "2023", value: 10, highlight: false },
          { label: "2024", value: 20, highlight: true },
        ],
        points: [{ text: "Fast", icon: "clock" }],
        logo: null,
        count: 3,
        mood: "a",
        fancy: 2.5,
      },
    }),
  ],
  themes: [
    { id: "clean", name: "Clean light", dark: false, bg: "#F6F5F2", text: "#16181D", accent: ["#2563EB", "#F97316", "#10B981", "#E11D48", "#8B5CF6"] },
    { id: "pop", name: "Bold pop", dark: false, bg: "#FFD84D", text: "#111111", accent: ["#FF3D7F", "#1E40FF", "#00B37E", "#111111", "#FF7A00"] },
  ],
};
CATALOG.templates[0].presets = CATALOG.sections[0].cards;
CATALOG.templates[1].presets = CATALOG.sections[1].cards;
