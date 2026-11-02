import { readPreference, RECENT_COLORS_KEY, writePreference } from "./preferences";

export { RECENT_COLORS_KEY };

export function parseHex(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const hex = value.trim().replace(/^#/, "");
  if (/^[0-9a-f]{3}$/i.test(hex)) return `#${[...hex].map((n) => n + n).join("").toUpperCase()}`;
  return /^[0-9a-f]{6}$/i.test(hex) ? `#${hex.toUpperCase()}` : null;
}
export const clamp = (n: number, min = 0, max = 1) => Math.min(max, Math.max(min, n));
export interface HSV { h: number; s: number; v: number }
export function hexToHsv(hex: string): HSV {
  const [r, g, b] = [1, 3, 5].map((n) => parseInt(hex.slice(n, n + 2), 16) / 255);
  const v = Math.max(r, g, b), min = Math.min(r, g, b), d = v - min;
  const h = !d ? 0 : v === r ? ((g - b) / d + 6) % 6 : v === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return { h: h * 60, s: v ? d / v : 0, v };
}
export function hsvToHex({ h, s, v }: HSV): string {
  const c = v * s, x = c * (1 - Math.abs((h / 60) % 2 - 1)), m = v - c;
  const parts = h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x] : h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x];
  return `#${parts.map((p) => Math.round((p + m) * 255).toString(16).padStart(2, "0")).join("").toUpperCase()}`;
}
export function readRecentColors(): string[] {
  const stored = readPreference("recent_colors");
  return Array.isArray(stored)
    ? [...new Set(stored.map(parseHex).filter((c): c is string => c !== null))].slice(0, 8)
    : [];
}
export function rememberColor(value: string): string[] {
  const color = parseHex(value);
  const recent = readRecentColors();
  if (!color) return recent;
  const next = [color, ...recent.filter((c) => c !== color)].slice(0, 8);
  writePreference("recent_colors", next);
  return next;
}
