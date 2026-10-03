import type { ManimColorName } from "./constants";
import { pythonString } from "./format";

export const SHAPES = [
  "Circle",
  "Square",
  "Rectangle",
  "Triangle",
  "Star",
  "Dot",
  "Line",
  "Arrow",
  "Text",
  "MathTex",
] as const;
export type ShapeKind = (typeof SHAPES)[number];

export const ENTRY_ANIMATIONS = ["Create", "Write", "FadeIn", "GrowFromCenter", "DrawBorderThenFill", "SpinInFromNothing", "none"] as const;
export const EMPHASIS_ANIMATIONS = ["none", "Indicate", "Circumscribe", "Wiggle", "Rotate", "ScaleUp", "Recolor"] as const;
export const EXIT_ANIMATIONS = ["FadeOut", "Uncreate", "ShrinkToCenter", "none"] as const;

export type EntryAnimation = (typeof ENTRY_ANIMATIONS)[number];
export type EmphasisAnimation = (typeof EMPHASIS_ANIMATIONS)[number];
export type ExitAnimation = (typeof EXIT_ANIMATIONS)[number];

export const ANIMATION_LABELS: Record<string, string> = {
  none: "None",
  GrowFromCenter: "Grow from center",
  DrawBorderThenFill: "Draw border, then fill",
  SpinInFromNothing: "Spin in",
  ScaleUp: "Scale up",
  Recolor: "Change color",
  ShrinkToCenter: "Shrink to center",
};

export interface ShapeOptions {
  shape: ShapeKind;
  variable: string;
  text: string;
  latex: string;
  color: ManimColorName;
  fill: boolean;
  scale: number;
  rotation: number;
  shiftX: number;
  shiftY: number;
  entry: EntryAnimation;
  emphasis: EmphasisAnimation;
  exit: ExitAnimation;
}

export const DEFAULT_SHAPE_OPTIONS: ShapeOptions = {
  shape: "Circle",
  variable: "",
  text: "Hello, Manim",
  latex: "a^2 + b^2 = c^2",
  color: "BLUE",
  fill: true,
  scale: 1,
  rotation: 0,
  shiftX: 0,
  shiftY: 0,
  entry: "Create",
  emphasis: "none",
  exit: "FadeOut",
};

const FILLABLE: ReadonlySet<ShapeKind> = new Set(["Circle", "Square", "Rectangle", "Triangle", "Star"]);

export function isFillable(shape: ShapeKind): boolean {
  return FILLABLE.has(shape);
}

export function defaultVariableName(shape: ShapeKind): string {
  if (shape === "Text") return "label";
  if (shape === "MathTex") return "equation";
  return shape.toLowerCase();
}

/** Coerce user input into a valid Python identifier. */
export function toIdentifier(input: string, fallback: string): string {
  const cleaned = input.trim().replace(/[^A-Za-z0-9_]/g, "_").replace(/^_+$/, "");
  if (!cleaned) return fallback;
  return /^\d/.test(cleaned) ? `_${cleaned}` : cleaned;
}

function num(value: number): string {
  return String(Math.round(value * 1000) / 1000);
}

function constructor(o: ShapeOptions): string {
  const color = `color=${o.color}`;
  switch (o.shape) {
    case "Circle":
      return `Circle(radius=1, ${color})`;
    case "Square":
      return `Square(side_length=2, ${color})`;
    case "Rectangle":
      return `Rectangle(width=3.5, height=2, ${color})`;
    case "Triangle":
      return `Triangle(${color})`;
    case "Star":
      return `Star(${color})`;
    case "Dot":
      return `Dot(radius=0.12, ${color})`;
    case "Line":
      return `Line(LEFT * 2, RIGHT * 2, ${color})`;
    case "Arrow":
      return `Arrow(LEFT * 2, RIGHT * 2, ${color})`;
    case "Text":
      return `Text(${pythonString(o.text || "Text")}, font_size=48, ${color})`;
    case "MathTex":
      return `MathTex(${pythonString(o.latex || "x", { raw: true })}, ${color})`;
  }
}

function shiftExpression(x: number, y: number): string | null {
  const parts: string[] = [];
  if (x) parts.push(`${x > 0 ? "RIGHT" : "LEFT"} * ${num(Math.abs(x))}`);
  if (y) parts.push(`${y > 0 ? "UP" : "DOWN"} * ${num(Math.abs(y))}`);
  return parts.length ? parts.join(" + ") : null;
}

/**
 * Python statements (unindented) that create, place, and animate one object.
 * Meant to be inserted into a Scene's construct() method.
 */
export function buildShapeCode(o: ShapeOptions): string {
  const name = toIdentifier(o.variable, defaultVariableName(o.shape));
  const lines: string[] = [];

  let definition = `${name} = ${constructor(o)}`;
  if (o.fill && isFillable(o.shape)) definition += `.set_fill(${o.color}, opacity=0.5)`;
  lines.push(definition);

  if (Number.isFinite(o.scale) && o.scale > 0 && o.scale !== 1) lines.push(`${name}.scale(${num(o.scale)})`);
  if (Number.isFinite(o.rotation) && o.rotation % 360 !== 0) lines.push(`${name}.rotate(${num(o.rotation)} * DEGREES)`);
  const shift = shiftExpression(Number.isFinite(o.shiftX) ? o.shiftX : 0, Number.isFinite(o.shiftY) ? o.shiftY : 0);
  if (shift) lines.push(`${name}.shift(${shift})`);

  lines.push(o.entry === "none" ? `self.add(${name})` : `self.play(${o.entry}(${name}))`);

  switch (o.emphasis) {
    case "Indicate":
    case "Circumscribe":
    case "Wiggle":
      lines.push(`self.play(${o.emphasis}(${name}))`);
      break;
    case "Rotate":
      lines.push(`self.play(Rotate(${name}, angle=PI / 2))`);
      break;
    case "ScaleUp":
      lines.push(`self.play(${name}.animate.scale(1.5))`);
      break;
    case "Recolor":
      lines.push(`self.play(${name}.animate.set_color(${o.color === "YELLOW" ? "PINK" : "YELLOW"}))`);
      break;
  }

  if (o.exit !== "none") lines.push(`self.play(${o.exit}(${name}))`);
  return lines.join("\n");
}
