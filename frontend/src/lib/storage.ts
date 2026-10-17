/**
 * localStorage access that never throws (private windows, blocked storage,
 * quota errors). Values are JSON encoded.
 */
export const STORAGE_KEYS = {
  storageMode: "mc.storageMode",
  quality: "mc.quality",
  autoSave: "mc.autoSaveBeforeRender",
  downloadOnly: "mc.downloadOnly",
  useOpenGL: "mc.useOpenGL",
  autoRender: "mc.autoRender",
  loopPreview: "mc.loopPreview",
  editorFontSize: "mc.editorFontSize",
  sidebarView: "mc.sidebarView",
  activeFile: "mc.activeFile",
  sceneByFile: "mc.sceneByFile",
  /** "mode:file" -> scene name typed with "Other scene…" (the parser can't see it). */
  typedSceneByFile: "mc.typedSceneByFile",
  browserFiles: "mc.browserFiles",
} as const;

// Keys used by earlier versions, migrated on first read.
const LEGACY_KEYS: Partial<Record<string, string>> = {
  [STORAGE_KEYS.storageMode]: "manim_composer_storage_location",
  [STORAGE_KEYS.autoSave]: "manim_composer_auto_save_on_render",
  [STORAGE_KEYS.downloadOnly]: "manim_composer_download_only_mode",
  [STORAGE_KEYS.browserFiles]: "manim_composer_browser_files",
};

function parseLegacy(key: string, raw: string): unknown {
  if (key === STORAGE_KEYS.storageMode) return raw === "browser" ? "browser" : "disk";
  if (raw === "true" || raw === "false") return raw === "true";
  return JSON.parse(raw);
}

export function readStored<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    if (raw !== null) return JSON.parse(raw) as T;
    const legacyKey = LEGACY_KEYS[key];
    const legacy = legacyKey ? window.localStorage.getItem(legacyKey) : null;
    if (legacy !== null) return parseLegacy(key, legacy) as T;
  } catch {
    // fall through
  }
  return fallback;
}

export function writeStored(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage full or unavailable: preferences just won't persist.
  }
}

export const BROWSER_STARTER_NAME = "my_scene.py";

export const BROWSER_STARTER = `from manim import *


class MyScene(Scene):
    def construct(self):
        text = Text("Stored in your browser", font_size=40)
        self.play(Write(text))
        self.wait(1)
        self.play(FadeOut(text))
`;

// ---- Browser-storage scripts --------------------------------------------------
// One localStorage key per script ("mc.browserFile:<name>"), so a tab whose view of
// storage is stale can only ever write the file it saves, never another tab's file.
// Older versions kept every script in one JSON map (mc.browserFiles, before that
// manim_composer_browser_files); it is migrated on first read and removed.

const BROWSER_FILE_PREFIX = "mc.browserFile:";
/** Set once the starter script has been offered, so deleting every script leaves an empty list. */
const BROWSER_SEEDED_KEY = "mc.browserSeeded";

/** localStorage key that holds the browser-storage script *name*. */
export function browserFileKey(name: string): string {
  return `${BROWSER_FILE_PREFIX}${name}`;
}

/** True for a "storage" event key that can change the browser-storage scripts. */
export function isBrowserFilesKey(key: string | null): boolean {
  return key === null || key.startsWith(BROWSER_FILE_PREFIX) || key === STORAGE_KEYS.browserFiles;
}

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function storedNames(store: Storage): string[] {
  const names: string[] = [];
  for (let index = 0; index < store.length; index += 1) {
    const key = store.key(index);
    if (key?.startsWith(BROWSER_FILE_PREFIX)) names.push(key.slice(BROWSER_FILE_PREFIX.length));
  }
  return names;
}

/** Move the old one-map format into per-file keys (files already stored per key win). */
function migrateBrowserMap(store: Storage): void {
  const legacyKeys = [STORAGE_KEYS.browserFiles, "manim_composer_browser_files"];
  for (const key of legacyKeys) {
    let raw: string | null;
    try {
      raw = store.getItem(key);
    } catch {
      return;
    }
    if (raw === null) continue;
    let map: unknown;
    try {
      map = JSON.parse(raw);
    } catch {
      map = null;
    }
    try {
      if (map && typeof map === "object") {
        for (const [name, content] of Object.entries(map as Record<string, unknown>)) {
          if (typeof content !== "string" || store.getItem(browserFileKey(name)) !== null) continue;
          store.setItem(browserFileKey(name), content);
        }
      }
      store.setItem(BROWSER_SEEDED_KEY, "true");
      store.removeItem(key);
    } catch {
      return; // Storage full: keep the map, try again next time.
    }
  }
}

/** Read one browser-storage script, or undefined when it doesn't exist. */
export function readBrowserFile(name: string): string | undefined {
  const store = storage();
  if (!store) return undefined;
  migrateBrowserMap(store);
  try {
    return store.getItem(browserFileKey(name)) ?? undefined;
  } catch {
    return undefined;
  }
}

/** Write one browser-storage script. False when storage is full or unavailable. */
export function writeBrowserFile(name: string, content: string): boolean {
  const store = storage();
  if (!store) return false;
  try {
    store.setItem(browserFileKey(name), content);
    store.setItem(BROWSER_SEEDED_KEY, "true");
    return true;
  } catch {
    return false;
  }
}

export function deleteBrowserFile(name: string): void {
  try {
    storage()?.removeItem(browserFileKey(name));
  } catch {
    // nothing to do
  }
}

/**
 * Scripts kept in this browser (storage mode "browser"). The starter script is
 * added the first time only; after the user deletes everything the list stays empty.
 */
export function loadBrowserFiles(): Record<string, string> {
  const store = storage();
  if (!store) return {};
  migrateBrowserMap(store);
  const files: Record<string, string> = {};
  for (const name of storedNames(store)) {
    try {
      const content = store.getItem(browserFileKey(name));
      if (content !== null) files[name] = content;
    } catch {
      // skip
    }
  }
  let seeded: boolean;
  try {
    seeded = store.getItem(BROWSER_SEEDED_KEY) !== null;
  } catch {
    seeded = true;
  }
  if (Object.keys(files).length === 0 && !seeded) {
    if (writeBrowserFile(BROWSER_STARTER_NAME, BROWSER_STARTER)) files[BROWSER_STARTER_NAME] = BROWSER_STARTER;
  }
  return files;
}
