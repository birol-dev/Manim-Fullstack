// Mirrors backend/workspace_paths.py (safe_basename + validate_new_filename) so the
// New script and rename forms show the server's rule before a round trip.
const RESERVED_NAMES = new Set([
  "CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
  ...Array.from({ length: 10 }, (_, index) => `COM${index}`),
  ...Array.from({ length: 10 }, (_, index) => `LPT${index}`),
]);
const RESERVED_CHARS = '<>:"|?*';
export const MAX_FILENAME_BYTES = 255;
export const MAX_FILENAME_STEM_CHARS = 100;
export const TEMP_SCRIPT_PREFIX = "_temp_run_";

/** "My Scene" -> "My Scene.py"; leaves an existing .py suffix alone. */
export function toScriptName(input: string): string {
  const name = input.trim();
  return name.toLowerCase().endsWith(".py") ? name : `${name}.py`;
}

/** Returns an error message, or null when *name* is a usable name for a new script. */
export function validateScriptName(name: string, existing: readonly string[] = []): string | null {
  const stem = name.replace(/\.py$/i, "");
  if (!stem.trim()) return "Enter a file name.";
  if (name !== name.trim()) return "Filename cannot start or end with a dot or space.";
  if (/[/\\]/.test(name)) return "Filename cannot contain folders or path separators.";
  if (/[\p{Cc}\p{Cf}]/u.test(name)) return "Filename cannot contain control or invisible characters.";
  const bad = [...new Set([...name].filter((char) => RESERVED_CHARS.includes(char)))].sort();
  if (bad.length) return `Filename cannot contain ${bad.join(" ")}.`;
  if (new TextEncoder().encode(name).length > MAX_FILENAME_BYTES) return `Filename is too long (max ${MAX_FILENAME_BYTES} bytes).`;
  if ([...stem].length > MAX_FILENAME_STEM_CHARS) {
    return `Filename is too long (max ${MAX_FILENAME_STEM_CHARS} characters before the extension).`;
  }
  if (!stem.replace(/^\.+|\.+$/g, "")) return "Filename needs a name before the extension.";
  if (RESERVED_NAMES.has(name.split(".")[0].trimEnd().toUpperCase())) return `Filename '${name}' is a reserved device name.`;
  if (name.startsWith("-")) return "Filename cannot start with a dash.";
  if (name.startsWith(".")) return "Filename cannot start with a dot.";
  if (name.toLowerCase().startsWith(TEMP_SCRIPT_PREFIX)) {
    return `Filenames starting with '${TEMP_SCRIPT_PREFIX}' are reserved for scratch renders.`;
  }
  if (existing.includes(name)) return `${name} already exists.`;
  const folded = name.toLowerCase();
  const clash = existing.find((other) => other.toLowerCase() === folded);
  if (clash) return `'${clash}' already exists. File names that differ only by case are not allowed.`;
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

const PYTHON_KEYWORDS = new Set(
  "False None True and as assert async await break class continue def del elif else except finally for from global if import in is lambda nonlocal not or pass raise return try while with yield".split(" "),
);

/** A Python variable name for an asset, from its file name ("My Logo.svg" -> "my_logo"). */
export function assetVariable(name: string, fallback: string): string {
  const stem = name.replace(/\.[^.]*$/, "").toLowerCase();
  const cleaned = stem.replace(/[^a-z0-9_]+/g, "_").replace(/^_+|_+$/g, "");
  if (!cleaned) return fallback;
  const identifier = /^\d/.test(cleaned) ? `_${cleaned}` : cleaned;
  return PYTHON_KEYWORDS.has(identifier) ? `${identifier}_` : identifier;
}

/** Statements that use an uploaded asset in a scene's construct(). */
export function assetUsageSnippet(name: string): string {
  const path = pythonString(`assets/${name}`);
  switch (assetKind(name)) {
    case "vector": {
      const variable = assetVariable(name, "graphic");
      return `${variable} = SVGMobject(${path})\nself.play(FadeIn(${variable}))`;
    }
    case "image": {
      const variable = assetVariable(name, "picture");
      return `${variable} = ImageMobject(${path})\nself.play(FadeIn(${variable}))`;
    }
    case "audio":
      return `self.add_sound(${path})`;
    default:
      return path;
  }
}
