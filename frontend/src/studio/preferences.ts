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
}

export type PreferenceKey = keyof Preferences;

export const APPEARANCE_KEY = "studio:appearance";
export const SIDEBAR_KEY = "studio:sidebar-collapsed";
export const CATEGORIES_KEY = "studio:template-categories-open";
export const RECENT_COLORS_KEY = "studio.recent-colors";
export const SEEN_EXPORTS_KEY = "studio:seen-exports";

export const PREFERENCE_KEYS: PreferenceKey[] = [
  "appearance",
  "sidebar_collapsed",
  "template_categories_open",
  "recent_colors",
  "seen_exports",
];

/** How long a burst of changes waits before one PATCH carries all of them. */
export const PREFERENCE_FLUSH_MS = 250;

/** Values from the server once they arrived; null while loading or when it is unreachable. */
let serverValues: Preferences | null = null;
let loadPromise: Promise<void> | null = null;
let wrote = false;
let pending = new Map<PreferenceKey, unknown>();
let timer: ReturnType<typeof setTimeout> | null = null;
let sending: Promise<void> = Promise.resolve();

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
