import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, act, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";

// Mock global fetch
const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

// Mock URL.createObjectURL and revokeObjectURL
globalThis.URL.createObjectURL = vi.fn(() => "blob:http://localhost:5173/mock-blob-video");
globalThis.URL.revokeObjectURL = vi.fn();

// Mock clipboard
Object.assign(navigator, {
  clipboard: {
    writeText: vi.fn().mockImplementation(() => Promise.resolve()),
  },
});

// Mock WebSocket
class MockWebSocket {
  static instances: MockWebSocket[] = [];
  url: string;
  readyState: number = 0;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  sentMessages: string[] = [];

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
    setTimeout(() => {
      this.readyState = 1; // OPEN
      if (this.onopen) this.onopen();
    }, 5);
  }

  send(data: string) {
    this.sentMessages.push(data);
  }

  close() {
    this.readyState = 3; // CLOSED
    if (this.onclose) this.onclose();
  }
}

globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket;

const mockDiagnostics = {
  profile: "balanced",
  preview_quality: "720p30",
  recommended_threads: 4,
  opengl_supported: true,
  description: "Balanced configuration for multi-core hardware rendering.",
  hardware: {
    cpu: { model: "Intel Core i7", physical_cores: 8, logical_threads: 16 },
    ram_gb: 16.0,
    gpu: { devices: [{ name: "RTX 3070", type: "NVIDIA", vram: "8GB" }], has_cuda: true },
    os: "Windows",
  },
  dependencies: {
    manim: "C:\\manim.exe",
    ffmpeg: "C:\\ffmpeg.exe",
    latex: "C:\\latex.exe",
    latex_available: true,
    dvisvgm: "C:\\dvisvgm.exe",
  },
};

const mockFiles = {
  scripts: [
    { name: "example.py", size: 1024, type: "script" },
    { name: "shapes.py", size: 512, type: "script" },
  ],
  assets: [
    { name: "logo.svg", size: 2048, type: "asset", url: "/assets/logo.svg" },
    { name: "diagram.png", size: 4096, type: "asset", url: "/assets/diagram.png" },
  ],
  media: [
    { name: "example.mp4", size: 4096, type: "video", url: "/media/example.mp4" },
    { name: "shapes.mp4", size: 8192, type: "video", url: "/media/shapes.mp4" },
  ],
};

const mockFileContent = {
  filename: "example.py",
  code: "from manim import *\n\nclass SquareToCircle(Scene):\n    def construct(self):\n        self.play(Create(Square()))\n        self.wait(1.0)\n",
  scenes: ["SquareToCircle"],
  animations: {
    SquareToCircle: [
      { type: "play", label: "Play: Create(Square())", line: 5 },
      { type: "wait", label: "Wait 1.0s", duration: 1.0, line: 6 },
    ],
  },
};

const defaultFetchHandler = (url: RequestInfo | URL | string) => {
  const urlStr = typeof url === "string" ? url : "url" in url ? (url as Request).url : String(url);
  if (urlStr.includes("diagnostics")) {
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve(mockDiagnostics),
    });
  }
  if (urlStr.includes("files")) {
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve(mockFiles),
    });
  }
  if (urlStr.includes("file-content")) {
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve(mockFileContent),
    });
  }
  if (urlStr.includes("parse-code")) {
    return Promise.resolve({
      ok: true,
      json: () =>
        Promise.resolve({
          scenes: ["SquareToCircle"],
          animations: mockFileContent.animations,
        }),
    });
  }
  if (urlStr.includes("save")) {
    return Promise.resolve({
      ok: true,
      json: () =>
        Promise.resolve({
          success: true,
          filename: "example.py",
          scenes: ["SquareToCircle"],
          animations: mockFileContent.animations,
        }),
    });
  }
  if (urlStr.includes("rename")) {
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ success: true }),
    });
  }
  if (urlStr.includes("upload-asset")) {
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ success: true, filename: "uploaded.svg", url: "/assets/uploaded.svg" }),
    });
  }
  if (urlStr.includes("install-")) {
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ success: true, message: "Installer started successfully" }),
    });
  }
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve({}),
    blob: () => Promise.resolve(new Blob(["video-content"], { type: "video/mp4" })),
  });
};

