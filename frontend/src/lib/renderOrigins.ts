import type { StorageMode } from "./types";

// Which storage mode (and script name) each render output came from, kept client side.
// The server puts browser-storage renders in media/<kind>/.browser/<stem>/ and says so in
// each media item's `storage`, so a browser my_scene.py and the workspace folder's
// my_scene.py no longer share an output folder. The record here still labels an output
// with the script's current name after a rename mid-render (the folder keeps the name the
// render started under), and tells apart outputs that older servers wrote to the shared
// folder. Outputs with no record count as the storage the server reports, else the
// workspace folder's.

const KEY = "mc.renderOrigins";
const MAX_ENTRIES = 500;

export interface RenderOrigin {
  storage: StorageMode;
  /** The script's name when the output was written (after any rename while it rendered). */
  file: string;
  at: number;
}

type Origins = Record<string, RenderOrigin>;

function read(): Origins {
  try {
    const raw = window.localStorage.getItem(KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" ? (parsed as Origins) : {};
  } catch {
    return {};
  }
}

function write(origins: Origins) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(origins));
  } catch {
    // Storage full or blocked: origins are a hint, not data.
  }
}

/** Remember that the output at *mediaPath* (relative to workspace/media) was rendered from *file* in *storage*. */
export function recordRenderOrigin(mediaPath: string, storage: StorageMode, file: string) {
  const origins = read();
  origins[mediaPath] = { storage, file, at: Date.now() };
  const paths = Object.keys(origins);
  if (paths.length > MAX_ENTRIES) {
    paths.sort((a, b) => origins[a].at - origins[b].at);
    for (const path of paths.slice(0, paths.length - MAX_ENTRIES)) delete origins[path];
  }
  write(origins);
}

/** Relabel the outputs recorded for *oldName* (renamed in *storage*). */
export function renameRenderOrigins(storage: StorageMode, oldName: string, newName: string) {
  const origins = read();
  let changed = false;
  for (const origin of Object.values(origins)) {
    if (origin.storage === storage && origin.file === oldName) {
      origin.file = newName;
      changed = true;
    }
  }
  if (changed) write(origins);
}

/** Forget an output (deleted from the Renders list). */
export function forgetRenderOrigin(mediaPath: string) {
  const origins = read();
  if (!(mediaPath in origins)) return;
  delete origins[mediaPath];
  write(origins);
}

/** A snapshot of every recorded origin, for looking up many outputs at once. */
export function readRenderOrigins(): Readonly<Origins> {
  return read();
}

/**
 * Where the output at *mediaPath* came from. *serverStorage* is the media item's `storage`:
 * an output in the browser folder is always a browser-storage render. Otherwise a recorded
 * origin wins (older servers wrote browser renders to the shared folder), and unrecorded
 * outputs are the workspace folder's.
 */
export function renderOrigin(
  mediaPath: string,
  stem: string | null,
  origins: Readonly<Origins> = read(),
  serverStorage?: StorageMode,
): { storage: StorageMode; file: string | null } {
  const origin = origins[mediaPath];
  const byStem = stem ? `${stem}.py` : null;
  if (serverStorage === "browser") {
    return { storage: "browser", file: origin?.storage === "browser" ? origin.file : byStem };
  }
  if (origin) return { storage: origin.storage, file: origin.file };
  return { storage: "disk", file: byStem };
}
