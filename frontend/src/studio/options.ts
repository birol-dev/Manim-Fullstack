/** Plain-language labels for the studio's choices, and default settings. */
import type {
  Aspect,
  BackgroundKind,
  Card,
  Catalog,
  Energy,
  Ending,
  ExportFormat,
  ExportQuality,
  RenderSettings,
  TemplateInfo,
} from "./types";

export const ASPECTS: Array<{ value: Aspect; label: string; hint: string; w: number; h: number }> = [
  { value: "16:9", label: "Wide", hint: "YouTube, TVs, slides", w: 16, h: 9 },
  { value: "9:16", label: "Tall", hint: "Stories, Reels, TikTok", w: 9, h: 16 },
  { value: "1:1", label: "Square", hint: "Feeds, chats", w: 1, h: 1 },
  { value: "4:5", label: "Portrait", hint: "Instagram & Facebook feed", w: 4, h: 5 },
];

export const isPortrait = (aspect: Aspect | undefined) => aspect === "9:16" || aspect === "4:5";

export const ENERGIES: Array<{ value: Energy; label: string }> = [
  { value: "calm", label: "Calm" },
  { value: "normal", label: "Normal" },
  { value: "punchy", label: "Punchy" },
];

export const ENDINGS: Array<{ value: Ending; label: string }> = [
  { value: "hold", label: "Stay" },
  { value: "fade", label: "Fade out" },
  { value: "cut", label: "Cut" },
];

export const BACKGROUNDS: Array<{ value: BackgroundKind; label: string }> = [
  { value: "theme", label: "Theme" },
  { value: "solid", label: "Color" },
  { value: "gradient", label: "Gradient" },
  { value: "transparent", label: "None" },
];

export const LOCALES: Array<{ value: string; label: string; sample: string }> = [
  { value: "en", label: "English", sample: "1,234.5" },
  { value: "tr", label: "Türkçe", sample: "1.234,5" },
  { value: "de", label: "Deutsch", sample: "1.234,5" },
  { value: "fr", label: "Français", sample: "1 234,5" },
  { value: "es", label: "Español", sample: "1234,5" },
  { value: "it", label: "Italiano", sample: "1.234,5" },
  { value: "pt", label: "Português", sample: "1234,5" },
  { value: "nl", label: "Nederlands", sample: "1.234,5" },
];

export const EXPORT_FORMATS: Array<{ value: ExportFormat; label: string; hint: string; video: boolean; transparent?: boolean }> = [
  { value: "mp4", label: "Video (MP4)", hint: "Plays everywhere: phones, social media, slides.", video: true },
  { value: "gif", label: "GIF", hint: "A silent loop for chats, emails and websites. Bigger file, fewer colors.", video: false },
  { value: "webm", label: "See-through video (WebM)", hint: "Transparent background, for websites and video editors.", video: true, transparent: true },
  { value: "mov", label: "See-through video (MOV)", hint: "Transparent background, for Premiere, Final Cut or iMovie. Large file.", video: true, transparent: true },
  { value: "png", label: "Picture (PNG)", hint: "One still image of the best moment.", video: false },
];

export const QUALITIES: Array<{ value: ExportQuality; label: string; hint: string }> = [
  { value: "draft", label: "Draft (480p)", hint: "Fastest. Good for a quick check." },
  { value: "720p", label: "720p", hint: "Good for phones and chats. Small file." },
  { value: "1080p", label: "1080p (Full HD)", hint: "Sharp on most screens. The best choice for most uses." },
  { value: "1080p60", label: "1080p, 60 fps", hint: "Extra smooth motion. Takes about twice as long." },
  { value: "4k", label: "4K", hint: "Very sharp for big screens. Slow to make, large file." },
];

/** The qualities the server lists (ids or {id} objects), or all of ours. */
export function availableQualities(catalog: Catalog | null) {
  const listed = catalog?.qualities;
  const ids = Array.isArray(listed)
    ? listed.map((item) => (typeof item === "string" ? item : (item as { id?: string })?.id)).filter(Boolean)
    : Object.keys((listed as Record<string, unknown>) ?? {});
  const filtered = QUALITIES.filter((quality) => ids.includes(quality.value));
  return filtered.length ? filtered : QUALITIES;
}

