import { expect, it, vi } from "vitest";
import { cropGeometry, cropPhoto, cropPositionLabel, cropRatio, RESET_CROP } from "./crop";

it("fits the slot, clamps pan/zoom, and never samples outside the original", () => {
  expect(cropRatio("circle", 2)).toBe(1); expect(cropRatio("16:9", 2)).toBe(16 / 9); expect(cropRatio(undefined, 2)).toBe(2);
  expect(cropGeometry(1200, 800, 1, RESET_CROP)).toEqual({ x: 200, y: 0, width: 800, height: 800 });
  expect(cropGeometry(1200, 800, 1, { x: 1, y: -1, zoom: 2 })).toEqual({ x: 800, y: 0, width: 400, height: 400 });
  for (const ratio of [.25, 1, 16 / 9, 4]) for (const x of [-2, 0, 2]) {
    const rect = cropGeometry(1200, 800, ratio, { x, y: -x, zoom: 4 });
    expect(rect.x).toBeGreaterThanOrEqual(0); expect(rect.y).toBeGreaterThanOrEqual(0);
    expect(rect.x + rect.width).toBeLessThanOrEqual(1200); expect(rect.y + rect.height).toBeLessThanOrEqual(800);
  }
});
it("keeps the saved crop convention so an existing crop reopens in the same place", () => {
  expect(cropGeometry(1200, 800, 1, { x: .5, y: -.5, zoom: 2 })).toEqual({ x: 600, y: 100, width: 400, height: 400 });
  expect(cropGeometry(1200, 800, 1, { x: -1, y: 1, zoom: 2 })).toEqual({ x: 0, y: 400, width: 400, height: 400 });
  expect(cropGeometry(1200, 800, 1, { x: 1, y: -1, zoom: 2 })).toEqual({ x: 800, y: 0, width: 400, height: 400 });
});
it("names where the crop window sits in plain words", () => {
  expect(cropPositionLabel({ x: 0, y: 0, zoom: 1 })).toBe("Center");
  expect(cropPositionLabel({ x: -1, y: -1, zoom: 1 })).toBe("Top left");
  expect(cropPositionLabel({ x: .8, y: .8, zoom: 4 })).toBe("Bottom right");
  expect(cropPositionLabel({ x: 0, y: -.5, zoom: 1 })).toBe("Top");
  expect(cropPositionLabel({ x: .5, y: 0, zoom: 1 })).toBe("Right");
  expect(cropPositionLabel({ x: 2, y: -2, zoom: 1 })).toBe("Top right");
});
it("exports a PNG using the selected source rectangle and circle clip", async () => {
  const ctx = { beginPath: vi.fn(), arc: vi.fn(), clip: vi.fn(), drawImage: vi.fn() };
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(ctx as unknown as CanvasRenderingContext2D);
  vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation((callback) => callback(new Blob(["crop"], { type: "image/png" })));
  const image = new Image(); Object.defineProperties(image, { naturalWidth: { value: 1200 }, naturalHeight: { value: 800 } });
  const file = await cropPhoto(image, "circle", 1, { x: 1, y: -1, zoom: 2 }, "portrait.jpg");
  expect(file.name).toBe("portrait-crop.png"); expect(file.type).toBe("image/png");
  expect(ctx.drawImage).toHaveBeenCalledWith(image, 800, 0, 400, 400, 0, 0, 400, 400);
  expect(ctx.clip).toHaveBeenCalledOnce();
});
