import * as shaders from "@paper-design/shaders-react";
import {
  DitheringShapes, DitheringTypes, DotGridShapes, GemSmokeShapes, GlassDistortionShapes,
  GlassGridShapes, GrainGradientShapes, HalftoneCmykTypes, HalftoneDotsGrids,
  HalftoneDotsTypes, LiquidMetalShapes, PulsingBorderAspectRatios, WarpPatterns,
} from "@paper-design/shaders";
import type { ComponentType } from "react";
import type { ShaderComponentProps } from "@paper-design/shaders-react";

export type ShaderValue = number | string | boolean | string[];
export type ShaderParams = Record<string, ShaderValue>;
export type Category = "Image filters" | "Logo animations" | "Effects";
export interface Preset { name: string; params: ShaderParams }
export interface ShaderRenderProps extends ShaderComponentProps {
  image: string;
  speed?: number;
  suspendWhenProcessingImage?: boolean;
}
export interface ShaderDefinition {
  id: string;
  name: string;
  category: Category;
  description: string;
  component: ComponentType<ShaderRenderProps>;
  presets: Preset[];
  animated: boolean;
}

function define(id: string, name: string, category: Category, description: string, component: ComponentType<ShaderRenderProps>, presets: readonly { name: string; params: object }[], overrides: ShaderParams = {}): ShaderDefinition {
  const items = presets.map((preset, index) => ({ name: preset.name, params: { ...preset.params, ...(index === 0 ? overrides : {}) } as ShaderParams }));
  return { id, name, category, description, component, presets: items, animated: Number(items[0].params.speed ?? 0) > 0 };
}

const grain = { grainMixer: 0.1, grainOverlay: 0.1 };

