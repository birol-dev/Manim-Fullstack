import { apiUrl } from "./api";
import { readRenderOrigins, renderOrigin } from "./renderOrigins";
import type { MediaFile, PreviewItem, StorageMode } from "./types";

export function scriptStem(filename: string): string {
  return filename.replace(/\.py$/i, "");
}

export function previewFromMedia(item: MediaFile): PreviewItem {
  const origin = renderOrigin(item.path, item.script);
  return {
    url: `${apiUrl(item.url)}?v=${Math.round(item.modified)}`,
    kind: item.type,
    title: item.scene,
    location: `workspace/media/${item.path}`,
    mediaPath: item.path,
    downloadName: item.name,
    file: origin.file ?? undefined,
    scene: item.scene,
    storage: origin.storage,
  };
}

/** The script name to show for a render output: its current name if it was renamed while rendering. */
export function mediaScriptLabel(item: MediaFile): string | null {
  return renderOrigin(item.path, item.script).file;
}

/**
 * Newest render of *scene* from *filename* (any scene when *scene* is empty) in *storage*:
 * a browser-storage file never falls back to the workspace file's render of the same name.
 */
export function latestRenderFor(media: readonly MediaFile[], filename: string, scene: string, storage: StorageMode = "disk"): MediaFile | null {
  const origins = readRenderOrigins();
  let best: MediaFile | null = null;
  for (const item of media) {
    if (scene && item.scene !== scene) continue;
    const origin = renderOrigin(item.path, item.script, origins);
    if (origin.storage !== storage || origin.file === null || scriptStem(origin.file) !== scriptStem(filename)) continue;
    if (!best || item.modified > best.modified) best = item;
  }
  return best;
}

/** The preview shows a render of *scene* from *filename* in *storage*. */
export function previewBelongsTo(preview: PreviewItem | null, filename: string, scene: string, storage: StorageMode = "disk"): boolean {
  return Boolean(preview && preview.file === filename && (preview.storage ?? "disk") === storage && (!scene || preview.scene === scene));
}
