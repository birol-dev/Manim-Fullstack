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

/** Scripts kept in this browser (storage mode "browser"). Seeds a starter file. */
export function loadBrowserFiles(): Record<string, string> {
  const files = readStored<Record<string, string> | null>(STORAGE_KEYS.browserFiles, null);
  if (files && typeof files === "object" && Object.keys(files).length > 0) return files;
  const seeded = { [BROWSER_STARTER_NAME]: BROWSER_STARTER };
  writeStored(STORAGE_KEYS.browserFiles, seeded);
  return seeded;
}

export function saveBrowserFiles(files: Record<string, string>): boolean {
  try {
    window.localStorage.setItem(STORAGE_KEYS.browserFiles, JSON.stringify(files));
    return true;
  } catch {
    return false;
  }
}
