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
