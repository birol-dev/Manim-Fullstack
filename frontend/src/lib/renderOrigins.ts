import type { StorageMode } from "./types";

// Which storage mode (and script name) each render output came from, kept client side.
// The server writes every render to media/videos/<script stem>/..., whatever the script's
// storage: a browser-storage my_scene.py and the workspace folder's my_scene.py share
// one output folder. Recording the origin here keeps a disk render out of a browser file's
// preview (and the other way round), and labels an output with the script's current name
// after a rename mid-render (the folder keeps the name the render started under).
// Outputs with no record (rendered before this was kept, or by another browser) count as
// the workspace folder's.

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

/** Where the output at *mediaPath* came from; unrecorded outputs are the workspace folder's. */
export function renderOrigin(
  mediaPath: string,
  stem: string | null,
  origins: Readonly<Origins> = read(),
): { storage: StorageMode; file: string | null } {
  const origin = origins[mediaPath];
  if (origin) return { storage: origin.storage, file: origin.file };
  return { storage: "disk", file: stem ? `${stem}.py` : null };
}
