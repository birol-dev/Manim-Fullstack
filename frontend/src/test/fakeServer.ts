import { vi } from "vitest";

import type { AnimationStep, AssetFile, Diagnostics, MediaFile, ParseResult } from "@/lib/types";

export const DIAGNOSTICS: Diagnostics = {
  platform: "Linux",
  python_version: "3.12.1",
  profile: "balanced",
  description: "Standard system configuration.",
  preview_quality: "720p30",
  default_fps: 30,
  default_resolution: "1280x720",
  recommended_threads: 7,
  opengl_supported: false,
  hardware: {
    cpu: { model: "Test CPU 9000", physical_cores: 4, logical_threads: 8 },
    ram_gb: 16,
    gpu: { devices: [{ name: "Test GPU", vram: "8 GB", type: "NVIDIA" }], has_cuda: true },
  },
  dependencies: {
    manim: "/usr/bin/manim",
    ffmpeg: "/usr/bin/ffmpeg",
    latex: "/usr/bin/latex",
    dvisvgm: "/usr/bin/dvisvgm",
    latex_available: true,
  },
};

export const EXAMPLE_CODE = `from manim import *


class Intro(Scene):
    def construct(self):
        self.play(Create(Circle()))
        self.wait(2)


class Outro(Scene):
    def construct(self):
        self.play(FadeOut(Square()), run_time=0.5)
`;

/** Rough stand-in for the backend's AST parser. */
export function parseScenes(code: string): ParseResult {
  const scenes: string[] = [];
  const animations: Record<string, AnimationStep[]> = {};
  let current: string | null = null;
  code.split("\n").forEach((text, index) => {
    const scene = /^class (\w+)\(\w*Scene\)/.exec(text);
    if (scene) {
      current = scene[1];
      scenes.push(current);
      return;
    }
    if (!current) return;
    const play = /self\.play\((.*?)(?:, run_time=([\d.]+))?\)$/.exec(text.trim());
    const wait = /self\.wait\(([\d.]*)\)/.exec(text);
    const steps = (animations[current] ??= []);
    if (play) {
      steps.push({ type: "play", label: play[1], line: index + 1, ...(play[2] ? { duration: Number(play[2]) } : {}) });
    } else if (wait) {
      const duration = wait[1] ? Number(wait[1]) : 1;
      steps.push({ type: "wait", label: `Wait ${duration}s`, line: index + 1, duration });
    }
  });
  for (const key of Object.keys(animations)) if (animations[key].length === 0) delete animations[key];
  return { scenes, animations };
}

export interface FakeServer {
  scripts: Record<string, string>;
  assets: AssetFile[];
  media: MediaFile[];
  diagnostics: Diagnostics;
  offline: boolean;
  /** Paths to fail with a 500 and this detail message. */
  failures: Record<string, string>;
  calls: Array<{ method: string; path: string; body: unknown }>;
  fetch: ReturnType<typeof vi.fn>;
}

function response(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    blob: async () => new Blob(["video-bytes"], { type: "video/mp4" }),
  } as unknown as Response;
}

export function media(scene: string, overrides: Partial<MediaFile> = {}): MediaFile {
  const path = `videos/example/720p30/${scene}.mp4`;
  return {
    name: `${scene}.mp4`,
    size: 2048,
    type: "video",
    url: `/media/${path}`,
    path,
    script: "example",
    scene,
    quality: "720p30",
    modified: Date.now() / 1000 - 120,
    ...overrides,
  };
}

/** Install a fetch mock that behaves like the FastAPI backend, backed by memory. */
export function installFakeServer(overrides: Partial<Pick<FakeServer, "scripts" | "assets" | "media" | "diagnostics">> = {}): FakeServer {
  const server: FakeServer = {
    scripts: overrides.scripts ?? { "example.py": EXAMPLE_CODE, "notes.py": "class Notes(Scene):\n    pass\n" },
    assets: overrides.assets ?? [],
    media: overrides.media ?? [],
    diagnostics: overrides.diagnostics ?? structuredClone(DIAGNOSTICS),
    offline: false,
    failures: {},
    calls: [],
    fetch: vi.fn(),
  };

  server.fetch.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const method = (init?.method ?? "GET").toUpperCase();
    let body: unknown = undefined;
    if (typeof init?.body === "string") body = JSON.parse(init.body);
    else if (init?.body instanceof FormData) body = init.body;
    server.calls.push({ method, path: url.pathname, body });

    if (server.offline) throw new TypeError("Failed to fetch");
    if (server.failures[url.pathname]) return response(500, { detail: server.failures[url.pathname] });

    const json = body as Record<string, string> | undefined;
    const param = (name: string) => url.searchParams.get(name) ?? "";

    switch (`${method} ${url.pathname}`) {
      case "GET /api/diagnostics":
        return response(200, server.diagnostics);
      case "GET /api/files":
        return response(200, {
          scripts: Object.entries(server.scripts)
            .map(([name, code]) => ({ name, size: code.length, type: "script" }))
            .sort((a, b) => a.name.localeCompare(b.name)),
          assets: server.assets,
          media: server.media,
        });
      case "GET /api/file-content": {
        const name = param("filename");
        if (!(name in server.scripts)) return response(404, { detail: "Python script not found." });
        return response(200, { filename: name, code: server.scripts[name], ...parseScenes(server.scripts[name]) });
      }
      case "POST /api/parse-code":
        return response(200, { success: true, ...parseScenes(json!.code) });
      case "POST /api/save":
        server.scripts[json!.filename] = json!.code;
        return response(200, { success: true, filename: json!.filename, ...parseScenes(json!.code) });
      case "POST /api/rename": {
        if (json!.new_name in server.scripts) return response(400, { detail: "A file with the target name already exists." });
        server.scripts[json!.new_name] = server.scripts[json!.old_name];
        delete server.scripts[json!.old_name];
        return response(200, { success: true });
      }
      case "DELETE /api/scripts":
        delete server.scripts[param("filename")];
        return response(200, { success: true });
      case "DELETE /api/assets":
        server.assets = server.assets.filter((asset) => asset.name !== param("filename"));
        return response(200, { success: true });
      case "DELETE /api/media":
        server.media = server.media.filter((item) => item.path !== param("path"));
        return response(200, { success: true });
      case "POST /api/upload-asset": {
        const file = (body as FormData).get("file") as File;
        server.assets.push({ name: file.name, size: file.size, type: "asset", url: `/assets/${file.name}` });
        return response(200, { success: true, filename: file.name });
      }
      case "POST /api/install-manim":
      case "POST /api/install-latex":
      case "POST /api/install-ffmpeg":
        return response(200, { success: true, message: "Installer started." });
    }
    if (method === "GET" && (url.pathname.startsWith("/media/") || url.pathname.startsWith("/api/download-temp"))) {
      return response(200, {});
    }
    return response(404, { detail: `No route for ${method} ${url.pathname}` });
  });

  globalThis.fetch = server.fetch as unknown as typeof fetch;
  return server;
}
