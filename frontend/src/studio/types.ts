/** Shapes of the /api/studio endpoints (see backend/studio/README.md). */

export type Aspect = "16:9" | "9:16" | "1:1" | "4:5";
export type Energy = "calm" | "normal" | "punchy";
export type Ending = "hold" | "fade" | "cut";
export type BackgroundKind = "theme" | "solid" | "gradient" | "transparent";
export type ExportFormat = "mp4" | "gif" | "webm" | "mov" | "png";
export type ExportQuality = "draft" | "720p" | "1080p" | "1080p60" | "4k";
export type PreviewMode = "poster" | "storyboard";

export interface ImageCropRecipe {
  source: string;
  position: { x: number; y: number; zoom: number };
  ratio: number;
  shape: string;
}

export interface ImageInfo {
  name: string;
  crop: ImageCropRecipe | null;
}

/** A JSON Schema node as produced by Pydantic, plus the studio's x-* hints. */
export interface JsonSchema {
  type?: string | string[];
  title?: string;
  description?: string;
  default?: unknown;
  enum?: unknown[];
  const?: unknown;
  properties?: Record<string, JsonSchema>;
  required?: string[];
  items?: JsonSchema;
  anyOf?: JsonSchema[];
  oneOf?: JsonSchema[];
  allOf?: JsonSchema[];
  $ref?: string;
  $defs?: Record<string, JsonSchema>;
  definitions?: Record<string, JsonSchema>;
  maxLength?: number;
  minLength?: number;
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
  exclusiveMaximum?: number;
  minItems?: number;
  maxItems?: number;
  "x-widget"?: string;
  "x-labels"?: Record<string, string>;
  "x-help"?: string;
  "x-option-help"?: Record<string, string>;
  "x-item-title"?: string;
  "x-placeholder"?: string;
  "x-unit"?: string;
  "x-step"?: number;
  "x-shape"?: string;
  "x-crop"?: string;
  "x-choice-of"?: string;
  [key: string]: unknown;
}

export interface Background {
  kind: BackgroundKind;
  color?: string | null;
  color2?: string | null;
}

export interface RenderSettings {
  aspect: Aspect;
  length?: number | null;
  theme: string;
  background: Background;
  energy: Energy;
  ending: Ending;
  safe_zone: boolean;
  locale: string;
  brand?: Record<string, unknown>;
}

export type Params = Record<string, unknown>;

export interface Card {
  id: string;
  template: string;
  title: string;
  summary: string;
  category: string;
  params: Params;
  settings: Partial<RenderSettings>;
  tags: string[];
  peek_url?: string | null;
}

export interface Section {
  id: string;
  title: string;
  cards: Card[];
}

export interface TemplateInfo {
  id: string;
  version: number;
  title: string;
  summary: string;
  category: string;
  aspects: Aspect[];
  default_aspect: Aspect;
  min_length: number;
  max_length: number;
  default_length: number;
  loopable: boolean;
  export_fps?: number | null;
  length_from_params: boolean;
  tags: string[];
  schema: JsonSchema;
  defaults: Params;
  presets: Card[];
}

export interface Theme {
  id: string;
  name: string;
  dark: boolean;
  bg: string;
  text: string;
  accent: string[];
}

export interface Catalog {
  sections: Section[];
  templates: TemplateInfo[];
  themes?: Theme[];
  aspects?: unknown;
  qualities?: unknown;
}

export interface StoryboardInfo {
  frames: number;
  columns: number;
  times: number[];
  frame_size?: unknown;
  length: number;
}

export interface PreviewRequest {
  template: string;
  params: Params;
  settings: Partial<RenderSettings>;
  mode: PreviewMode;
}

export interface PreviewResponse {
  url: string;
  mode: PreviewMode;
  width: number;
  height: number;
  cached?: boolean;
  ms?: number;
  storyboard?: StoryboardInfo;
}

export interface MotionPreview {
  id: string;
  status: "queued" | "rendering" | "done" | "failed" | "cancelled";
  url?: string;
  duration?: number;
  truncated?: boolean;
  error?: string;
}

export type ExportStatus = "queued" | "rendering" | "done" | "failed" | "cancelled";

export interface ExportJob {
  id: string;
  template: string;
  title?: string | null;
  format: ExportFormat;
  quality: ExportQuality;
  status: ExportStatus;
  progress: number | null;
  message?: string | null;
  /** Measured frame throughput estimate; absent until enough frames have finished. */
  time_left?: string | null;
  phase?: "drawing" | "finishing" | "done";
  rendered_frames?: number;
  total_frames?: number;
  url?: string | null;
  filename?: string | null;
  size?: number | null;
  duration?: number | null;
  error?: string | null;
  created: number | string;
}

export interface ProjectSummary {
  id: string;
  title: string;
  template: string;
  updated: number | string;
  poster_url?: string | null;
}

export interface Project {
  id: string;
  title: string;
  template: string;
  params: Params;
  settings: Partial<RenderSettings>;
  created: number | string;
  updated: number | string;
}

export interface FieldError {
  field: string;
  message: string;
}
