import { apiUrl } from "./api";
import type { MediaFile, PreviewItem } from "./types";

export function scriptStem(filename: string): string {
  return filename.replace(/\.py$/i, "");
}

export function previewFromMedia(item: MediaFile): PreviewItem {
  return {
    url: `${apiUrl(item.url)}?v=${Math.round(item.modified)}`,
    kind: item.type,
    title: item.scene,
    location: `workspace/media/${item.path}`,
    mediaPath: item.path,
    downloadName: item.name,
    file: item.script ? `${item.script}.py` : undefined,
    scene: item.scene,
  };
}

/** Newest render of *scene* from *filename* (any scene when *scene* is empty). */
export function latestRenderFor(media: readonly MediaFile[], filename: string, scene: string): MediaFile | null {
  const stem = scriptStem(filename);
  let best: MediaFile | null = null;
  for (const item of media) {
    if (item.script !== stem || (scene && item.scene !== scene)) continue;
    if (!best || item.modified > best.modified) best = item;
  }
  return best;
}

/** The preview shows a render of *scene* from *filename*. */
export function previewBelongsTo(preview: PreviewItem | null, filename: string, scene: string): boolean {
  return Boolean(preview && preview.file === filename && (!scene || preview.scene === scene));
}
