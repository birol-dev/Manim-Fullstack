import { ApiError, apiUrl, postJson, requestJson } from "@/lib/api";
import type { AssetFile } from "@/lib/types";

import type {
  Catalog,
  ExportFormat,
  ExportJob,
  ExportQuality,
  Params,
  PreviewRequest,
  PreviewResponse,
  Project,
  ProjectSummary,
  RenderSettings,
} from "./types";

/** What the studio says when the server can't be reached (the shared message names the code app). */
export const STUDIO_OFFLINE = "Can't reach the app's server. Is it still running?";

export interface AIConnection {
  available: boolean;
  url: string;
  token: string;
}

/** Credentials are fetched on demand and never cached. */
export const getConnection = () => requestJson<AIConnection>("/api/studio/connection");

export function friendlyError(error: unknown, fallback = "Something went wrong. Please try again."): string {
  if (error instanceof ApiError && error.status === 0) return STUDIO_OFFLINE;
  return error instanceof Error && error.message ? error.message : fallback;
}

/** A preview or export failure in plain words (the server's text can be technical). */
export function previewProblem(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 0) return STUDIO_OFFLINE;
    if (error.status === 503) return "Previews aren't available right now. The app may still be starting up.";
    if (error.status === 504) return "The preview took too long. Try again.";
    if (error.status === 429) return "Busy right now. Try again in a moment.";
    if (error.status >= 500) return "This content couldn't be drawn. Try shorter text or another option.";
  }
  return friendlyError(error, "Couldn't update the preview.");
}

let catalogPromise: Promise<Catalog> | null = null;

/** The gallery catalog, fetched once per page load (a failed fetch is retried next time). */
export function getCatalog(): Promise<Catalog> {
  if (!catalogPromise) {
    catalogPromise = requestJson<Catalog>("/api/studio/catalog").catch((error) => {
      catalogPromise = null;
      throw error;
    });
  }
  return catalogPromise;
}

/** Forget the cached catalog (tests). */
export function resetCatalogCache() {
  catalogPromise = null;
}

export function requestPreview(request: PreviewRequest, signal?: AbortSignal): Promise<PreviewResponse> {
  return requestJson<PreviewResponse>("/api/studio/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal,
  });
}

export interface ExportRequest {
  template: string;
  params: Params;
  settings: Partial<RenderSettings>;
  format: ExportFormat;
  quality: ExportQuality;
  title?: string;
}

export const startExport = (body: ExportRequest) => postJson<ExportJob>("/api/studio/exports", body);
export const listExports = () => requestJson<ExportJob[]>("/api/studio/exports");
export const getExport = (id: string) => requestJson<ExportJob>(`/api/studio/exports/${encodeURIComponent(id)}`);
export const cancelExport = (id: string) =>
  requestJson<ExportJob>(`/api/studio/exports/${encodeURIComponent(id)}`, { method: "DELETE" });

export const listProjects = () => requestJson<ProjectSummary[]>("/api/studio/projects");
export const getProject = (id: string) => requestJson<Project>(`/api/studio/projects/${encodeURIComponent(id)}`);
export const deleteProject = (id: string) =>
  requestJson<unknown>(`/api/studio/projects/${encodeURIComponent(id)}`, { method: "DELETE" });

export interface ProjectDraft {
  title?: string;
  template: string;
  params: Params;
  settings: Partial<RenderSettings>;
}

export const createProject = (body: ProjectDraft, keepalive = false) => requestJson<Project>("/api/studio/projects", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
  keepalive,
});

export function updateProject(id: string, body: Partial<Omit<ProjectDraft, "template">>, keepalive = false) {
  return requestJson<Project>(`/api/studio/projects/${encodeURIComponent(id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    keepalive,
  });
}

let iconsPromise: Promise<string[]> | null = null;

export function listIcons(): Promise<string[]> {
  if (!iconsPromise) {
    iconsPromise = requestJson<string[]>("/api/studio/icons").catch((error) => {
      iconsPromise = null;
      throw error;
    });
  }
  return iconsPromise;
}

export const iconUrl = (name: string) => apiUrl(`/api/studio/icons/${encodeURIComponent(name)}.svg`);
export const assetUrl = (name: string) => apiUrl(`/assets/${encodeURIComponent(name)}`);

export const IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"];
const MAX_IMAGE_BYTES = 50 * 1024 * 1024;

export function isImageName(name: string) {
  const lower = name.toLowerCase();
  return IMAGE_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

/** Uploaded images (the workspace's assets that are pictures). */
export async function listImages(): Promise<AssetFile[]> {
  const files = await requestJson<{ assets?: AssetFile[] }>("/api/files");
  return (files.assets ?? []).filter((asset) => !asset.broken && !asset.outside && isImageName(asset.name));
}

function withSuffix(name: string, suffix: string) {
  const dot = name.lastIndexOf(".");
  return dot > 0 ? `${name.slice(0, dot)}-${suffix}${name.slice(dot)}` : `${name}-${suffix}`;
}

/**
 * Upload a picture and return the stored file name. A name that is already taken gets a short
 * suffix instead of replacing someone's earlier upload.
 */
export async function uploadImage(file: File): Promise<string> {
  if (!isImageName(file.name)) throw new Error("Please pick a picture (PNG, JPG, GIF, WebP or SVG).");
  if (file.size > MAX_IMAGE_BYTES) throw new Error("That picture is larger than 50 MB.");
  let name = file.name;
  for (let attempt = 0; attempt < 6; attempt += 1) {
    const body = new FormData();
    body.append("file", attempt === 0 ? file : new File([file], name, { type: file.type }));
    try {
      const result = await requestJson<{ filename?: string }>("/api/upload-asset", { method: "POST", body });
      return result.filename ?? name;
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 409) throw error;
      name = withSuffix(file.name, Math.random().toString(36).slice(2, 6));
    }
  }
  throw new Error("Couldn't find a free name for that picture. Try renaming the file.");
}
