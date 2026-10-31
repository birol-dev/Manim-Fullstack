/** Portable project files: one file to carry a video, and the open action's state. */
import { useState, type DragEvent } from "react";
import { toast } from "sonner";

import { friendlyError, getProjectFileInfo, openProjectFile, projectFileUrl } from "./api";
import type { PortableOpenResult } from "./types";

export const PORTABLE_SUFFIX = ".manimstudio";
export const MAX_PORTABLE_BYTES = 200 * 1024 * 1024;

/** Whether a dragged item is a file (not a text selection or a template card). */
export function dragHasFiles(event: DragEvent) {
  try {
    return Array.from(event.dataTransfer?.types ?? []).includes("Files");
  } catch {
    return false;
  }
}

export function isPortableFile(file: File) {
  return file.name.toLowerCase().endsWith(PORTABLE_SUFFIX);
}

/** A file as base64, the shape the server's open route accepts. */
export function portableFileData(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Couldn't read that file. Choose it again."));
    reader.onload = () => {
      const result = String(reader.result ?? "");
      const comma = result.indexOf(",");
      if (comma < 0) reject(new Error("Couldn't read that file. Choose it again."));
      else resolve(result.slice(comma + 1));
    };
    reader.readAsDataURL(file);
  });
}

/**
 * Save a saved video as one file. A link with `download` is exactly how a finished export
 * is saved in the desktop app, so WebView2 shows the same system Save dialog.
 */
export async function saveProjectFile(id: string) {
  const info = await getProjectFileInfo(id);
  const link = document.createElement("a");
  link.href = projectFileUrl(id);
  link.download = info.filename || `video${PORTABLE_SUFFIX}`;
  link.hidden = true;
  document.body.appendChild(link);
  link.click();
  link.remove();
  if (info.notes?.length) toast(info.notes.join(" "));
}

/** The open action's state: one file at a time, errors kept on the page. */
export function usePortableOpener(onOpened: (result: PortableOpenResult) => void) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const open = async (file: File | null | undefined) => {
    if (!file) return;
    if (!isPortableFile(file)) {
      setError(`Choose a Manim Studio file (it ends in ${PORTABLE_SUFFIX}).`);
      return;
    }
    if (!file.size) {
      setError("That file is empty. Choose another one.");
      return;
    }
    if (file.size > MAX_PORTABLE_BYTES) {
      setError("That file is larger than 200 MB and can't be opened.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onOpened(await openProjectFile(file.name, await portableFileData(file)));
    } catch (problem) {
      setError(friendlyError(problem, "Couldn't open that file."));
    } finally {
      setBusy(false);
    }
  };
  return { error, busy, open, clearError: () => setError(null) };
}
