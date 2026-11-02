export interface CropPosition { x: number; y: number; zoom: number }
export const RESET_CROP: CropPosition = { x: 0, y: 0, zoom: 1 };
const bound = (n: number) => Math.max(-1, Math.min(1, n));
/** Plain words for where the crop window sits, e.g. "Top left", "Center". */
export function cropPositionLabel(position: CropPosition) {
  const x = bound(position.x);
  const y = bound(position.y);
  const vertical = y <= -1 / 3 ? "top" : y >= 1 / 3 ? "bottom" : "";
  const horizontal = x <= -1 / 3 ? "left" : x >= 1 / 3 ? "right" : "";
  const label = [vertical, horizontal].filter(Boolean).join(" ");
  return label ? `${label[0].toUpperCase()}${label.slice(1)}` : "Center";
}
export function cropGeometry(width: number, height: number, ratio: number, position: CropPosition) {
  const sourceWidth = Math.min(width, height * ratio) / Math.max(1, Math.min(4, position.zoom));
  const sourceHeight = sourceWidth / ratio;
  return { width: sourceWidth, height: sourceHeight, x: (width - sourceWidth) * (bound(position.x) + 1) / 2, y: (height - sourceHeight) * (bound(position.y) + 1) / 2 };
}
export function cropRatio(shape: string | undefined, originalRatio: number) {
  if (shape === "circle") return 1;
  const match = shape?.match(/^([1-9]\d*):([1-9]\d*)$/);
  return match ? Number(match[1]) / Number(match[2]) : originalRatio;
}
/** Output stays at source resolution, with a 2048px ceiling to keep uploads small. */
export async function cropPhoto(image: HTMLImageElement, shape: string | undefined, ratio: number, position: CropPosition, name: string): Promise<File> {
  const rect = cropGeometry(image.naturalWidth, image.naturalHeight, ratio, position);
  const scale = Math.min(1, 2048 / Math.max(rect.width, rect.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(rect.width * scale));
  canvas.height = Math.max(1, Math.round(rect.height * scale));
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Couldn't prepare this photo. Please try again.");
  if (shape === "circle") {
    ctx.beginPath(); ctx.arc(canvas.width / 2, canvas.height / 2, Math.min(canvas.width, canvas.height) / 2, 0, Math.PI * 2); ctx.clip();
  }
  ctx.drawImage(image, rect.x, rect.y, rect.width, rect.height, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise<Blob>((resolve, reject) => canvas.toBlob((data) => data ? resolve(data) : reject(new Error("Couldn't crop this photo. Please try again.")), "image/png"));
  return new File([blob], `${name.replace(/\.[^.]+$/, "")}-crop.png`, { type: "image/png" });
}
