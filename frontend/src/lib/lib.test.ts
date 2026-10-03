import { describe, expect, it, vi } from "vitest";

import { ApiError, apiUrl, errorMessage, OFFLINE_MESSAGE, postJson, requestJson, wsUrl } from "./api";
import {
  assetKind,
  assetUsageSnippet,
  classNameFromFile,
  formatBytes,
  formatDuration,
  formatRelativeTime,
  pythonString,
  toScriptName,
  validateScriptName,
} from "./format";
import { findErrorLocation, findLineReference } from "./logs";
import { overallPercent, stepSeconds } from "./progress";
import { buildShapeCode, DEFAULT_SHAPE_OPTIONS, defaultVariableName, isFillable, toIdentifier } from "./shapeBuilder";
import { BROWSER_STARTER, BROWSER_STARTER_NAME, loadBrowserFiles, readStored, saveBrowserFiles, STORAGE_KEYS, writeStored } from "./storage";
import { newSceneCode, SCENE_TEMPLATES } from "./templates";
import type { ActiveRender } from "@/hooks/useRenderSession";

describe("format", () => {
  it("normalizes and validates script names", () => {
    expect(toScriptName("  intro ")).toBe("intro.py");
    expect(toScriptName("Intro.PY")).toBe("Intro.PY");

    expect(validateScriptName("intro.py")).toBeNull();
    expect(validateScriptName(".py")).toBe("Enter a file name.");
    expect(validateScriptName("a/b.py")).toMatch(/can't contain/);
    expect(validateScriptName("tab\there.py")).toMatch(/can't contain/);
    expect(validateScriptName(" lead.py")).toMatch(/start or end/);
    expect(validateScriptName("dot..py")).toMatch(/start or end/);
    expect(validateScriptName("con.py")).toMatch(/reserved/);
    expect(validateScriptName("Intro.py", ["intro.py"])).toBe("Intro.py already exists.");
  });

  it("derives class names from file names", () => {
    expect(classNameFromFile("orbit_demo.py")).toBe("OrbitDemo");
    expect(classNameFromFile("3d plot.py")).toBe("Scene3dPlot");
    expect(classNameFromFile("___.py")).toBe("NewScene");
  });

  it("formats sizes, durations, and relative times", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(25 * 1024 * 1024)).toBe("25 MB");
    expect(formatBytes(-1)).toBe("—");

    expect(formatDuration(2)).toBe("2s");
    expect(formatDuration(1.5)).toBe("1.5s");
    expect(formatDuration(75)).toBe("1m 15s");

    const now = 1_000_000_000_000;
    expect(formatRelativeTime(now / 1000 - 10, now)).toBe("just now");
    expect(formatRelativeTime(now / 1000 - 300, now)).toBe("5m ago");
    expect(formatRelativeTime(now / 1000 - 7200, now)).toBe("2h ago");
    expect(formatRelativeTime(now / 1000 - 3 * 86400, now)).toBe("3d ago");
    expect(formatRelativeTime(now / 1000 - 90 * 86400, now)).toMatch(/\d/);
  });

  it("builds Python string literals", () => {
    expect(pythonString("hi")).toBe('"hi"');
    expect(pythonString('say "hi"\n')).toBe('"say \\"hi\\"\\n"');
    expect(pythonString("\\frac{a}{b}", { raw: true })).toBe('r"\\frac{a}{b}"');
    expect(pythonString('a"b', { raw: true })).toBe("r'a\"b'");
    expect(pythonString("x \\", { raw: true })).toBe('"x \\\\"');
    expect(pythonString(`a"b'c`, { raw: true })).toBe('"a\\"b\'c"');
  });

  it("classifies assets and suggests code to load them", () => {
    expect(assetKind("logo.SVG")).toBe("vector");
    expect(assetKind("photo.jpeg")).toBe("image");
    expect(assetKind("beep.wav")).toBe("audio");
    expect(assetKind("font.otf")).toBe("font");
    expect(assetKind("data.bin")).toBe("other");

    expect(assetUsageSnippet("logo.svg")).toBe('SVGMobject("assets/logo.svg")');
    expect(assetUsageSnippet("photo.png")).toBe('ImageMobject("assets/photo.png")');
    expect(assetUsageSnippet("beep.mp3")).toBe('self.add_sound("assets/beep.mp3")');
    expect(assetUsageSnippet("font.ttf")).toBe('"assets/font.ttf"');
  });
});

