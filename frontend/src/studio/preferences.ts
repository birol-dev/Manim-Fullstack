import { getPreferences, updatePreferences } from "./api";
import type { Appearance } from "./appearance";

export type { Appearance };

/** The choices kept with the workspace, so the desktop app can restore them at launch. */
export interface Preferences {
  appearance?: Appearance;
  sidebar_collapsed?: boolean;
  template_categories_open?: boolean | null;
  recent_colors?: string[];
  seen_exports?: string[];
  onboarding_done?: boolean;
  brand_name?: string;
  brand_color?: string | null;
  default_format?: string | null;
  default_theme?: string | null;
}

export type PreferenceKey = keyof Preferences;

export const APPEARANCE_KEY = "studio:appearance";
export const SIDEBAR_KEY = "studio:sidebar-collapsed";
export const CATEGORIES_KEY = "studio:template-categories-open";
export const RECENT_COLORS_KEY = "studio.recent-colors";
export const SEEN_EXPORTS_KEY = "studio:seen-exports";
export const ONBOARDING_KEY = "studio:onboarding-done";
export const BRAND_NAME_KEY = "studio:brand-name";
export const BRAND_COLOR_KEY = "studio:brand-color";
export const DEFAULT_FORMAT_KEY = "studio:default-format";
export const DEFAULT_THEME_KEY = "studio:default-theme";

export const PREFERENCE_KEYS: PreferenceKey[] = [
  "appearance",
  "sidebar_collapsed",
  "template_categories_open",
  "recent_colors",
  "seen_exports",
  "onboarding_done",
  "brand_name",
  "brand_color",
  "default_format",
  "default_theme",
];

/** The far end of a brand name, as the settings form enforces. */
export const BRAND_NAME_MAX = 80;

/** How long a burst of changes waits before one PATCH carries all of them. */
export const PREFERENCE_FLUSH_MS = 250;

/** Values from the server once they arrived; null while loading or when it is unreachable. */
let serverValues: Preferences | null = null;
let loadPromise: Promise<void> | null = null;
let wrote = false;
let pending = new Map<PreferenceKey, unknown>();
let timer: ReturnType<typeof setTimeout> | null = null;
let sending: Promise<void> = Promise.resolve();

function normalizeBrandName(value: unknown): string | undefined {
  return typeof value === "string" ? value.trim().slice(0, BRAND_NAME_MAX) : undefined;
}

function normalizeBrandColor(value: unknown): string | null | undefined {
  if (value === null) return null;
  if (typeof value !== "string") return undefined;
  return /^#[0-9a-f]{6}$/i.test(value.trim()) ? value.trim().toUpperCase() : undefined;
}

