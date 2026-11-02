import { cloneParams, DEFAULT_IMAGE, getShader, parameterOptions, parameterRange, SHADERS, type ShaderDefinition, type ShaderParams } from "./catalog";

export const SHADER_DRAFT_KEY = "manim-studio:shaders:v1";
export const ASPECTS = { Landscape: [1280, 720], Square: [1080, 1080], Portrait: [720, 1280] } as const;
export type Aspect = keyof typeof ASPECTS;
export interface ShaderDraft {
  shader: string;
  preset: string;
  params: ShaderParams;
  image: string;
  logo: string;
  logoShape: string;
  aspect: Aspect;
}

export function newDraft(shader: ShaderDefinition): ShaderDraft {
  return { shader: shader.id, preset: "Default", params: cloneParams(shader.presets[0].params), image: DEFAULT_IMAGE, logo: "", logoShape: "diamond", aspect: "Landscape" };
}

function object(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

/** Imported settings can only address known controls and local/embedded pictures. */
function validSource(value: unknown): value is string {
  return typeof value === "string" && (value === "" || value === DEFAULT_IMAGE || /^\/assets\/[^?#]+$/.test(value) || /^data:image\/(png|jpeg|webp|gif|svg\+xml);base64,[a-z\d+/=\s]+$/i.test(value));
}

export function parseDraft(value: unknown): ShaderDraft {
  if (!object(value) || typeof value.shader !== "string") throw new Error("Choose a shader settings file saved by this app.");
  const shader = getShader(value.shader);
  if (!shader || !object(value.params)) throw new Error("That file contains an unknown shader.");
  const draft = newDraft(shader);
  for (const [key, defaultValue] of Object.entries(draft.params)) {
    const item = value.params[key];
    if (item === undefined) continue;
    if (typeof defaultValue === "number") {
      if (typeof item !== "number" || !Number.isFinite(item)) throw new Error(`Invalid value for ${key}.`);
      const range = parameterRange(shader, key);
      // Upstream presets sometimes exceed the slider's suggested range.
      const presetValues = shader.presets.map((preset) => Number(preset.params[key])).filter(Number.isFinite);
      if (key !== "frame" && (item < Math.min(range.min, ...presetValues) || item > Math.max(range.max, ...presetValues))) throw new Error(`The value for ${key} is outside its range.`);
      draft.params[key] = item;
    } else if (typeof defaultValue === "boolean" && typeof item === "boolean") draft.params[key] = item;
    else if (Array.isArray(defaultValue) && Array.isArray(item) && item.length > 0 && item.length <= 10 && item.every((color) => typeof color === "string" && /^#[\da-f]{6}([\da-f]{2})?$/i.test(color))) draft.params[key] = [...item];
    else if (typeof defaultValue === "string" && typeof item === "string" && (key.startsWith("color") ? /^#[\da-f]{6}([\da-f]{2})?$/i.test(item) : parameterOptions(shader, key).includes(item))) draft.params[key] = item;
    else throw new Error(`Invalid value for ${key}.`);
  }
  if (!validSource(value.image) || !validSource(value.logo)) throw new Error("That file contains an unsupported picture source.");
  draft.image = value.image;
  draft.logo = value.logo;
  draft.logoShape = ["diamond", "circle", "daisy", "metaballs", "none"].includes(String(value.logoShape)) ? String(value.logoShape) : "diamond";
  draft.aspect = typeof value.aspect === "string" && Object.hasOwn(ASPECTS, value.aspect) ? value.aspect as Aspect : "Landscape";
  draft.preset = shader.presets.some((preset) => preset.name === value.preset) ? String(value.preset) : "Custom";
  return draft;
}

export function readDraft(): ShaderDraft {
  try { const saved = localStorage.getItem(SHADER_DRAFT_KEY); if (saved) return parseDraft(JSON.parse(saved)); } catch { /* Invalid or unavailable storage starts a fresh draft. */ }
  return newDraft(SHADERS.find((shader) => shader.id === "mesh-gradient")!);
}

export function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  // Give WebView2 time to begin its download before revoking the URL.
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export function blobDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Couldn't read that picture."));
    reader.onload = () => resolve(String(reader.result));
    reader.readAsDataURL(blob);
  });
}

export async function portableDraft(draft: ShaderDraft): Promise<Blob> {
  const embed = async (source: string) => {
    if (!source || source === DEFAULT_IMAGE || source.startsWith("data:")) return source;
    const response = await fetch(source);
    if (!response.ok) throw new Error("Couldn't include the source picture. Try uploading it again.");
    // The asset API deliberately serves downloads as application/octet-stream.
    // A portable image needs its actual MIME type to be decoded after reopening.
    const extension = decodeURIComponent(source).split(".").pop()?.toLowerCase();
    const types: Record<string, string> = { png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", webp: "image/webp", gif: "image/gif", svg: "image/svg+xml" };
    const blob = await response.blob();
    return blobDataUrl(new Blob([blob], { type: types[extension ?? ""] ?? blob.type }));
  };
  const category = getShader(draft.shader)?.category;
  const [image, logo] = await Promise.all([category === "Image filters" ? embed(draft.image) : DEFAULT_IMAGE, category === "Logo animations" ? embed(draft.logo) : ""]);
  return new Blob([JSON.stringify({ format: "manim-shader", version: 1, ...draft, image, logo }, null, 2)], { type: "application/json" });
}

export function canvasPng(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error("Couldn't capture the preview. Please try again.")), "image/png"));
}

/** Heatmap accepts a mask rather than a shape enum. The other two logo effects have native shapes. */
export function heatmapShape(shape: string): string {
  const path = shape === "circle" ? '<circle cx="128" cy="128" r="84"/>'
    : shape === "daisy" ? '<path d="M128 30C155 0 174 48 172 67C218 48 240 90 212 116C256 140 232 183 194 180C210 224 166 249 141 215C117 258 75 233 78 195C32 212 9 168 43 143C1 119 26 77 64 80C47 35 91 11 116 45Z"/>'
    : shape === "metaballs" ? '<circle cx="99" cy="104" r="58"/><circle cx="156" cy="146" r="63"/>'
    : shape === "none" ? '<rect width="256" height="256"/>' : '<path d="M128 22L234 128L128 234L22 128Z"/>';
  return `data:image/svg+xml;base64,${btoa(`<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256" fill="black">${path}</svg>`)}`;
}