describe("logs", () => {
  it("finds line references only for the given files", () => {
    expect(findLineReference('  File "/w/example.py", line 12, in construct', ["example.py"])).toBe(12);
    expect(findLineReference("│ /w/example.py:7 in construct │", ["example.py"])).toBe(7);
    expect(findLineReference("C:\\work\\example.py:9 in construct", ["example.py"])).toBe(9);
    expect(findLineReference("/site-packages/manim/scene.py:259 in render", ["example.py"])).toBeNull();
    expect(findLineReference("my_example.py:3", ["example.py"])).toBeNull();
    expect(findLineReference("anything", ["", "x.py"])).toBeNull();
  });

  it("finds the failing line and exception message", () => {
    const output = [
      "│ /lib/manim/scene.py:259 in render │",
      "│ /w/example.py:7 in construct │",
      "│ ❱ 7 │ undefined_name() │",
      "╰──────────╯",
      "NameError: name 'undefined_name' is not defined",
    ];
    expect(findErrorLocation(output, ["example.py"])).toEqual({ line: 7, message: "NameError: name 'undefined_name' is not defined" });
    expect(findErrorLocation(["│ /w/example.py:3 in construct │"], ["example.py"])).toEqual({ line: 3, message: "Error" });
    expect(findErrorLocation(["nothing useful"], ["example.py"])).toBeNull();
  });
});

describe("progress", () => {
  const render = (progress: ActiveRender["progress"]): ActiveRender => ({
    id: "r",
    request: { filename: "a.py", scene: "A", quality: "l", useOpenGL: false, downloadOnly: false },
    progress,
    startedAt: 0,
  });

  it("estimates overall progress from per-animation progress", () => {
    expect(overallPercent(render(null), 4)).toBeNull();
    expect(overallPercent(render({ percent: 40 }), 4)).toBe(40);
    expect(overallPercent(render({ percent: 50, animation: 1 }), 4)).toBe(38);
    expect(overallPercent(render({ percent: 100, animation: 3 }), 4)).toBe(100);
    // More animations than the static count (loops): never exceed 100.
    expect(overallPercent(render({ percent: 50, animation: 9 }), 4)).toBe(95);
    expect(overallPercent(render({ percent: 70, animation: 2 }), 0)).toBe(70);
  });

  it("assumes one second for steps without a literal duration", () => {
    expect(stepSeconds({ type: "wait", label: "", line: 1, duration: 2.5 })).toBe(2.5);
    expect(stepSeconds({ type: "wait", label: "", line: 1, duration: "t" })).toBe(1);
    expect(stepSeconds({ type: "play", label: "", line: 1 })).toBe(1);
  });
});

describe("shape builder", () => {
  it("generates a complete snippet", () => {
    const code = buildShapeCode({
      ...DEFAULT_SHAPE_OPTIONS,
      shape: "Square",
      color: "RED",
      scale: 1.5,
      rotation: 45,
      shiftX: -2,
      shiftY: 1,
      emphasis: "Indicate",
      exit: "Uncreate",
    });
    expect(code.split("\n")).toEqual([
      "square = Square(side_length=2, color=RED).set_fill(RED, opacity=0.5)",
      "square.scale(1.5)",
      "square.rotate(45 * DEGREES)",
      "square.shift(LEFT * 2 + UP * 1)",
      "self.play(Create(square))",
      "self.play(Indicate(square))",
      "self.play(Uncreate(square))",
    ]);
  });

  it("handles text, LaTeX, static objects, and every emphasis", () => {
    const text = buildShapeCode({ ...DEFAULT_SHAPE_OPTIONS, shape: "Text", text: 'Say "hi"', entry: "Write", exit: "none" });
    expect(text).toBe('label = Text("Say \\"hi\\"", font_size=48, color=BLUE)\nself.play(Write(label))');

    const tex = buildShapeCode({ ...DEFAULT_SHAPE_OPTIONS, shape: "MathTex", latex: "\\pi", entry: "none", exit: "none", variable: "my eq" });
    expect(tex).toBe('my_eq = MathTex(r"\\pi", color=BLUE)\nself.add(my_eq)');

    const emphasis = (value: (typeof DEFAULT_SHAPE_OPTIONS)["emphasis"], color = DEFAULT_SHAPE_OPTIONS.color) =>
      buildShapeCode({ ...DEFAULT_SHAPE_OPTIONS, shape: "Dot", emphasis: value, color, exit: "none" }).split("\n").at(-1);
    expect(emphasis("Rotate")).toBe("self.play(Rotate(dot, angle=PI / 2))");
    expect(emphasis("ScaleUp")).toBe("self.play(dot.animate.scale(1.5))");
    expect(emphasis("Recolor")).toBe("self.play(dot.animate.set_color(YELLOW))");
    expect(emphasis("Recolor", "YELLOW")).toBe("self.play(dot.animate.set_color(PINK))");
    expect(emphasis("Wiggle")).toBe("self.play(Wiggle(dot))");

    for (const shape of ["Circle", "Rectangle", "Triangle", "Star", "Line", "Arrow"] as const) {
      expect(buildShapeCode({ ...DEFAULT_SHAPE_OPTIONS, shape })).toContain(`${shape}(`);
    }
  });

  it("ignores invalid transforms and sanitizes names", () => {
    const code = buildShapeCode({ ...DEFAULT_SHAPE_OPTIONS, scale: Number.NaN, rotation: 360, shiftX: Number.NaN, shiftY: 0, fill: false });
    expect(code).toBe("circle = Circle(radius=1, color=BLUE)\nself.play(Create(circle))\nself.play(FadeOut(circle))");
    expect(toIdentifier("2 fast", "x")).toBe("_2_fast");
    expect(toIdentifier("___", "fallback")).toBe("fallback");
    expect(defaultVariableName("Arrow")).toBe("arrow");
    expect(isFillable("Line")).toBe(false);
  });
});