function normalizeChoice(value: unknown): string | null | undefined {
  if (value === null) return null;
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function readCache(key: PreferenceKey): unknown {
  try {
    switch (key) {
      case "appearance": {
        const value = localStorage.getItem(APPEARANCE_KEY);
        return value === "light" || value === "dark" || value === "system" ? value : undefined;
      }
      case "sidebar_collapsed": {
        const value = localStorage.getItem(SIDEBAR_KEY);
        return value === "true" ? true : value === "false" ? false : undefined;
      }
      case "template_categories_open": {
        const value = localStorage.getItem(CATEGORIES_KEY);
        return value === "true" ? true : value === "false" ? false : undefined;
      }
      case "recent_colors": {
        // readRecentColors drops anything that isn't a hex color.
        const value: unknown = JSON.parse(localStorage.getItem(RECENT_COLORS_KEY) ?? "null");
        return Array.isArray(value) ? value : undefined;
      }
      case "seen_exports": {
        const value: unknown = JSON.parse(localStorage.getItem(SEEN_EXPORTS_KEY) ?? "null");
        return Array.isArray(value) && value.every((item) => typeof item === "string") ? value : undefined;
      }
      case "onboarding_done": {
        const value = localStorage.getItem(ONBOARDING_KEY);
        return value === "true" ? true : value === "false" ? false : undefined;
      }
      case "brand_name":
        return normalizeBrandName(localStorage.getItem(BRAND_NAME_KEY));
      case "brand_color":
        return normalizeBrandColor(localStorage.getItem(BRAND_COLOR_KEY)) ?? undefined;
      case "default_format":
        return normalizeChoice(localStorage.getItem(DEFAULT_FORMAT_KEY)) ?? undefined;
      case "default_theme":
        return normalizeChoice(localStorage.getItem(DEFAULT_THEME_KEY)) ?? undefined;
    }
  } catch {
    return undefined; // Local preferences are optional when storage is unavailable.
  }
}

function writeCache(key: PreferenceKey, value: unknown) {
  try {
    switch (key) {
      case "appearance":
        localStorage.setItem(APPEARANCE_KEY, String(value));
        break;
      case "sidebar_collapsed":
        localStorage.setItem(SIDEBAR_KEY, String(value));
        break;
      case "template_categories_open":
        if (typeof value === "boolean") localStorage.setItem(CATEGORIES_KEY, String(value));
        else localStorage.removeItem(CATEGORIES_KEY);
        break;
      case "recent_colors":
        localStorage.setItem(RECENT_COLORS_KEY, JSON.stringify(value));
        break;
      case "seen_exports":
        localStorage.setItem(SEEN_EXPORTS_KEY, JSON.stringify(value));
        break;
      case "onboarding_done":
        localStorage.setItem(ONBOARDING_KEY, String(value));
        break;
      case "brand_name":
        localStorage.setItem(BRAND_NAME_KEY, String(value ?? ""));
        break;
      case "brand_color": {
        const color = normalizeBrandColor(value);
        if (color) localStorage.setItem(BRAND_COLOR_KEY, color);
        else localStorage.removeItem(BRAND_COLOR_KEY);
        break;
      }
      case "default_format": {
        const format = normalizeChoice(value);
        if (format) localStorage.setItem(DEFAULT_FORMAT_KEY, format);
        else localStorage.removeItem(DEFAULT_FORMAT_KEY);
        break;
      }
      case "default_theme": {
        const theme = normalizeChoice(value);
        if (theme) localStorage.setItem(DEFAULT_THEME_KEY, theme);
        else localStorage.removeItem(DEFAULT_THEME_KEY);
        break;
      }
    }
  } catch {
    /* Keep the in-memory choice. */
  }
}

/** Only known, well-formed values from the server are used. */
function sanitize(raw: unknown): Preferences {
  const values: Preferences = {};
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return values;
  const data = raw as Record<string, unknown>;
  if (data.appearance === "light" || data.appearance === "dark" || data.appearance === "system") {
    values.appearance = data.appearance;
  }
  if (typeof data.sidebar_collapsed === "boolean") values.sidebar_collapsed = data.sidebar_collapsed;
  if (typeof data.template_categories_open === "boolean" || data.template_categories_open === null) {
    values.template_categories_open = data.template_categories_open;
  }
  if (Array.isArray(data.recent_colors) && data.recent_colors.every((item) => typeof item === "string")) {
    values.recent_colors = data.recent_colors;
  }
  if (Array.isArray(data.seen_exports) && data.seen_exports.every((item) => typeof item === "string")) {
    values.seen_exports = data.seen_exports;
  }
  if (typeof data.onboarding_done === "boolean") values.onboarding_done = data.onboarding_done;
  const brandName = normalizeBrandName(data.brand_name);
  if (brandName !== undefined) values.brand_name = brandName;
  const brandColor = normalizeBrandColor(data.brand_color);
  if (brandColor !== undefined) values.brand_color = brandColor;
  const defaultFormat = normalizeChoice(data.default_format);
  if (defaultFormat !== undefined) values.default_format = defaultFormat;
  const defaultTheme = normalizeChoice(data.default_theme);
  if (defaultTheme !== undefined) values.default_theme = defaultTheme;
  return values;
}

function adopt(values: Preferences) {
  serverValues = values;
  for (const key of PREFERENCE_KEYS) {
    if (Object.prototype.hasOwnProperty.call(values, key)) writeCache(key, values[key]);
  }
}

/**
 * Load the workspace preferences once, waiting at most *timeoutMs*.
 *
 * The desktop app wipes browser storage at every launch, so the entry point awaits
 * this before the first render; an unreachable or slow server simply leaves the
 * localStorage cache and the defaults in charge.
 */
export function loadPreferences(timeoutMs = 400): Promise<void> {
  if (!loadPromise) loadPromise = loadOnce(timeoutMs);
  return loadPromise;
}

async function loadOnce(timeoutMs: number): Promise<void> {
  let deadline: ReturnType<typeof setTimeout> | undefined;
  const response = getPreferences().then(sanitize, () => null);
  const timeout = new Promise<null>((resolve) => {
    deadline = setTimeout(() => resolve(null), timeoutMs);
  });
  try {
    const values = await Promise.race([response, timeout]);
    if (values) adopt(values);
  } finally {
    if (deadline !== undefined) clearTimeout(deadline);
  }
  // An answer after the deadline still becomes the cache for later reads, unless
  // a newer local choice has been made in the meantime.
  void response.then((values) => {
    if (values && !wrote) adopt(values);
  });
}

/** The server value once loaded, else the localStorage cache, else undefined for the caller's default. */
export function readPreference<K extends PreferenceKey>(key: K): Preferences[K] | undefined {
  if (serverValues !== null && Object.prototype.hasOwnProperty.call(serverValues, key)) {
    return serverValues[key] as Preferences[K];
  }
  return readCache(key) as Preferences[K] | undefined;
}

/** Save a choice in the fast local cache now and in the workspace shortly (coalesced). */
export function writePreference<K extends PreferenceKey>(key: K, value: Preferences[K]): void {
  writeCache(key, value);
  if (serverValues !== null) serverValues = { ...serverValues, [key]: value };
  wrote = true;
  pending.set(key, value);
  if (timer !== null) clearTimeout(timer);
  timer = setTimeout(() => void flushPreferences(), PREFERENCE_FLUSH_MS);
}

/** Send everything written so far as one PATCH; failures leave the local cache in charge. */
export function flushPreferences(): Promise<void> {
  if (timer !== null) {
    clearTimeout(timer);
    timer = null;
  }
  if (pending.size === 0) return sending;
  const patch = Object.fromEntries(pending) as Partial<Preferences>;
  pending = new Map();
  sending = sending.then(async () => {
    try {
      await updatePreferences(patch);
    } catch {
      /* Offline: the localStorage cache still has this choice. */
    }
  });
  return sending;
}

/** Whether the workspace answered the preferences request (even with an empty object). */
export function preferencesLoaded(): boolean {
  return serverValues !== null;
}

export function readOnboardingDone(): boolean {
  return readPreference("onboarding_done") === true;
}

/**
 * First launch: the workspace answered, and nobody has finished the welcome tour.
 *
 * An unanswered request (an older server, or a test without a preferences mock) leaves the
 * gallery alone instead of trapping someone on the welcome page.
 */
export function needsOnboarding(): boolean {
  return preferencesLoaded() && !readOnboardingDone();
}

export function setOnboardingDone(value: boolean) {
  writePreference("onboarding_done", value);
}

export function readBrandName(): string {
  return readPreference("brand_name") ?? "";
}

export function setBrandName(value: string) {
  writePreference("brand_name", normalizeBrandName(value) ?? "");
}

/** "#RRGGBB", or null when the brand keeps the template's own colours. */
export function readBrandColor(): string | null {
  return readPreference("brand_color") ?? null;
}

export function setBrandColor(value: string | null) {
  writePreference("brand_color", normalizeBrandColor(value) ?? null);
}

export function readDefaultFormat(): string | null {
  return readPreference("default_format") ?? null;
}

export function setDefaultFormat(value: string | null) {
  writePreference("default_format", normalizeChoice(value) ?? null);
}

export function readDefaultTheme(): string | null {
  return readPreference("default_theme") ?? null;
}

export function setDefaultTheme(value: string | null) {
  writePreference("default_theme", normalizeChoice(value) ?? null);
}

/** Forget everything this module knows (tests). */
export function resetPreferencesForTests() {
  serverValues = null;
  loadPromise = null;
  wrote = false;
  pending = new Map();
  sending = Promise.resolve();
  if (timer !== null) {
    clearTimeout(timer);
    timer = null;
  }
}