/** Original upstream effects and presets. Default overrides follow the supplied parameter notes. */
export const SHADERS: ShaderDefinition[] = [
  define("paper-texture", "Paper Texture", "Image filters", "Tactile fibers, soft folds, and beautifully imperfect paper.", shaders.PaperTexture, shaders.paperTexturePresets),
  define("fluted-glass", "Fluted Glass", "Image filters", "Refract a picture through sculpted, ribbed glass.", shaders.FlutedGlass, shaders.flutedGlassPresets, { ...grain, marginLeft: 0.1, marginRight: 0.1, marginTop: 0.1, marginBottom: 0.1 }),
  define("water", "Water", "Image filters", "Rippling surfaces, dancing highlights, and liquid caustics.", shaders.Water, shaders.waterPresets),
  define("image-dithering", "Image Dithering", "Image filters", "Turn a picture into a playful, limited-color print.", shaders.ImageDithering, shaders.imageDitheringPresets),
  define("halftone-dots", "Halftone Dots", "Image filters", "From inky dots to glowing pixels and soft mosaics.", shaders.HalftoneDots, shaders.halftoneDotsPresets),
  define("halftone-cmyk", "Halftone CMYK", "Image filters", "Four-color print with rich inks and newspaper textures.", shaders.HalftoneCmyk, shaders.halftoneCmykPresets, { ...grain, grainSize: 0.1 }),
  define("lens-distortion", "Lens Distortion", "Image filters", "Split light into prismatic layers and curved lenses.", shaders.LensDistortion, shaders.lensDistortionPresets, grain),
  define("heatmap", "Heatmap", "Logo animations", "Give a silhouette a flowing, thermal glow.", shaders.Heatmap, shaders.heatmapPresets),
  define("liquid-metal", "Liquid Metal", "Logo animations", "Polished, flowing chrome for your logo or a simple shape.", shaders.LiquidMetal, shaders.liquidMetalPresets),
  define("gem-smoke", "Gem Smoke", "Logo animations", "Wrap a shape in luminous, gem-like smoke.", shaders.GemSmoke, shaders.gemSmokePresets),
  define("mesh-gradient", "Mesh Gradient", "Effects", "Soft pools of color, always finding a new way to flow.", shaders.MeshGradient, shaders.meshGradientPresets, grain),
  define("static-mesh-gradient", "Static Mesh Gradient", "Effects", "Place and blend color into a still, expressive gradient.", shaders.StaticMeshGradient, shaders.staticMeshGradientPresets, grain),
  define("static-radial-gradient", "Static Radial Gradient", "Effects", "Sculpt concentric color with a movable focal point.", shaders.StaticRadialGradient, shaders.staticRadialGradientPresets, grain),
  define("dithering", "Dithering", "Effects", "Animated patterns with a crisp, pixelated character.", shaders.Dithering, shaders.ditheringPresets),
  define("grain-gradient", "Grain Gradient", "Effects", "Color and fine grain, mixed into organic forms.", shaders.GrainGradient, shaders.grainGradientPresets),
  define("dot-orbit", "Dot Orbit", "Effects", "A small universe of orbiting dots and shifting color.", shaders.DotOrbit, shaders.dotOrbitPresets),
  define("dot-grid", "Dot Grid", "Effects", "A precise grid of dots, diamonds, squares, or triangles.", shaders.DotGrid, shaders.dotGridPresets),
  define("warp", "Warp", "Effects", "Twist color into marbling, flowing ink, and liquid checks.", shaders.Warp, shaders.warpPresets),
  define("spiral", "Spiral", "Effects", "A single line unfolding into hypnotic geometry.", shaders.Spiral, shaders.spiralPresets),
  define("swirl", "Swirl", "Effects", "Bands of color turning around a shifting center.", shaders.Swirl, shaders.swirlPresets),
  define("waves", "Waves", "Effects", "Rhythmic lines, from smooth waves to sharp zigzags.", shaders.Waves, shaders.wavesPresets),
  define("neuro-noise", "Neuro Noise", "Effects", "A glowing network of fluid lines and intersections.", shaders.NeuroNoise, shaders.neuroNoisePresets),
  define("perlin-noise", "Perlin Noise", "Effects", "Layer organic noise into clouds, water, and terrain.", shaders.PerlinNoise, shaders.perlinNoisePresets),
  define("simplex-noise", "Simplex Noise", "Effects", "Smooth, rolling fields of stepped color.", shaders.SimplexNoise, shaders.simplexNoisePresets),
  define("voronoi", "Voronoi", "Effects", "Living cells, luminous bubbles, and crystalline edges.", shaders.Voronoi, shaders.voronoiPresets),
  define("pulsing-border", "Pulsing Border", "Effects", "A frame of light, with drifting color and soft pulses.", shaders.PulsingBorder, shaders.pulsingBorderPresets),
  define("metaballs", "Metaballs", "Effects", "Gooey blobs that drift, merge, and separate.", shaders.Metaballs, shaders.metaballsPresets),
  define("color-panels", "Color Panels", "Effects", "Translucent panels rotating through a spectrum of light.", shaders.ColorPanels, shaders.colorPanelsPresets),
  define("smoke-ring", "Smoke Ring", "Effects", "A ring of turbulent smoke with a luminous edge.", shaders.SmokeRing, shaders.smokeRingPresets),
  define("god-rays", "God Rays", "Effects", "Blooming shafts of light, from subtle haze to radiant bursts.", shaders.GodRays, shaders.godRaysPresets),
];

export const CATEGORIES: Category[] = ["Image filters", "Logo animations", "Effects"];
export const DEFAULT_IMAGE = "/shaders/flowers.webp";
export const getShader = (id: string) => SHADERS.find((shader) => shader.id === id);
export const cloneParams = (params: ShaderParams): ShaderParams => structuredClone(params);

