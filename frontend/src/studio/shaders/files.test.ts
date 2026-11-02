import { beforeEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_IMAGE, getShader, parameterKeys, parameterRange, SHADERS } from "./catalog";
import { heatmapShape, newDraft, parseDraft, portableDraft, readDraft, SHADER_DRAFT_KEY } from "./files";

beforeEach(() => localStorage.clear());

describe("the supplied shader collection", () => {
  it("includes every referenced shader and its real upstream presets", () => {
    expect(SHADERS.map((shader) => shader.name)).toEqual([
      "Paper Texture", "Fluted Glass", "Water", "Image Dithering", "Halftone Dots", "Halftone CMYK", "Lens Distortion",
      "Heatmap", "Liquid Metal", "Gem Smoke", "Mesh Gradient", "Static Mesh Gradient", "Static Radial Gradient", "Dithering",
      "Grain Gradient", "Dot Orbit", "Dot Grid", "Warp", "Spiral", "Swirl", "Waves", "Neuro Noise", "Perlin Noise",
      "Simplex Noise", "Voronoi", "Pulsing Border", "Metaballs", "Color Panels", "Smoke Ring", "God Rays",
    ]);
    for (const shader of SHADERS) {
      expect(shader.presets[0].name).toBe("Default");
      expect(shader.presets.length).toBeGreaterThanOrEqual(shader.id === "heatmap" ? 2 : 4);
      if (shader.animated) expect(parameterKeys(shader).slice(0, 2)).toEqual(["speed", "scale"]);
    }
    expect(getShader("warp")!.presets.map((preset) => preset.name)).toEqual(["Default", "Cauldron Pot", "Live Ink", "Kelp", "Nectar", "Passion"]);
    expect(getShader("paper-texture")!.presets.map((preset) => preset.name)).toEqual(["Default", "Spread", "Creased", "Flat"]);
  });

  it("uses the reference defaults and units, including grouped controls", () => {
    const paper = getShader("paper-texture")!;
    expect(newDraft(paper).params).toMatchObject({ scale: 0.9, seed: 4, angle: 300, distortion: 0.75, crumples: 0, crumpleCount: 6 });
    expect(newDraft(getShader("fluted-glass")!).params).toMatchObject({ grainMixer: 0.1, grainOverlay: 0.1, marginLeft: 0.1, marginBottom: 0.1 });
    expect(parameterRange(paper, "distortion")).toMatchObject({ min: -1, max: 1, unit: "%" });
    expect(parameterRange(paper, "angle")).toMatchObject({ min: 0, max: 360, unit: "°" });
    expect(parameterRange(getShader("image-dithering")!, "size")).toMatchObject({ min: 0.1, max: 120, unit: "" });
  });
});

describe("portable settings and drafts", () => {
  it("embeds downloadable images with the correct MIME type so the file can reopen", async () => {
    const draft = { ...newDraft(getShader("water")!), image: "/assets/photo.webp", logo: "/assets/unrelated.svg" };
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true, blob: async () => new Blob(["image"], { type: "application/octet-stream" }) } as Response);
    const blob = await portableDraft(draft);
    const content = await new Promise<string>((resolve) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.readAsText(blob); });
    const saved = JSON.parse(content);
    expect(saved.image).toMatch(/^data:image\/webp;base64,/);
    expect(saved.logo).toBe("");
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(parseDraft(saved).image).toBe(saved.image);
    fetch.mockRestore();
  });
  it("round-trips all presets without discarding alpha, shapes, or unusual preset values", () => {
    for (const shader of SHADERS) for (const preset of shader.presets) {
      const draft = { ...newDraft(shader), preset: preset.name, params: preset.params };
      expect(parseDraft(JSON.parse(JSON.stringify(draft)))).toEqual(draft);
    }
  });

  it("starts with defaults when storage is missing or corrupt and restores valid edits", () => {
    expect(readDraft().shader).toBe("mesh-gradient");
    localStorage.setItem(SHADER_DRAFT_KEY, "invalid");
    expect(readDraft().shader).toBe("mesh-gradient");
    const draft = newDraft(getShader("water")!);
    draft.params.speed = 0.45; draft.image = "/assets/my%20photo.png";
    localStorage.setItem(SHADER_DRAFT_KEY, JSON.stringify(draft));
    expect(readDraft()).toEqual(draft);
  });

  it("rejects untrusted sources, unknown shaders, and invalid control values", () => {
    const draft = newDraft(getShader("mesh-gradient")!);
    expect(() => parseDraft({ ...draft, shader: "unknown" })).toThrow(/unknown shader/);
    expect(() => parseDraft({ ...draft, image: "https://example.com/tracker.png" })).toThrow(/picture source/);
    expect(() => parseDraft({ ...draft, logo: "javascript:alert(1)" })).toThrow(/picture source/);
    for (const params of [{ speed: Infinity }, { distortion: "high" }, { colors: ["red"] }, { scale: 100000 }, { fit: "unexpected" }]) {
      expect(() => parseDraft({ ...draft, params: { ...draft.params, ...params } })).toThrow();
    }
    expect(parseDraft({ ...draft, aspect: "__proto__" }).aspect).toBe("Landscape");
    expect(parseDraft({ ...draft, params: { ...draft.params, onClick: "untrusted" } }).params).not.toHaveProperty("onClick");
  });

  it("keeps embedded pictures and supplies defaults for newly added controls", () => {
    const draft = newDraft(getShader("paper-texture")!);
    const image = "data:image/png;base64,aGVsbG8=";
    const parsed = parseDraft({ ...draft, image, params: { seed: 15 }, aspect: "Square" });
    expect(parsed.image).toBe(image);
    expect(parsed.params).toMatchObject({ seed: 15, crumples: 0, scale: 0.9 });
    expect(parsed.aspect).toBe("Square");
    expect(newDraft(getShader("water")!).image).toBe(DEFAULT_IMAGE);
    expect(heatmapShape("circle")).toMatch(/^data:image\/svg\+xml;base64,/);
  });
});
