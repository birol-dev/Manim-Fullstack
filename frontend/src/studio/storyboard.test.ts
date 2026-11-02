import { describe, expect, it } from "vitest";

import { fitStoryboard, spokenDuration } from "./storyboard";

describe("storyboard fit", () => {
  it("uses three substantial columns for a nine-frame wide video", () => {
    const fit = fitStoryboard(9, 16 / 9, 1000, 730);
    expect(fit.columns).toBe(3);
    expect(fit.rows).toBe(3);
    expect(fit.frameWidth).toBeGreaterThan(300);
  });

  it.each([16 / 9, 9 / 16, 1, 4 / 5])("maximizes frame size within both dimensions at aspect %s", (ratio) => {
    for (const count of [1, 4, 9]) {
      for (const [width, height] of [[1000, 730], [342, 320]]) {
        const fit = fitStoryboard(count, ratio, width, height);
        expect(fit.frameWidth).toBeLessThanOrEqual(360);
        expect(fit.width).toBeLessThanOrEqual(width - 32 + 0.001);
        expect(fit.rows * (fit.frameWidth / ratio + 27) + (fit.rows - 1) * 16).toBeLessThanOrEqual(height - 64 + 0.001);
        for (let columns = 1; columns <= count; columns++) {
          const rows = Math.ceil(count / columns);
          const candidate = Math.max(0, Math.min(360, (width - 32 - (columns - 1) * 16) / columns, (height - 64 - (rows - 1) * 16 - rows * 27) / rows * ratio));
          expect(fit.frameWidth).toBeGreaterThanOrEqual(candidate);
        }
      }
    }
  });

  it.each([[305, "5 min 5 s"], [120, "2 min"], [90, "1 min 30 s"], [60, "1 min"], [119.9, "2 min"], [17.03, "17 seconds"], [10.9, "11 seconds"], [7.54, "7.5 seconds"], [7, "7 seconds"], [1, "1 second"]])("speaks %s naturally", (value, expected) => {
    expect(spokenDuration(value as number)).toBe(expected);
  });

  // The preview area of the 900–1199px split at 1000x680, 1093x614 and 900x680.
  it.each([[616, 484], [709, 418], [516, 484]])("keeps nine frames readable in a %sx%s preview", (width, height) => {
    const fit = fitStoryboard(9, 16 / 9, width, height);
    expect(fit.columns).toBe(3);
    expect(fit.frameWidth).toBeGreaterThanOrEqual(140);
    expect(fit.width).toBeLessThanOrEqual(width - 32 + 0.001);
  });
});