export type Range = { min: number; max: number; step: number; unit: "%" | "°" | "" };
type RangeSpec = [number, number, ("%" | "°" | "")?, number?];
const commonRanges: Record<string, RangeSpec> = {
  speed: [0, 2], scale: [0.1, 4], rotation: [-360, 360, "°", 1], angle: [-360, 360, "°", 1],
  focalAngle: [0, 360, "°", 1], offsetX: [-1, 1], offsetY: [-1, 1], imageX: [-1, 1], imageY: [-1, 1],
  seed: [0, 1000, "", 1], shift: [-1, 1], shiftRed: [-1, 1], shiftBlue: [-1, 1],
  gainC: [-1, 1], gainM: [-1, 1], gainY: [-1, 1], gainK: [-1, 1],
  octaveCount: [1, 8, "", 1], lacunarity: [1.5, 10, "", 0.1],
  swirlIterations: [1, 20, "", 1], stepsPerColor: [1, 10, "", 1],
  noiseIterations: [1, 8, "", 1], crumpleCount: [2, 15, "", 1], positions: [0, 100, "", 1],
  bandCount: [0, 15, "", 1], spots: [1, 4, "", 1], noiseFrequency: [0, 2],
};
const ranges: Record<string, Record<string, RangeSpec>> = {
  "paper-texture": { scale: [0.3, 3], angle: [0, 360, "°", 1], distortion: [-1, 1] },
  "fluted-glass": { scale: [0.1, 3] },
  water: { scale: [0.1, 3], size: [0.01, 7] },
  "image-dithering": { scale: [0.1, 3], size: [0.1, 120, "", 0.1], colorSteps: [1, 7, "", 1] },
  "halftone-dots": { radius: [0, 2] },
  "halftone-cmyk": { size: [0.01, 1], contrast: [0, 2] },
  "lens-distortion": { scale: [0.1, 3], bias: [-1, 1], angle: [0, 360, "°", 1], count: [2, 50, "", 1], dispersionShift: [-1, 1], swirl: [-1, 1], lensBulge: [-1, 1], noiseFrequency: [0, 1] },
  heatmap: { speed: [0, 5], scale: [0.1, 2] },
  "liquid-metal": { speed: [0, 3], scale: [0, 4], repetition: [1, 10] },
  "gem-smoke": { speed: [0, 3], scale: [0, 4], offset: [-1, 1] },
  "mesh-gradient": { scale: [0.1, 5] },
  "static-mesh-gradient": { scale: [0.01, 10] },
  "static-radial-gradient": { scale: [0.01, 10], radius: [0, 3], focalDistance: [0, 3], falloff: [-1, 1], distortionFreq: [0, 40, "", 1] },
  dithering: { scale: [0, 4], size: [0.1, 120, "", 0.1] },
  "grain-gradient": { scale: [0, 4], rotation: [0, 360, "°", 1] },
  "dot-orbit": { scale: [0.1, 2], stepsPerColor: [1, 4, "", 1] },
  "dot-grid": { size: [0, 100, "", 1], gapX: [0, 1000, "", 1], gapY: [0, 1000, "", 1], strokeWidth: [0, 100, "", 1] },
  warp: { speed: [0, 10], scale: [0, 5], swirl: [0, 2], distortion: [0, 2], shapeScale: [0, 2] },
  spiral: { speed: [0, 5], scale: [0, 4], rotation: [0, 360, "°", 1] },
  swirl: { speed: [0, 5], scale: [0, 4] },
  waves: { scale: [0.01, 10], frequency: [0, 2], amplitude: [0, 10], spacing: [0, 10], shape: [0, 3] },
  "neuro-noise": { speed: [0, 10], scale: [0, 2] },
  "perlin-noise": { speed: [0, 3], scale: [0, 10] },
  "simplex-noise": { speed: [0, 10], scale: [0, 10] },
  voronoi: { scale: [0.1, 5], stepsPerColor: [1, 5, "", 1], gap: [0, 0.1, "%", 0.001], distortion: [0, 0.5] },
  "pulsing-border": { scale: [0, 1.5], rotation: [0, 360, "°", 1] },
  metaballs: { scale: [0, 4], size: [0.01, 1.25], count: [1, 20, "", 1] },
  "color-panels": { speed: [0, 4], scale: [0, 4], density: [0, 7], angle1: [-1, 1], angle2: [-1, 1], length: [0, 3], blur: [0, 0.5] },
  "smoke-ring": { speed: [0, 3], scale: [0, 2], innerShape: [0, 2], noiseScale: [0, 5] },
  "god-rays": { speed: [0, 4], scale: [0, 4], midSize: [0, 10] },
};

export function parameterRange(shader: ShaderDefinition, key: string): Range {
  const [min, max, unit = "%", step = 0.01] = ranges[shader.id]?.[key] ?? commonRanges[key] ?? [0, 1];
  return { min, max, unit, step };
}