export const DEFAULT_SETTINGS: RenderSettings = {
  aspect: "16:9",
  length: null,
  theme: "clean",
  background: { kind: "theme", color: null, color2: null },
  energy: "normal",
  ending: "hold",
  safe_zone: false,
  locale: "en",
};

/** Full settings: defaults, then the template's default format, then the card's or project's own. */
export function initialSettings(template: TemplateInfo | undefined, overrides: Partial<RenderSettings> | undefined): RenderSettings {
  const merged: RenderSettings = {
    ...DEFAULT_SETTINGS,
    aspect: template?.default_aspect ?? DEFAULT_SETTINGS.aspect,
    ...(overrides ?? {}),
    background: { ...DEFAULT_SETTINGS.background, ...(overrides?.background ?? {}) },
  };
  if (template && !template.aspects.includes(merged.aspect)) merged.aspect = template.default_aspect;
  return merged;
}

/** A gallery card's thumbnail request settings (the card's look in the template's default format). */
export function cardSettings(card: Card, template: TemplateInfo | undefined): Partial<RenderSettings> {
  return { aspect: template?.default_aspect ?? "16:9", ...card.settings };
}

export function formatSeconds(seconds: number): string {
  if (!Number.isFinite(seconds)) return "";
  if (seconds < 60) return `${Math.round(seconds * 10) / 10} s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return rest ? `${minutes} min ${rest} s` : `${minutes} min`;
}

export function formatBytes(size: number | null | undefined): string {
  if (!size || size < 0) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${(size / (1024 * 1024)).toFixed(size < 10 * 1024 * 1024 ? 1 : 0)} MB`;
}

/** Seconds or ISO string → Date. */
export function toDate(value: number | string | null | undefined): Date | null {
  if (value == null) return null;
  const date = typeof value === "number" ? new Date(value < 1e12 ? value * 1000 : value) : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function timeAgo(value: number | string | null | undefined, now = Date.now()): string {
  const date = toDate(value);
  if (!date) return "";
  const seconds = Math.round((now - date.getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return days === 1 ? "yesterday" : `${days} days ago`;
  return date.toLocaleDateString();
}

/** "shopping-cart" → "Shopping cart". */
export function iconLabel(name: string) {
  const words = name.replace(/[-_]+/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export const ACTIVE_EXPORT = new Set(["queued", "rendering"]);

export function exportStatusLabel(job: { status: string; progress: number | null }): string {
  switch (job.status) {
    case "queued":
      return "Waiting to start…";
    case "rendering":
      return job.progress != null ? `Making… ${Math.round(job.progress)}%` : "Making…";
    case "done":
      return "Ready";
    case "failed":
      return "Didn't work";
    case "cancelled":
      return "Cancelled";
    default:
      return job.status;
  }
}

/** The server's progress messages, without the technical words. */
export function friendlyExportMessage(message: string | null | undefined): string {
  if (!message) return "";
  const step = /^Rendering animation (\d+)(?: of (\d+))?$/i.exec(message);
  if (step) return step[2] ? `Step ${step[1]} of ${step[2]}` : `Step ${step[1]}`;
  if (/^Starting Manim$/i.test(message)) return "Starting";
  if (/^Rendering the image$/i.test(message)) return "Drawing the picture";
  return message.replace(/\bManim\b\s*/g, "").replace(/\bRendering\b/g, "Making").replace(/\brender(ing)?\b/gi, "making");
}

export const formatLabel = (format: string) => EXPORT_FORMATS.find((item) => item.value === format)?.label ?? format.toUpperCase();
export const qualityLabel = (quality: string) => QUALITIES.find((item) => item.value === quality)?.label ?? quality;

/** Cards whose title, summary, tags (or their template's) contain every typed word. */
export function filterCards(cards: Card[], query: string, templates: Map<string, TemplateInfo>): Card[] {
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return cards;
  return cards.filter((card) => {
    const template = templates.get(card.template);
    const haystack = [card.title, card.summary, ...card.tags, template?.title, ...(template?.tags ?? [])].join(" ").toLowerCase();
    return words.every((word) => haystack.includes(word));
  });
}