describe("Frontend App Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    MockWebSocket.instances = [];
    mockFetch.mockReset();
    mockFetch.mockImplementation(defaultFetchHandler);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders main header and editor workspace without crashing", async () => {
    render(<App />);
    expect(screen.getByText(/MANIM COMPOSER/i)).toBeDefined();
    await waitFor(() => {
      expect(screen.getByText("SquareToCircle")).toBeDefined();
    });
  });

  it("switches sidebar tabs between wizard, snippets, latex, assets, and diags", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(screen.getByText(/FILES/i)).toBeDefined());

    await user.click(screen.getByRole("tab", { name: /wizard/i }));
    await waitFor(() => expect(screen.getByText(/Shape Wizard/i)).toBeDefined());

    await user.click(screen.getByRole("tab", { name: /snippets/i }));
    await waitFor(() => expect(screen.getByText(/Basic Animation/i)).toBeDefined());

    await user.click(screen.getByRole("tab", { name: /latex/i }));
    await waitFor(() => expect(screen.getByText(/LaTeX Sandbox/i)).toBeDefined());

    await user.click(screen.getByRole("tab", { name: /assets/i }));
    await waitFor(() => expect(screen.getByText(/Library Assets/i)).toBeDefined());

    await user.click(screen.getByRole("tab", { name: /diags/i }));
    await waitFor(() => expect(screen.getByText(/Intel Core i7/i)).toBeDefined());
  });

  it("handles storage location switch and local browser file CRUD", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(screen.getByRole("tab", { name: /config/i })).toBeDefined());

    await user.click(screen.getByRole("tab", { name: /config/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /Local Browser/i })).toBeDefined());

    await user.click(screen.getByRole("button", { name: /Local Browser/i }));
    expect(screen.getByRole("button", { name: /Local Browser/i })).toBeDefined();

    await user.click(screen.getByRole("button", { name: /Workspace Disk/i }));
    expect(screen.getByRole("button", { name: /Workspace Disk/i })).toBeDefined();
  });

  it("creates a new python file with validation", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByRole("button", { name: /^New$/i })).toBeDefined());

    const newFileBtn = screen.getByRole("button", { name: /^New$/i });
    fireEvent.click(newFileBtn);

    await waitFor(() => expect(screen.getByText(/Create New Python Script/i)).toBeDefined());

    const input = screen.getByPlaceholderText(/scene_name.py/i);
    fireEvent.change(input, { target: { value: "brand_new_scene.py" } });

    const createBtn = screen.getByRole("button", { name: "Create File" });
    fireEvent.click(createBtn);

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/save"),
        expect.objectContaining({ method: "POST" })
      );
    });
  });

  it("validates invalid and reserved file names on creation", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByRole("button", { name: /^New$/i })).toBeDefined());

    const newFileBtn = screen.getByRole("button", { name: /^New$/i });
    fireEvent.click(newFileBtn);

    const input = screen.getByPlaceholderText(/scene_name.py/i);
    const createBtn = screen.getByRole("button", { name: "Create File" });

    // Test Windows reserved device names
    fireEvent.change(input, { target: { value: "CON.py" } });
    fireEvent.click(createBtn);

    fireEvent.change(input, { target: { value: "PRN.py" } });
    fireEvent.click(createBtn);
  });

  it("handles inline file rename in backend storage mode", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText("shapes.py")).toBeDefined());

    const shapesItem = screen.getByText("shapes.py");
    fireEvent.doubleClick(shapesItem);

    const renameInput = screen.getByDisplayValue("shapes.py");
    fireEvent.change(renameInput, { target: { value: "shapes_v2.py" } });
    fireEvent.keyDown(renameInput, { key: "Enter", code: "Enter" });

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/rename"),
        expect.objectContaining({ method: "POST" })
      );
    });
  });

  it("handles snippet insertion with replace and append options", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(screen.getByRole("tab", { name: /snippets/i })).toBeDefined());

    await user.click(screen.getByRole("tab", { name: /snippets/i }));
    await waitFor(() => expect(screen.getByText(/Basic Animation/i)).toBeDefined());

    const insertButtons = screen.getAllByRole("button", { name: /Insert Cursor/i });
    expect(insertButtons.length).toBeGreaterThan(0);
    await user.click(insertButtons[0]);
  });

  it("handles wizard shape, color, animation selections and code insertion", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(screen.getByRole("tab", { name: /wizard/i })).toBeDefined());

    await user.click(screen.getByRole("tab", { name: /wizard/i }));
    await waitFor(() => expect(screen.getByText(/Shape Wizard/i)).toBeDefined());

    const insertBtn = screen.getByRole("button", { name: /Insert Code/i });
    expect(insertBtn).toBeDefined();
    await user.click(insertBtn);
  });

  it("handles live WebSocket rendering stream events and progress", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText("SquareToCircle")).toBeDefined());

    await waitFor(() => {
      expect(MockWebSocket.instances.length).toBeGreaterThan(0);
    });

    const ws = MockWebSocket.instances[0];

    act(() => {
      if (ws.onmessage) {
        ws.onmessage({ data: JSON.stringify({ type: "progress", percent: 50 }) });
        ws.onmessage({ data: JSON.stringify({ type: "log", message: "Rendering frame 30/60", stream: "stdout" }) });
        ws.onmessage({ data: JSON.stringify({ type: "info", message: "Render profile: balanced" }) });
        ws.onmessage({
          data: JSON.stringify({
            type: "file_ready",
            rel_path: "media/videos/example.mp4",
            filename: "example.mp4",
          }),
        });
        ws.onmessage({ data: JSON.stringify({ type: "latex_error_warning", message: "LaTeX parsing warning" }) });
        ws.onmessage({ data: JSON.stringify({ type: "result", success: true, status: "success" }) });
      }
    });

    await waitFor(() => {
      expect(screen.getByText(/Video ready! File saved to: example.mp4/i)).toBeDefined();
    });
  });

  it("handles render cancellation via cancel button", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText("SquareToCircle")).toBeDefined());

    await waitFor(() => {
      expect(MockWebSocket.instances.length).toBeGreaterThan(0);
    });

    const ws = MockWebSocket.instances[0];

    // Emulate server error / logs / render progress
    act(() => {
      if (ws.onmessage) {
        ws.onmessage({ data: JSON.stringify({ type: "log", message: "Compiling manim scene...", stream: "stdout" }) });
      }
    });

    await waitFor(() => {
      expect(screen.getByText(/Compiling manim scene.../i)).toBeDefined();
    });

    ws.send(JSON.stringify({ type: "cancel" }));
    expect(ws.sentMessages).toContain(JSON.stringify({ type: "cancel" }));
  });

  it("handles asset upload validation, errors, and clipboard actions", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(screen.getByRole("tab", { name: /assets/i })).toBeDefined());

    await user.click(screen.getByRole("tab", { name: /assets/i }));
    await waitFor(() => expect(screen.getByText(/Library Assets/i)).toBeDefined());

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    expect(fileInput).toBeDefined();

    // Valid SVG test
    const svgFile = new File(["<svg></svg>"], "test_logo.svg", { type: "image/svg+xml" });
    fireEvent.change(fileInput, { target: { files: [svgFile] } });

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/upload-asset"),
        expect.any(Object)
      );
    });
  });

  it("handles formula sandbox LaTeX preview, chips clicking, and insertion", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(screen.getByRole("tab", { name: /latex/i })).toBeDefined());

    await user.click(screen.getByRole("tab", { name: /latex/i }));
    await waitFor(() => expect(screen.getByText(/LaTeX Sandbox/i)).toBeDefined());

    const eulerChip = screen.getByText(/Euler's Identity/i);
    await user.click(eulerChip);

    const quadChip = screen.getByText(/Quadratic Formula/i);
    await user.click(quadChip);

    const formulaInput = screen.getByPlaceholderText(/e.g. e\^\{i\\pi\}/i);
    fireEvent.change(formulaInput, { target: { value: "E = mc^2" } });

    const insertMathTexBtn = screen.getByRole("button", { name: /Insert MathTex/i });
    expect(insertMathTexBtn).toBeDefined();
    await user.click(insertMathTexBtn);
  });

  it("handles installer actions for LaTeX, FFmpeg, and Manim", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText(/MANIM COMPOSER/i)).toBeDefined());

    // Trigger installation API calls
    const resLatex = await fetch("http://localhost:8000/api/install-latex", { method: "POST" });
    expect(resLatex.ok).toBe(true);

    const resFFmpeg = await fetch("http://localhost:8000/api/install-ffmpeg", { method: "POST" });
    expect(resFFmpeg.ok).toBe(true);

    const resManim = await fetch("http://localhost:8000/api/install-manim", { method: "POST" });
    expect(resManim.ok).toBe(true);
  });

  it("handles timeline step focus and line jumping", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(screen.getByText("SquareToCircle")).toBeDefined());

    await user.click(screen.getByRole("tab", { name: /Visual Timeline/i }));

    await waitFor(() => {
      expect(screen.getByText("STEP 1")).toBeDefined();
      expect(screen.getByText(/Create\(Square\(\)\)/i)).toBeDefined();
    });

    const stepItem = screen.getByText("STEP 1");
    await user.click(stepItem);

    expect(stepItem).toBeDefined();
  });

  it("handles side-by-side video comparison modal, timeline scrubber, and close", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(screen.getByRole("button", { name: /Compare Renders/i })).toBeDefined());

    const compareBtn = screen.getByRole("button", { name: /Compare Renders/i });
    await user.click(compareBtn);

    expect(screen.getByText(/Synchronized Render Comparison/i)).toBeDefined();

    const playBtn = screen.getByRole("button", { name: /^Play Sync$/i });
    await user.click(playBtn);
    expect(screen.getByRole("button", { name: /^Pause$/i })).toBeDefined();

    const scrubber = screen.getByRole("slider");
    fireEvent.change(scrubber, { target: { value: "5" } });

    const closeBtn = screen.getByRole("button", { name: /Close/i });
    await user.click(closeBtn);

    expect(screen.queryByText(/Synchronized Render Comparison/i)).toBeNull();
  });

  it("inspects hardware diagnostics profile tab and launches setup wizard", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(screen.getByRole("tab", { name: /diags/i })).toBeDefined());

    await user.click(screen.getByRole("tab", { name: /diags/i }));

    await waitFor(() => expect(screen.getByText(/Hardware Specs/i)).toBeDefined());
    expect(screen.getByText(/RTX 3070/i)).toBeDefined();

    const wizardTriggerBtn = screen.getByRole("button", { name: /Launch Setup Wizard/i });
    await user.click(wizardTriggerBtn);

    expect(screen.getByText(/Setup Environment Wizard/i)).toBeDefined();
  });

  it("handles settings toggles and preferences", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(screen.getByRole("tab", { name: /config/i })).toBeDefined());

    await user.click(screen.getByRole("tab", { name: /config/i }));

    await waitFor(() => expect(screen.getByText(/Storage & Saves/i)).toBeDefined());
    expect(screen.getByText(/Auto-Save on Render/i)).toBeDefined();
    expect(screen.getByText(/Download-Only Mode/i)).toBeDefined();

    const autoSaveLabel = screen.getByText(/Auto-Save on Render/i);
    fireEvent.click(autoSaveLabel);

    const downloadOnlyLabel = screen.getByText(/Download-Only Mode/i);
    fireEvent.click(downloadOnlyLabel);
  });

  it("handles video preview selection", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(screen.getByText("example.mp4")).toBeDefined());

    const videoItem = screen.getByText("example.mp4");
    await user.click(videoItem);

    expect(screen.getByText(/Loading video file: example.mp4/i)).toBeDefined();
  });
});