const enums: Record<string, Record<string, object>> = {
  "fluted-glass": { shape: GlassGridShapes, distortionShape: GlassDistortionShapes },
  "image-dithering": { type: DitheringTypes },
  "halftone-dots": { type: HalftoneDotsTypes, grid: HalftoneDotsGrids },
  "halftone-cmyk": { type: HalftoneCmykTypes },
  "liquid-metal": { shape: LiquidMetalShapes }, "gem-smoke": { shape: GemSmokeShapes },
  dithering: { type: DitheringTypes, shape: DitheringShapes },
  "grain-gradient": { shape: GrainGradientShapes }, "dot-grid": { shape: DotGridShapes },
  warp: { shape: WarpPatterns }, "pulsing-border": { aspectRatio: PulsingBorderAspectRatios },
};
export function parameterOptions(shader: ShaderDefinition, key: string): string[] {
  if (key === "fit") return shader.category === "Image filters" ? ["contain", "cover"] : ["none", "contain", "cover"];
  return Object.keys(enums[shader.id]?.[key] ?? {});
}

const labels: Record<string, string> = {
  colorBack: "Background", colorFront: "Foreground", colorMid: "Tint", colorTint: "Tint", colorPaper: "Paper", colorShadow: "Shadow", colorHighlight: "Highlight",
  colorFill: "Fill", colorStroke: "Stroke", colorGlow: "Glow", colorGap: "Gap color", colorInner: "Inner", colorBloom: "Bloom color",
  colorC: "Cyan", colorM: "Magenta", colorY: "Yellow", colorK: "Black", gainC: "Cyan gain", gainM: "Magenta gain", gainY: "Yellow gain", gainK: "Black gain",
  floodC: "Cyan flood", floodM: "Magenta flood", floodY: "Yellow flood", floodK: "Black flood", grainMixer: "Mixing", grainOverlay: "Overlay", grainSize: "Grain size",
  clip: "Clip to image", octaveCount: "Octaves", spots: "Spot count", glow: "Inner glow", shiftRed: "Redshift", shiftBlue: "Blueshift", angle1: "Skew left", angle2: "Skew right",
  waveX: "Horizontal wave", waveXShift: "Horizontal shift", waveY: "Vertical wave", waveYShift: "Vertical shift", distortionFreq: "Frequency", noise: "Noise",
  imageX: "Position X", imageY: "Position Y", crumples: "Strength", crumpleCount: "Count", folds: "Strength", foldSizeX: "Size X", foldSizeY: "Size Y", foldOffsetX: "Offset X", foldOffsetY: "Offset Y", wrinkles: "Strength", wrinkleSize: "Size",
};
export function parameterLabel(key: string): string {
  return labels[key] ?? key.replace(/([A-Z])/g, " $1").replace(/^./, (c) => c.toUpperCase());
}

export function parameterGroup(key: string, shader: ShaderDefinition): string {
  if (key.startsWith("color")) return "Colors";
  if (key.startsWith("grain")) return "Grain";
  if (key.startsWith("margin") && key !== "margin") return "Margins";
  if (/^(fold|wrinkle|crumple)/.test(key)) return key.startsWith("fold") ? "Folds" : key.startsWith("wrinkle") ? "Wrinkles" : "Crumples";
  if (key.startsWith("gain")) return "Gain";
  if (key.startsWith("flood")) return "Flood";
  if (shader.id === "static-radial-gradient" && key.startsWith("distortion")) return "Distortion";
  if (["rotation", "offsetX", "offsetY"].includes(key)) return "Position";
  return "Parameters";
}

export function parameterKeys(shader: ShaderDefinition): string[] {
  const hidden = ["frame", "worldWidth", "worldHeight", "originX", "originY", "margin"];
  if (!shader.animated) hidden.push("speed");
  const keys = Object.keys(shader.presets[0].params).filter((key) => !hidden.includes(key));
  return [...(shader.animated ? ["speed"] : []), "scale", ...keys.filter((key) => key !== "speed" && key !== "scale")];
}
