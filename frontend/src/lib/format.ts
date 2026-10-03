const RESERVED_NAMES = new Set([
  "CON", "PRN", "AUX", "NUL",
  "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
  "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
]);

/** "My Scene" -> "My Scene.py"; leaves an existing .py suffix alone. */
export function toScriptName(input: string): string {
  const name = input.trim();
  return name.toLowerCase().endsWith(".py") ? name : `${name}.py`;
}

/** Returns an error message, or null when *name* is a usable script filename. */
export function validateScriptName(name: string, existing: readonly string[] = []): string | null {
  const stem = name.replace(/\.py$/i, "");
  if (!stem.trim()) return "Enter a file name.";
  if (/[<>:"/\\|?*]/.test(name) || [...name].some((char) => char.charCodeAt(0) < 32)) {
    return 'Names can\'t contain < > : " / \\ | ? or *.';
  }
  if (/^[\s.]|[\s.]$/.test(stem)) return "Names can't start or end with a space or dot.";
  if (RESERVED_NAMES.has(stem.toUpperCase())) return `"${stem}" is a reserved name on Windows.`;
  if (existing.some((other) => other.toLowerCase() === name.toLowerCase())) return `${name} already exists.`;
  return null;
}

/** "orbit_demo.py" -> "OrbitDemo" (a valid Python class name). */
export function classNameFromFile(filename: string): string {
  const words = filename
    .replace(/\.py$/i, "")
    .split(/[^A-Za-z0-9]+/)
    .filter(Boolean)
    .map((word) => word[0].toUpperCase() + word.slice(1));
  let name = words.join("") || "NewScene";
  if (/^\d/.test(name)) name = `Scene${name}`;
  return name;
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`;
}

/** Compact relative time for an epoch-seconds timestamp ("just now", "5m ago", "3d ago"). */
export function formatRelativeTime(epochSeconds: number, nowMs: number = Date.now()): string {
  const seconds = Math.max(0, Math.round(nowMs / 1000 - epochSeconds));
  if (seconds < 45) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(epochSeconds * 1000).toLocaleDateString();
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds % 1 === 0 ? seconds : seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${Math.round(seconds % 60)}s`;
}

/** Python string literal for *value*; raw strings keep LaTeX backslashes readable. */
export function pythonString(value: string, { raw = false } = {}): string {
  const trailingBackslashes = value.match(/\\*$/)?.[0].length ?? 0;
  if (raw && !/[\r\n]/.test(value) && trailingBackslashes % 2 === 0) {
    if (!value.includes('"')) return `r"${value}"`;
    if (!value.includes("'")) return `r'${value}'`;
  }
  const escaped = value
    .replace(/\\/g, "\\\\")
    .replace(/"/g, '\\"')
    .replace(/\n/g, "\\n")
    .replace(/\r/g, "\\r");
  return `"${escaped}"`;
}

const IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"];
const AUDIO_EXTENSIONS = [".mp3", ".wav", ".ogg", ".m4a"];

export type AssetKind = "image" | "vector" | "audio" | "font" | "other";

export function assetKind(name: string): AssetKind {
  const lower = name.toLowerCase();
  if (lower.endsWith(".svg")) return "vector";
  if (IMAGE_EXTENSIONS.some((ext) => lower.endsWith(ext))) return "image";
  if (AUDIO_EXTENSIONS.some((ext) => lower.endsWith(ext))) return "audio";
  if (lower.endsWith(".ttf") || lower.endsWith(".otf")) return "font";
  return "other";
}

/** Code that uses an uploaded asset from a scene's construct(). */
export function assetUsageSnippet(name: string): string {
  const path = pythonString(`assets/${name}`);
  switch (assetKind(name)) {
    case "vector":
      return `SVGMobject(${path})`;
    case "image":
      return `ImageMobject(${path})`;
    case "audio":
      return `self.add_sound(${path})`;
    default:
      return path;
  }
}
