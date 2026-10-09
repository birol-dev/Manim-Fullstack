export type Quality = "l" | "m" | "h" | "k";
export type StorageMode = "disk" | "browser";
export type OutputKind = "video" | "image";

export interface ScriptFile {
  name: string;
  size: number;
  type: "script";
  /** A symbolic link to a file outside the workspace: it can only be deleted (only the link is removed). */
  outside?: boolean;
  /** A symbolic link that points nowhere: it can only be deleted. */
  broken?: boolean;
}

export interface AssetFile {
  name: string;
  size: number;
  type: "asset";
  url: string;
}

export interface MediaFile {
  name: string;
  size: number;
  type: OutputKind;
  url: string;
  /** Path relative to workspace/media, used for deletion. */
  path: string;
  script: string | null;
  scene: string;
  quality: string | null;
  /** Modification time, seconds since the epoch. */
  modified: number;
}

export interface WorkspaceFiles {
  scripts: ScriptFile[];
  assets: AssetFile[];
  media: MediaFile[];
}

export interface AnimationStep {
  type: "play" | "wait";
  label: string;
  line: number;
  /** Seconds when known; an expression string when computed at runtime. */
  duration?: number | string;
  /**
   * True when *duration* is the parser's guess from Manim's defaults (no explicit run_time),
   * or when the step sits in an if/elif/else or match/case branch inside a loop (only one
   * branch runs per pass, so its count is a guess).
   */
  estimated?: boolean;
  /**
   * A branch inside a loop that is not counted: the parser counts only the branch with the
   * most animations per pass. Left out of the totals and the execution order.
   */
  alternative?: boolean;
  /** Present for calls inside a for/while loop: total times the call runs, or null when unknown. */
  repeat?: number | null;
  /** Line of the outermost loop that repeats this call. */
  loop_line?: number;
  /** Enclosing loops, outermost first: [line, column, iterations or null when unknown]. */
  loops?: Array<[number, number, number | null]>;
}

export type SceneAnimations = Record<string, AnimationStep[]>;

export interface SyntaxErrorInfo {
  message: string;
  line: number;
  column: number;
}

export interface ParseResult {
  scenes: string[];
  animations: SceneAnimations;
  syntaxError?: SyntaxErrorInfo | null;
}

export interface Dependencies {
  manim: string;
  ffmpeg: string;
  latex: string;
  dvisvgm: string;
  latex_available: boolean;
}

export interface Diagnostics {
  platform?: string;
  python_version?: string;
  profile: "eco" | "balanced" | "workstation" | string;
  description: string;
  preview_quality: string;
  default_fps: number;
  default_resolution: string;
  recommended_threads: number;
  opengl_supported: boolean;
  /** Largest script the server accepts (MANIM_MAX_CODE_BYTES). */
  max_code_bytes?: number;
  hardware: {
    cpu: { model: string; physical_cores: number; logical_threads: number };
    ram_gb: number;
    gpu: { devices: Array<{ name: string; vram: string; type: string }>; has_cuda: boolean };
  };
  dependencies: Dependencies;
}

export type Dependency = "manim" | "latex" | "ffmpeg";

/** The current thing shown in the preview pane. */
export interface PreviewItem {
  url: string;
  kind: OutputKind;
  title: string;
  /** Workspace-relative location shown under the preview. */
  location: string;
  /** Media list entry, when the preview came from (or was saved to) the workspace. */
  mediaPath?: string;
  downloadName: string;
  /** The clip is from an earlier render that has since failed or produced nothing. */
  stale?: boolean;
  /** Script and scene the render came from, when known. The preview follows the open file. */
  file?: string;
  scene?: string;
}