describe("storage", () => {
  it("round-trips values and migrates legacy keys", () => {
    writeStored(STORAGE_KEYS.quality, "h");
    expect(readStored(STORAGE_KEYS.quality, "m")).toBe("h");
    expect(readStored("missing", 42)).toBe(42);

    localStorage.setItem("manim_composer_auto_save_on_render", "false");
    expect(readStored(STORAGE_KEYS.autoSave, true)).toBe(false);
    localStorage.setItem("manim_composer_storage_location", "backend");
    expect(readStored(STORAGE_KEYS.storageMode, "disk")).toBe("disk");

    localStorage.setItem(STORAGE_KEYS.loopPreview, "{not json");
    expect(readStored(STORAGE_KEYS.loopPreview, true)).toBe(true);
  });

  it("seeds and saves browser scripts", () => {
    expect(loadBrowserFiles()).toEqual({ [BROWSER_STARTER_NAME]: BROWSER_STARTER });
    expect(saveBrowserFiles({ "a.py": "x" })).toBe(true);
    expect(loadBrowserFiles()).toEqual({ "a.py": "x" });

    localStorage.setItem("manim_composer_browser_files", JSON.stringify({ "legacy.py": "y" }));
    localStorage.removeItem(STORAGE_KEYS.browserFiles);
    expect(loadBrowserFiles()).toEqual({ "legacy.py": "y" });
  });

  it("survives storage that throws", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("full", "QuotaExceededError");
    });
    expect(() => writeStored("k", 1)).not.toThrow();
    expect(saveBrowserFiles({ "a.py": "x" })).toBe(false);
  });
});

describe("api", () => {
  it("builds URLs against the current origin", () => {
    expect(apiUrl("/api/files")).toBe("/api/files");
    expect(apiUrl("media/x.mp4")).toBe("/media/x.mp4");
    expect(apiUrl("blob:http://x/1")).toBe("blob:http://x/1");
    expect(wsUrl("/api/render")).toBe("ws://localhost:3000/api/render".replace("localhost:3000", window.location.host));
  });

  it("surfaces server error details and network failures", async () => {
    globalThis.fetch = vi.fn().mockResolvedValueOnce({ ok: false, status: 413, json: async () => ({ detail: "Too big" }) });
    await expect(requestJson("/api/save")).rejects.toMatchObject({ message: "Too big", status: 413 });

    globalThis.fetch = vi.fn().mockResolvedValueOnce({ ok: false, status: 502, json: async () => Promise.reject(new Error("html")) });
    await expect(requestJson("/api/save")).rejects.toThrow("Request failed (HTTP 502).");

    globalThis.fetch = vi.fn().mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await expect(postJson("/api/save", { a: 1 })).rejects.toThrow(OFFLINE_MESSAGE);

    globalThis.fetch = vi.fn().mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ ok: 1 }) });
    await expect(postJson("/api/install-manim")).resolves.toEqual({ ok: 1 });
    expect(vi.mocked(globalThis.fetch).mock.calls[0][1]).toMatchObject({ method: "POST", body: undefined });

    expect(errorMessage(new ApiError("Nope", 400))).toBe("Nope");
    expect(errorMessage("weird", "Fallback")).toBe("Fallback");
  });
});

describe("templates", () => {
  it("defines renderable scenes with matching file names", () => {
    for (const template of SCENE_TEMPLATES) {
      expect(template.code).toMatch(/^from manim import \*/);
      expect(template.code).toMatch(/class \w+\(\w*Scene\):/);
      expect(template.filename).toMatch(/^[a-z0-9_]+\.py$/);
    }
    expect(newSceneCode("Orbit")).toContain("class Orbit(Scene):");
  });
});
