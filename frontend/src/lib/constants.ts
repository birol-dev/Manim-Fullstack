import type { Quality } from "./types";

export const QUALITY_OPTIONS: ReadonlyArray<{ value: Quality; label: string; detail: string }> = [
  { value: "l", label: "Low", detail: "480p · 15 fps" },
  { value: "m", label: "Medium", detail: "720p · 30 fps" },
  { value: "h", label: "High", detail: "1080p · 60 fps" },
  { value: "k", label: "4K", detail: "2160p · 60 fps" },
];

export const QUALITY_FOR_PROFILE: Record<string, Quality> = {
  eco: "l",
  balanced: "m",
  workstation: "h",
};

export const ALLOWED_ASSET_EXTENSIONS = [
  ".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp",
  ".mp3", ".wav", ".ogg", ".m4a",
  ".ttf", ".otf",
] as const;

export const MAX_ASSET_SIZE_BYTES = 50 * 1024 * 1024;
/** The backend's MANIM_MAX_CODE_BYTES default, used until the server reports its own. */
export const MAX_CODE_BYTES = 2 * 1024 * 1024;

let serverMaxCodeBytes: number | null = null;

/** Largest script the server accepts: its reported limit, or the default. */
export function getMaxCodeBytes(): number {
  return serverMaxCodeBytes ?? MAX_CODE_BYTES;
}

/** Record the limit from /api/diagnostics (`max_code_bytes`). Invalid values are ignored. */
export function setMaxCodeBytes(value: unknown): void {
  if (typeof value === "number" && Number.isSafeInteger(value) && value > 0) {
    serverMaxCodeBytes = value;
  }
}

/** "2 MB", "512 KB": the limit as people read it. */
export function formatByteLimit(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${Number((bytes / (1024 * 1024)).toFixed(1))} MB`;
  if (bytes >= 1024) return `${Number((bytes / 1024).toFixed(1))} KB`;
  return `${bytes} bytes`;
}

/** Manim's named colors with their hex values (manim.utils.color.manim_colors). */
export const MANIM_COLORS = [
  { name: "WHITE", hex: "#FFFFFF" },
  { name: "BLUE", hex: "#58C4DD" },
  { name: "TEAL", hex: "#5CD0B3" },
  { name: "GREEN", hex: "#83C167" },
  { name: "YELLOW", hex: "#F7D96F" },
  { name: "GOLD", hex: "#F0AC5F" },
  { name: "ORANGE", hex: "#FF862F" },
  { name: "RED", hex: "#FC6255" },
  { name: "MAROON", hex: "#C55F73" },
  { name: "PINK", hex: "#D147BD" },
  { name: "PURPLE", hex: "#9A72AC" },
  { name: "GREY", hex: "#888888" },
] as const;

export type ManimColorName = (typeof MANIM_COLORS)[number]["name"];

export const IS_MAC = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
export const MOD_KEY = IS_MAC ? "⌘" : "Ctrl";
