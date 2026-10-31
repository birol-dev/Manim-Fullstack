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

/** One video's brand overrides; every field is optional and null means "use the template's own". */
export interface Brand {
  accent?: string | null;
  accent2?: string | null;
  font?: string | null;
  logo?: string | null;
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
  brand?: Brand;
  sound?: SoundSettings;
}

export interface MusicTrack { id: string; title: string; description: string; url: string }
export interface MusicSettings {
  track: string | null;
  asset: string | null;
  volume: number;
  fade_out: boolean;
  loop: boolean;
}
export interface SoundSettings { effects: boolean; effects_volume: number; music: MusicSettings }

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
  music_tracks?: MusicTrack[];
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
  finished?: number | string | null;
  /** Set on every export a "Make many" list queued; the Exports page groups by it. */
  batch_id?: string | null;
  batch_title?: string | null;
  batch_total?: number | null;
  /** The batch's own subfolder under the exports folder. */
  folder?: string | null;
}

export type BatchFieldKind = "text" | "number" | "color";

/** A simple top-level template field a spreadsheet column can fill. */
export interface BatchField {
  field: string;
  label: string;
  kind: BatchFieldKind;
  max_length?: number | null;
  required?: boolean;
}

export interface BatchCellProblem {
  field: string;
  label: string;
  message: string;
}

/** One row that cannot be made, in plain words; the rest of the list still runs. */
export interface BatchRowProblem {
  row: number;
  title: string;
  errors: BatchCellProblem[];
}

export interface ParsedBatch {
  headers: string[];
  rows: string[][];
  fields: BatchField[];
  suggested_mapping: Record<string, number>;
  suggested_title_column?: number | null;
  row_errors?: BatchRowProblem[];
  valid_rows?: number;
}

export interface BatchCounts {
  queued: number;
  rendering: number;
  done: number;
  failed: number;
  cancelled: number;
}

export interface BatchSummary {
  id: string;
  name: string;
  template: string;
  title: string;
  created: number | string;
  total: number;
  folder?: string | null;
  format?: string | null;
  quality?: string | null;
  row_errors?: BatchRowProblem[];
  counts: BatchCounts;
  cancelled?: number;
  retried?: string[];
  skipped?: string[];
}

export interface BatchCreated {
  batch_id: string;
  export_ids: string[];
  row_errors: BatchRowProblem[];
  batch: BatchSummary;
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
