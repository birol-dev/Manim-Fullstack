/**
 * Backend location. By default the app talks to the server that served it (the
 * Vite dev server proxies /api, /media and /assets). Set VITE_BACKEND_URL to
 * point a separately hosted frontend at another backend.
 */
function normalizeBase(raw: string | undefined): string {
  const value = raw?.trim();
  if (!value) return "";
  const withScheme = /^https?:\/\//i.test(value) ? value : `http://${value}`;
  return withScheme.replace(/\/+$/, "");
}

export const API_BASE = normalizeBase(import.meta.env.VITE_BACKEND_URL);

/** Absolute URL for a backend path such as "/media/videos/x.mp4". */
export function apiUrl(path: string): string {
  if (/^(https?:|blob:|data:)/i.test(path)) return path;
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

export function wsUrl(path: string): string {
  const base = API_BASE || window.location.origin;
  return `${base.replace(/^http/i, "ws")}${path}`;
}

export class ApiError extends Error {
  readonly status: number;
  /** The parsed JSON error body, when there was one (e.g. a 412's current_version). */
  readonly body: unknown;
  /** The response's ETag header, when there was one. */
  readonly etag: string | null;

  constructor(message: string, status: number, body: unknown = null, etag: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
    this.etag = etag;
  }
}

export const OFFLINE_MESSAGE = "Can't reach the Manim Composer server. Is it running?";

export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(apiUrl(path), init);
  } catch {
    throw new ApiError(OFFLINE_MESSAGE, 0);
  }

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // Non-JSON bodies are only expected on errors; handled below.
  }

  if (!response.ok) {
    const detail = (body as { detail?: unknown } | null)?.detail;
    throw new ApiError(
      typeof detail === "string" && detail ? detail : `Request failed (HTTP ${response.status}).`,
      response.status,
      body,
      response.headers?.get?.("ETag") ?? null,
    );
  }
  return body as T;
}

export function postJson<T>(path: string, data?: unknown): Promise<T> {
  return requestJson<T>(path, {
    method: "POST",
    headers: data === undefined ? undefined : { "Content-Type": "application/json" },
    body: data === undefined ? undefined : JSON.stringify(data),
  });
}

export function deleteRequest<T>(path: string, params: Record<string, string>): Promise<T> {
  return requestJson<T>(`${path}?${new URLSearchParams(params)}`, { method: "DELETE" });
}

export function errorMessage(error: unknown, fallback = "Something went wrong."): string {
  return error instanceof Error && error.message ? error.message : fallback;
}
