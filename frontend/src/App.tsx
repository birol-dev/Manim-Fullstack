import React, { useState, useEffect, useRef, useCallback } from "react";
import Editor from "@monaco-editor/react";
import {
  Play,
  Square,
  Cpu,
  Layers,
  Video,
  FileText,
  Plus,
  Save,
  AlertTriangle,
  Upload,
  Sparkles,
  Download,
  RefreshCw,
  HardDrive,
  FileCode,
  Copy,
  Check,
} from "lucide-react";

// Import Shadcn UI Components
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Progress } from "@/components/ui/progress";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// API & WS configuration
const defaultHost =
  window.location.port === "5173" ? "localhost:8000" : window.location.host;
const BACKEND_HOST =
  import.meta.env.VITE_BACKEND_URL || defaultHost || "localhost:8000";
const isProd =
  !BACKEND_HOST.includes("localhost") && !BACKEND_HOST.includes("127.0.0.1");

const API_BASE = BACKEND_HOST.startsWith("http")
  ? BACKEND_HOST.replace(/\/$/, "")
  : `${isProd ? "https" : "http"}://${BACKEND_HOST}`;

const WS_BASE = BACKEND_HOST.startsWith("http")
  ? BACKEND_HOST.replace(/\/$/, "").replace(/^http/, "ws")
  : `${isProd ? "wss" : "ws"}://${BACKEND_HOST}`;

interface FileItem {
  name: string;
  size: number;
  type: "script" | "asset" | "video";
  url?: string;
}

interface FileListResponse {
  scripts: FileItem[];
  assets: FileItem[];
  media: FileItem[];
}

interface DiagnosticInfo {
  profile: string;
  description: string;
  preview_quality: string;
  default_fps: number;
  default_resolution: string;
  recommended_threads: number;
  opengl_supported: boolean;
  hardware: {
    cpu: { model: string; physical_cores: number; logical_threads: number };
    ram_gb: number;
    gpu: {
      devices: Array<{ name: string; vram: string; type: string }>;
      has_cuda: boolean;
    };
  };
  dependencies: {
    manim: string;
    ffmpeg: string;
    latex: string;
    dvisvgm: string;
    latex_available: boolean;
  };
}

interface LogLine {
  type:
    | "log"
    | "error"
    | "info"
    | "status"
    | "progress"
    | "file_ready"
    | "latex_error_warning"
    | "warning"
    | "success"
    | "result";
  stream?: string;
  message?: string;
  status?: string;
  percent?: number;
  filename?: string;
  rel_path?: string;
  success?: boolean;
}

// Monaco Editor typings to avoid "any"
interface MonacoSelection {
  startLineNumber: number;
  startColumn: number;
  endLineNumber: number;
  endColumn: number;
}

interface MonacoEditorInstance {
  getSelection: () => MonacoSelection;
  executeEdits: (
    source: string,
    edits: Array<{
      identifier: { major: number; minor: number };
      range: unknown;
      text: string;
      forceMoveMarkers: boolean;
    }>,
  ) => void;
  setPosition: (position: { lineNumber: number; column: number }) => void;
  revealLineInCenter: (lineNumber: number) => void;
  focus: () => void;
}

interface MonacoGlobal {
  Range: new (
    startLine: number,
    startCol: number,
    endLine: number,
    endCol: number,
  ) => unknown;
}

interface GlobalWindow {
  monaco?: MonacoGlobal;
}

const SNIPPETS = [
  {
    title: "Basic Animation",
    description: "Create a square, rotate it, and transform it into a circle.",
    category: "Basic",
    code: `from manim import *\n\nclass SquareToCircle(Scene):\n    def construct(self):\n        circle = Circle(color=PINK)\n        square = Square(color=BLUE)\n        square.flip(RIGHT)\n        square.rotate(PI / 8)\n        self.play(Create(square))\n        self.play(Transform(square, circle))\n        self.play(FadeOut(square))\n`,
  },
  {
    title: "Kinetic Typography",
    description: "Write styled header text and draw background accent rings.",
    category: "Text",
    code: `from manim import *\n\nclass KineticTitle(Scene):\n    def construct(self):\n        title = Text("MANIM COMPOSER", font="Outfit", font_size=48, color=YELLOW)\n        subtitle = Text("Hardware Optimized Video Editor", font_size=28, color=LIGHT_GRAY)\n        title.shift(UP * 0.5)\n        subtitle.next_to(title, DOWN)\n        ring = Circle(radius=3.5, color=BLUE_E, stroke_width=2)\n        self.play(Create(ring), run_time=1.5)\n        self.play(Write(title))\n        self.play(FadeIn(subtitle, shift=UP * 0.5))\n        self.wait(1)\n        self.play(ring.animate.scale(1.2).set_opacity(0), FadeOut(title, shift=LEFT * 2), FadeOut(subtitle, shift=RIGHT * 2))\n`,
  },
  {
    title: "Mathematical Plotting",
    description:
      "Plot functions (Sine & Cosine waves) using axes, grids and labels.",
    category: "Math",
    code: `from manim import *\n\nclass PlotSineCosine(Scene):\n    def construct(self):\n        axes = Axes(x_range=[-3, 10, 1], y_range=[-1.5, 1.5, 0.5], x_length=10, y_length=5, axis_config={"color": BLUE})\n        labels = axes.get_axis_labels(x_label="x", y_label="f(x)")\n        sine_curve = axes.plot(lambda x: np.sin(x), color=GREEN)\n        cosine_curve = axes.plot(lambda x: np.cos(x), color=RED)\n        sine_label = axes.get_graph_label(sine_curve, label="sin(x)", x_val=7.5, direction=UP)\n        cosine_label = axes.get_graph_label(cosine_curve, label="cos(x)", x_val=2.5, direction=DOWN)\n        self.play(Create(axes), Write(labels))\n        self.play(Create(sine_curve), run_time=2)\n        self.play(Write(sine_label))\n        self.wait(0.5)\n        self.play(Create(cosine_curve), run_time=2)\n        self.play(Write(cosine_label))\n        self.wait(1.5)\n`,
  },
  {
    title: "3D Coordinate Grid",
    description:
      "Initialize a ThreeDScene and perform camera rotation around objects.",
    category: "3D",
    code: `from manim import *\n\nclass ThreeDExample(ThreeDScene):\n    def construct(self):\n        axes = ThreeDAxes()\n        cylinder = Cylinder(radius=1.5, height=3, stroke_width=1, fill_color=PURPLE)\n        cylinder.set_opacity(0.6)\n        self.set_camera_orientation(phi=75 * DEGREES, theta=30 * DEGREES)\n        self.play(Create(axes))\n        self.play(Create(cylinder))\n        self.begin_ambient_camera_rotation(rate=0.2)\n        self.wait(3.0)\n        self.stop_ambient_camera_rotation()\n        self.wait(1.0)\n`,
  },
];

const LATEX_TEMPLATES = [
  { name: "Euler's Identity", code: "e^{i\\pi} + 1 = 0" },
  {
    name: "Quadratic Formula",
    code: "x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}",
  },
  {
    name: "Maxwell's Equations",
    code: "\\nabla \\cdot \\mathbf{E} = \\frac{\\rho}{\\varepsilon_0}",
  },
  {
    name: "Schrödinger Equation",
    code: "i\\hbar\\frac{\\partial}{\\partial t}\\Psi = \\hat{H}\\Psi",
  },
  {
    name: "Gaussian Integral",
    code: "\\int_{-\\infty}^{\\infty} e^{-x^2} dx = \\sqrt{\\pi}",
  },
  { name: "Matrix", code: "\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}" },
  { name: "Fraction", code: "\\frac{a}{b}" },
  { name: "Summation", code: "\\sum_{i=1}^{n} i = \\frac{n(n+1)}{2}" },
];

interface LaTeXProps {
  math: string;
  block?: boolean;
}

function LaTeX({ math, block = false }: LaTeXProps) {
  const containerRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (containerRef.current) {
      const globalWindow = window as unknown as Record<
        string,
        {
          render: (
            math: string,
            el: HTMLElement,
            options: Record<string, unknown>,
          ) => void;
        }
      >;
      if (globalWindow.katex) {
        try {
          globalWindow.katex.render(math, containerRef.current, {
            displayMode: block,
            throwOnError: false,
          });
        } catch {
          containerRef.current.textContent = math;
        }
      } else {
        containerRef.current.textContent = math;
      }
    }
  }, [math, block]);

  return <span ref={containerRef} />;
}

export default function App() {
  const [files, setFiles] = useState<FileListResponse>({
    scripts: [],
    assets: [],
    media: [],
  });
  const [activeFile, setActiveFile] = useState<string>("example.py");
  const [code, setCode] = useState<string>("");
  const [scenes, setScenes] = useState<string[]>([]);
  const [selectedScene, setSelectedScene] = useState<string>("");

  // Custom states added for upgrades
  const [animations, setAnimations] = useState<
    Record<
      string,
      Array<{
        type: "play" | "wait";
        label: string;
        line: number;
        duration?: number;
      }>
    >
  >({});
  const [showCompareDialog, setShowCompareDialog] = useState<boolean>(false);
  const [compareVideoA, setCompareVideoA] = useState<string>("");
  const [compareVideoB, setCompareVideoB] = useState<string>("");
  const [copiedAsset, setCopiedAsset] = useState<string | null>(null);

  // Wizard settings
  const [wizardShape, setWizardShape] = useState<string>("Circle");
  const [wizardColor, setWizardColor] = useState<string>("BLUE");
  const [wizardScale, setWizardScale] = useState<string>("1.0");
  const [wizardShiftX, setWizardShiftX] = useState<string>("0.0");
  const [wizardShiftY, setWizardShiftY] = useState<string>("0.0");
  const [wizardRotation, setWizardRotation] = useState<string>("0.0");
  const [wizardText, setWizardText] = useState<string>("Hello Manim");
  const [wizardLatex, setWizardLatex] = useState<string>("x^2 + y^2 = z^2");
  const [wizardEntryAnim, setWizardEntryAnim] = useState<string>("Create");
  const [wizardActionAnim, setWizardActionAnim] = useState<string>("none");
  const [wizardExitAnim, setWizardExitAnim] = useState<string>("FadeOut");

  const [quality, setQuality] = useState<string>("m");
  const [useOpengl, setUseOpengl] = useState<boolean>(false);
  const [isRendering, setIsRendering] = useState<boolean>(false);
  const [renderPercent, setRenderPercent] = useState<number>(0);

  const [logs, setLogs] = useState<LogLine[]>([]);
  const [diagnostics, setDiagnostics] = useState<DiagnosticInfo | null>(null);
  const [wsConnected, setWsConnected] = useState<boolean>(false);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [isInstallingLatex, setIsInstallingLatex] = useState<boolean>(false);
  const [isInstallingFFmpeg, setIsInstallingFFmpeg] = useState<boolean>(false);
  const [isInstallingManim, setIsInstallingManim] = useState<boolean>(false);
  const [showOnboarding, setShowOnboarding] = useState<boolean>(false);

  const [videoUrl, setVideoUrl] = useState<string>("");
  const [videoKey, setVideoKey] = useState<number>(0);

  const [showNewFileDialog, setShowNewFileDialog] = useState<boolean>(false);
  const [showLoadTemplateDialog, setShowLoadTemplateDialog] =
    useState<boolean>(false);
  const [pendingTemplateCode, setPendingTemplateCode] = useState<string>("");
  const [newFileName, setNewFileName] = useState<string>("");
  const [backendError, setBackendError] = useState<boolean>(false);
  const [latexInput, setLatexInput] = useState<string>("e^{i\\pi} + 1 = 0");
  const [autoRender, setAutoRender] = useState<boolean>(false);
  const [savedPath, setSavedPath] = useState<string>("");
  const [renamingFile, setRenamingFile] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState<string>("");

  const wsRef = useRef<WebSocket | null>(null);
  const logEndRef = useRef<HTMLDivElement | null>(null);
  const editorRef = useRef<unknown>(null);
  const monacoRef = useRef<unknown>(null);
  const autoRenderTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const startRenderRef = useRef<(() => void) | null>(null);
  const hasAutoCheckedRef = useRef<boolean>(false);
  const shouldCancelRenameRef = useRef<boolean>(false);
  const isRenamingInProgressRef = useRef<boolean>(false);

  // Sync Comparer state and callbacks
  const videoARef = useRef<HTMLVideoElement | null>(null);
  const videoBRef = useRef<HTMLVideoElement | null>(null);
  const [comparePlaying, setComparePlaying] = useState<boolean>(false);
  const [compareTime, setCompareTime] = useState<number>(0);
  const [compareDuration, setCompareDuration] = useState<number>(0);

  const handleComparePlayToggle = () => {
    const playState = !comparePlaying;
    setComparePlaying(playState);
    if (playState) {
      videoARef.current?.play().catch(() => {});
      videoBRef.current?.play().catch(() => {});
    } else {
      videoARef.current?.pause();
      videoBRef.current?.pause();
    }
  };

  const handleCompareTimeChange = (val: number) => {
    setCompareTime(val);
    if (videoARef.current) videoARef.current.currentTime = val;
    if (videoBRef.current) videoBRef.current.currentTime = val;
  };

  const handleVideoTimeUpdate = () => {
    if (videoARef.current) {
      setCompareTime(videoARef.current.currentTime);
    }
  };

  const handleVideoLoadedMetadata = () => {
    const durA = videoARef.current?.duration || 0;
    const durB = videoBRef.current?.duration || 0;
    setCompareDuration(Math.max(durA, durB) || 10);
  };

  const addLog = useCallback(
    (type: LogLine["type"], msg: string, stream?: string) => {
      setLogs((prev) => [...prev, { type, message: msg, stream }]);
    },
    [],
  );

  const fetchDiagnostics = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/diagnostics`);
      if (!res.ok) throw new Error();
      const data = (await res.json()) as DiagnosticInfo;
      setDiagnostics(data);
      setBackendError(false);

      if (data.profile === "eco") setQuality("l");
      else if (data.profile === "workstation") setQuality("h");
      else setQuality("m");

      // Auto-show onboarding if critical dependencies are missing on first load
      if (!hasAutoCheckedRef.current) {
        const hasManim =
          data.dependencies.manim && data.dependencies.manim !== "Not Found";
        const hasFFmpeg =
          data.dependencies.ffmpeg && data.dependencies.ffmpeg !== "Not Found";
        if (!hasManim || !hasFFmpeg) {
          setShowOnboarding(true);
        }
        hasAutoCheckedRef.current = true;
      }

      // Reset installer states once dependencies are successfully detected
      const hasManim =
        data.dependencies.manim && data.dependencies.manim !== "Not Found";
      const hasFFmpeg =
        data.dependencies.ffmpeg && data.dependencies.ffmpeg !== "Not Found";
      const hasLatex = data.dependencies.latex_available;

      if (hasManim) setIsInstallingManim(false);
      if (hasFFmpeg) setIsInstallingFFmpeg(false);
      if (hasLatex) setIsInstallingLatex(false);
    } catch {
      setBackendError(true);
    }
  }, [setIsInstallingManim, setIsInstallingFFmpeg, setIsInstallingLatex]);

  const fetchFiles = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/files`);
      if (!res.ok) throw new Error();
      const data = await res.json();
      setFiles(data);
    } catch {
      console.error("Failed to load workspace files.");
    }
  }, []);

  const loadFileContent = useCallback(async (name: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/file-content?filename=${name}`);
      if (!res.ok) throw new Error();
      const data = await res.json();
      setActiveFile(data.filename);
      setCode(data.code);
      setScenes(data.scenes as string[]);
      setAnimations(data.animations || {});
      if ((data.scenes as string[]).length > 0) {
        setSelectedScene(data.scenes[0]);
      } else {
        setSelectedScene("");
      }
    } catch {
      console.error("Failed to load file contents.");
    }
  }, []);

  const handleSave = useCallback(
    async (silent = false) => {
      if (!activeFile) return;
      setIsSaving(true);
      try {
        const res = await fetch(`${API_BASE}/api/save`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ filename: activeFile, code }),
        });
        const data = await res.json();
        if (data.success) {
          setScenes(data.scenes as string[]);
          setAnimations(data.animations || {});
          if (
            (data.scenes as string[]).length > 0 &&
            !(data.scenes as string[]).includes(selectedScene)
          ) {
            setSelectedScene(data.scenes[0]);
          }
          if (!silent) {
            addLog(
              "info",
              `File "${activeFile}" saved successfully. Found scenes: ${(data.scenes as string[]).join(", ")}`,
            );
          }
          fetchFiles();
        }
      } catch {
        addLog("error", "Error saving file to workspace.");
      } finally {
        setIsSaving(false);
      }
    },
    [activeFile, code, selectedScene, fetchFiles, addLog],
  );

  const handleCreateFile = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!newFileName.trim()) return;
      let name = newFileName.trim();
      if (!name.endsWith(".py")) name += ".py";

      const defaultCode = `from manim import *\n\nclass NewScene(Scene):\n    def construct(self):\n        text = Text("New Project", font_size=36)\n        self.play(Write(text))\n        self.wait(1)\n        self.play(FadeOut(text))\n`;

      try {
        const res = await fetch(`${API_BASE}/api/save`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ filename: name, code: defaultCode }),
        });
        const data = await res.json();
        if (data.success) {
          setNewFileName("");
          setShowNewFileDialog(false);
          await fetchFiles();
          await loadFileContent(name);
          addLog("info", `Created new script: ${name}`);
        }
      } catch {
        addLog("error", "Error creating new file.");
      }
    },
    [newFileName, fetchFiles, loadFileContent, addLog],
  );

  const handleRename = useCallback(
    async (oldName: string, newName: string) => {
      setRenamingFile(null);
      if (!newName.trim() || newName.trim() === oldName) return;
      let name = newName.trim();
      if (!name.endsWith(".py")) name += ".py";

      if (isRenamingInProgressRef.current) return;
      isRenamingInProgressRef.current = true;

      try {
        const res = await fetch(`${API_BASE}/api/rename`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ old_name: oldName, new_name: name }),
        });

        if (!res.ok) {
          const errorData = (await res.json()) as { detail?: string };
          throw new Error(errorData.detail || "Rename failed.");
        }

        const data = (await res.json()) as { success: boolean };
        if (data.success) {
          addLog("info", `Renamed file: ${oldName} -> ${name}`);
          if (activeFile === oldName) {
            setActiveFile(name);
          }
          fetchFiles();
        }
      } catch (error) {
        const msg =
          error instanceof Error ? error.message : "Error renaming file.";
        addLog("error", msg);
      } finally {
        isRenamingInProgressRef.current = false;
      }
    },
    [activeFile, fetchFiles, addLog],
  );

  const handleAssetUpload = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      if (!e.target.files || e.target.files.length === 0) return;
      const file = e.target.files[0];
      const formData = new FormData();
      formData.append("file", file);

      try {
        const res = await fetch(`${API_BASE}/api/upload-asset`, {
          method: "POST",
          body: formData,
        });
        const data = await res.json();
        if (data.success) {
          addLog("info", `Asset uploaded: ${data.filename}`);
          fetchFiles();
        }
      } catch {
        addLog("error", "Failed to upload asset.");
      }
    },
    [fetchFiles, addLog],
  );

  const downloadRenderedVideo = useCallback(
    async (relPath: string, providedName?: string) => {
      const normalizedPath = relPath.replace(/^\/+/, "");
      const downloadUrl = `${API_BASE}/${normalizedPath}`;
      const filename =
        providedName || normalizedPath.split("/").pop() || "render.mp4";

      try {
        const response = await fetch(downloadUrl);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const blob = await response.blob();
        const objectUrl = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = objectUrl;
        anchor.download = filename;
        anchor.style.display = "none";
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);

        addLog("success", `Downloaded video: ${filename}`);
      } catch {
        addLog(
          "warning",
          "Video rendered, but automatic download failed. Use the download icon in Rendered Videos.",
        );
      }
    },
    [addLog],
  );

  const sendRenderRequest = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({
          type: "start",
          filename: activeFile,
          scene: selectedScene,
          quality: quality,
          use_opengl: useOpengl,
        }),
      );
    } else {
      addLog(
        "error",
        "WebSocket render request failed: server connection closed.",
      );
      setIsRendering(false);
    }
  }, [activeFile, selectedScene, quality, useOpengl, addLog]);

  const connectWebSocket = useCallback(
    (onConnectCallback?: () => void) => {
      try {
        const ws = new WebSocket(`${WS_BASE}/api/render`);
        wsRef.current = ws;

        ws.onopen = () => {
          setWsConnected(true);
          setBackendError(false);
          if (onConnectCallback) onConnectCallback();
        };

        ws.onmessage = (event) => {
          const data = JSON.parse(event.data) as LogLine;

          if (data.type === "log") {
            addLog("log", data.message || "", data.stream);
          } else if (data.type === "info") {
            addLog("info", data.message || "");
          } else if (data.type === "error") {
            addLog("error", data.message || "");
            setIsRendering(false);
          } else if (data.type === "latex_error_warning") {
            addLog("warning", data.message || "");
          } else if (data.type === "progress") {
            setRenderPercent(data.percent || 0);
          } else if (data.type === "file_ready") {
            addLog("success", `Video ready! File saved to: ${data.filename}`);
            if (data.rel_path) {
              setVideoUrl(`${API_BASE}/${data.rel_path}?t=${Date.now()}`);
              setVideoKey((prev) => prev + 1);
              setSavedPath(`workspace/${data.rel_path}`);
              void downloadRenderedVideo(data.rel_path, data.filename);
            }
            fetchFiles();
          } else if (data.type === "result") {
            setIsRendering(false);
            setRenderPercent(100);
            if (data.success) {
              addLog("success", "Render task finished successfully!");
            } else {
              addLog("error", `Render task failed: ${data.status}`);
            }
          }
        };

        ws.onclose = () => {
          setWsConnected(false);
          wsRef.current = null;
        };

        ws.onerror = () => {
          setWsConnected(false);
        };
      } catch {
        console.error("WS error connecting.");
      }
    },
    [fetchFiles, addLog, downloadRenderedVideo],
  );

  const startRender = useCallback(async () => {
    if (isRendering) return;
    await handleSave(true);

    if (!selectedScene) {
      addLog(
        "error",
        "Please select or write a valid Scene class in the editor before rendering.",
      );
      return;
    }

    setIsRendering(true);
    setRenderPercent(0);
    setLogs([]);
    addLog(
      "info",
      `Initiating render for Scene "${selectedScene}" from file "${activeFile}"...`,
    );

    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      connectWebSocket(() => {
        sendRenderRequest();
      });
    } else {
      sendRenderRequest();
    }
  }, [
    isRendering,
    activeFile,
    selectedScene,
    handleSave,
    connectWebSocket,
    sendRenderRequest,
    addLog,
  ]);

  const cancelRender = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "cancel" }));
      addLog("info", "Cancelling render operation...");
    }
  }, [addLog]);

  const handleInstallLatex = useCallback(async () => {
    if (isInstallingLatex) return;
    setIsInstallingLatex(true);
    addLog(
      "info",
      "Starting MiKTeX LaTeX installation in the background via winget...",
    );
    try {
      const res = await fetch(`${API_BASE}/api/install-latex`, {
        method: "POST",
      });
      const data = await res.json();
      if (data.success) {
        addLog("success", data.message);
        addLog(
          "info",
          "The installation runs silently in your user profile directory (no UAC prompt required).",
        );
      } else {
        addLog("error", "LaTeX setup call returned failure state.");
        setIsInstallingLatex(false);
      }
    } catch {
      addLog("error", "Failed to contact backend to install LaTeX.");
      setIsInstallingLatex(false);
    }
  }, [isInstallingLatex, addLog]);

  const handleInstallFFmpeg = useCallback(async () => {
    if (isInstallingFFmpeg) return;
    setIsInstallingFFmpeg(true);
    addLog(
      "info",
      "Starting FFmpeg installation in the background via winget...",
    );
    try {
      const res = await fetch(`${API_BASE}/api/install-ffmpeg`, {
        method: "POST",
      });
      const data = await res.json();
      if (data.success) {
        addLog("success", data.message);
        addLog(
          "info",
          "The installation runs silently in your user profile directory (no UAC prompt required).",
        );
      } else {
        addLog("error", "FFmpeg setup call returned failure state.");
        setIsInstallingFFmpeg(false);
      }
    } catch {
      addLog("error", "Failed to contact backend to install FFmpeg.");
      setIsInstallingFFmpeg(false);
    }
  }, [isInstallingFFmpeg, addLog]);

  const handleInstallManim = useCallback(async () => {
    if (isInstallingManim) return;
    setIsInstallingManim(true);
    addLog(
      "info",
      "Starting Manim CE installation in the background via pip...",
    );
    try {
      const res = await fetch(`${API_BASE}/api/install-manim`, {
        method: "POST",
      });
      const data = await res.json();
      if (data.success) {
        addLog("success", data.message);
      } else {
        addLog("error", "Manim CE setup call returned failure state.");
        setIsInstallingManim(false);
      }
    } catch {
      addLog("error", "Failed to contact backend to install Manim CE.");
      setIsInstallingManim(false);
    }
  }, [isInstallingManim, addLog]);

  // Track installer state resolution (handled inside fetchDiagnostics)

  // Poll diagnostics while installs are running
  useEffect(() => {
    let interval: ReturnType<typeof setInterval> | null = null;
    if (isInstallingFFmpeg || isInstallingManim || isInstallingLatex) {
      interval = setInterval(() => {
        fetchDiagnostics();
      }, 3000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [
    isInstallingFFmpeg,
    isInstallingManim,
    isInstallingLatex,
    fetchDiagnostics,
  ]);

  const handleInsertSnippet = useCallback(
    (snippetCode: string) => {
      if (editorRef.current) {
        const editor = editorRef.current as MonacoEditorInstance;
        const selection = editor.getSelection();

        const globalWindow = window as unknown as GlobalWindow;
        if (globalWindow.monaco) {
          const range = new globalWindow.monaco.Range(
            selection.startLineNumber,
            selection.startColumn,
            selection.endLineNumber,
            selection.endColumn,
          );
          const id = { major: 1, minor: 1 };
          const op = {
            identifier: id,
            range: range,
            text: snippetCode,
            forceMoveMarkers: true,
          };
          editor.executeEdits("my-source", [op]);
          addLog("info", "Inserted template snippet into active buffer.");
        }
      } else {
        setCode(snippetCode);
        addLog("info", "Loaded template script.");
      }
    },
    [addLog],
  );

  const handleLoadTemplate = useCallback((templateCode: string) => {
    setPendingTemplateCode(templateCode);
    setShowLoadTemplateDialog(true);
  }, []);

  const confirmLoadTemplate = useCallback(() => {
    if (pendingTemplateCode) {
      setCode(pendingTemplateCode);
      setPendingTemplateCode("");
      setShowLoadTemplateDialog(false);
      addLog("info", "Loaded template script into active editor.");
    }
  }, [pendingTemplateCode, addLog]);

  const handleInsertMathTex = useCallback(
    (latexCode: string) => {
      const snippet = `MathTex(r"${latexCode}")`;
      handleInsertSnippet(snippet);
    },
    [handleInsertSnippet],
  );

  const handleInsertAssetPath = useCallback(
    (assetName: string) => {
      const path = `"assets/${assetName}"`;
      handleInsertSnippet(path);
    },
    [handleInsertSnippet],
  );

  const handleCopyAssetPath = useCallback(
    (assetName: string) => {
      const path = `assets/${assetName}`;
      navigator.clipboard
        .writeText(path)
        .then(() => {
          setCopiedAsset(assetName);
          addLog("info", `Copied asset path: ${path}`);
          setTimeout(() => setCopiedAsset(null), 2000);
        })
        .catch(() => {
          addLog("error", "Failed to copy to clipboard.");
        });
    },
    [addLog],
  );

  const getGeneratedWizardCode = useCallback(() => {
    let codeBlock = "";
    const varName = wizardShape.toLowerCase() + "_obj";

    // 1. Definition
    if (wizardShape === "Circle") {
      codeBlock += `        ${varName} = Circle(color=${wizardColor})\n`;
    } else if (wizardShape === "Square") {
      codeBlock += `        ${varName} = Square(color=${wizardColor})\n`;
    } else if (wizardShape === "Rectangle") {
      codeBlock += `        ${varName} = Rectangle(color=${wizardColor}, height=2.0, width=3.5)\n`;
    } else if (wizardShape === "Triangle") {
      codeBlock += `        ${varName} = Triangle(color=${wizardColor})\n`;
    } else if (wizardShape === "Line") {
      codeBlock += `        ${varName} = Line(start=LEFT, end=RIGHT, color=${wizardColor})\n`;
    } else if (wizardShape === "Arrow") {
      codeBlock += `        ${varName} = Arrow(start=LEFT, end=RIGHT, color=${wizardColor})\n`;
    } else if (wizardShape === "Text") {
      const escapedText = wizardText.replace(/"/g, '\\"');
      codeBlock += `        ${varName} = Text("${escapedText}", color=${wizardColor}, font_size=36)\n`;
    } else if (wizardShape === "MathTex") {
      const escapedLatex = wizardLatex.replace(/"/g, '\\"');
      codeBlock += `        ${varName} = MathTex(r"${escapedLatex}", color=${wizardColor})\n`;
    }

    // 2. Adjustments
    const scaleVal = parseFloat(wizardScale);
    if (!isNaN(scaleVal) && scaleVal !== 1.0) {
      codeBlock += `        ${varName}.scale(${scaleVal})\n`;
    }

    const shiftX = parseFloat(wizardShiftX);
    const shiftY = parseFloat(wizardShiftY);
    if (
      (!isNaN(shiftX) && shiftX !== 0.0) ||
      (!isNaN(shiftY) && shiftY !== 0.0)
    ) {
      let shiftTerm = "";
      if (shiftX !== 0.0) {
        shiftTerm +=
          shiftX > 0 ? `RIGHT * ${shiftX}` : `LEFT * ${Math.abs(shiftX)}`;
      }
      if (shiftY !== 0.0) {
        if (shiftTerm) shiftTerm += " + ";
        shiftTerm +=
          shiftY > 0 ? `UP * ${shiftY}` : `DOWN * ${Math.abs(shiftY)}`;
      }
      codeBlock += `        ${varName}.shift(${shiftTerm})\n`;
    }

    const rotVal = parseFloat(wizardRotation);
    if (!isNaN(rotVal) && rotVal !== 0.0) {
      codeBlock += `        ${varName}.rotate(${rotVal} * DEGREES)\n`;
    }

    codeBlock += `\n`;

    // 3. Play entry
    if (wizardEntryAnim !== "none") {
      codeBlock += `        self.play(${wizardEntryAnim}(${varName}))\n`;
    }

    // 4. Play action
    if (wizardActionAnim === "Rotate") {
      codeBlock += `        self.play(Rotate(${varName}, angle=PI / 2))\n`;
    } else if (wizardActionAnim === "ScaleUp") {
      codeBlock += `        self.play(${varName}.animate.scale(1.5))\n`;
    } else if (wizardActionAnim === "ColorChange") {
      codeBlock += `        self.play(${varName}.animate.set_color(PINK))\n`;
    }

    // 5. Play exit
    if (wizardExitAnim !== "none") {
      codeBlock += `        self.play(${wizardExitAnim}(${varName}))\n`;
    }

    return codeBlock;
  }, [
    wizardShape,
    wizardColor,
    wizardScale,
    wizardShiftX,
    wizardShiftY,
    wizardRotation,
    wizardText,
    wizardLatex,
    wizardEntryAnim,
    wizardActionAnim,
    wizardExitAnim,
  ]);

  const handleEditorDidMount = (editor: unknown, monacoInstance: unknown) => {
    editorRef.current = editor;
    monacoRef.current = monacoInstance;
  };

  // Sync monaco instance to global window asynchronously via effect
  useEffect(() => {
    if (monacoRef.current) {
      const targetMonaco = monacoRef.current;
      setTimeout(() => {
        const globalWindow = window as unknown as Record<string, unknown>;
        globalWindow.monaco = targetMonaco;
      }, 0);
    }
  }, [monacoRef]);

  // Handle Mounting Deferred Startup
  useEffect(() => {
    const startup = () => {
      fetchDiagnostics();
      fetchFiles();
      connectWebSocket();
    };
    const timer = setTimeout(startup, 0);
    return () => {
      clearTimeout(timer);
      if (wsRef.current) wsRef.current.close();
    };
  }, [fetchDiagnostics, fetchFiles, connectWebSocket]);

  // Handle File List Auto-Loader
  useEffect(() => {
    const listLoader = () => {
      if (files.scripts.length > 0 && !activeFile) {
        loadFileContent(files.scripts[0].name);
      } else if (activeFile) {
        const exists = files.scripts.some((f) => f.name === activeFile);
        if (exists && code === "") {
          loadFileContent(activeFile);
        }
      }
    };
    const timer = setTimeout(listLoader, 0);
    return () => clearTimeout(timer);
  }, [files.scripts, activeFile, code, loadFileContent]);

  // Sync startRender callback to ref for auto-rendering
  useEffect(() => {
    startRenderRef.current = startRender;
  }, [startRender]);

  // Clean up autoRender timeout on unmount
  useEffect(() => {
    return () => {
      if (autoRenderTimeoutRef.current) {
        clearTimeout(autoRenderTimeoutRef.current);
      }
    };
  }, []);

  const handleRetryConnection = useCallback(() => {
    fetchDiagnostics();
    fetchFiles();
    connectWebSocket();
  }, [fetchDiagnostics, fetchFiles, connectWebSocket]);

  return (
    <div className="dashboard-grid h-screen w-screen bg-black text-slate-100 flex flex-col font-sans select-none overflow-hidden p-3 gap-3">
      {/* 1. Header Row */}
      <header
        className="glass-panel h-14 flex items-center justify-between px-6 bg-zinc-950 border border-zinc-800 rounded-lg"
        style={{ gridColumn: "1 / 4", gridRow: "1" }}
      >
        <div className="flex items-center gap-2.5">
          <svg
            aria-hidden="true"
            viewBox="0 0 40 32"
            className="h-8 w-10 drop-shadow-[0_0_10px_rgba(56,189,248,0.45)]"
          >
            <defs>
              <linearGradient id="logoBlue" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor="#b7e9ff" />
                <stop offset="45%" stopColor="#38bdf8" />
                <stop offset="100%" stopColor="#1d4ed8" />
              </linearGradient>
              <linearGradient id="logoDark" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor="#6ee7ff" />
                <stop offset="100%" stopColor="#0f172a" />
              </linearGradient>
            </defs>
            <path d="M2 16 13 6v20L2 16Z" fill="url(#logoBlue)" opacity="0.9" />
            <path
              d="M15 5 29 16 15 27v-8l5-3-5-3V5Z"
              fill="url(#logoDark)"
              opacity="0.95"
            />
            <path
              d="M23 6 38 16 23 26l5-10-5-10Z"
              fill="url(#logoBlue)"
              opacity="0.85"
            />
            <path d="M11 10 18 16l-7 6V10Z" fill="#dff7ff" opacity="0.45" />
          </svg>
          <h1 className="font-outfit text-[22px] leading-none font-semibold tracking-[0.08em] text-slate-100 drop-shadow-[0_0_8px_rgba(255,255,255,0.25)]">
            MANIM COMPOSER
          </h1>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-xs">
            <span
              className={`font-bold ${wsConnected ? "text-white" : "text-red-500"}`}
            >
              {wsConnected ? "Engine Connected" : "Engine Offline"}
            </span>
            {backendError && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleRetryConnection}
                className="h-6 px-2 text-[10px] border-zinc-800 hover:bg-zinc-900"
              >
                <RefreshCw size={10} className="mr-1" /> Reconnect
              </Button>
            )}
          </div>
        </div>
      </header>

      {/* 2. Left Panel: File Browser / Snippets / Assets / Diagnostics */}
      <aside
        className="glass-panel bg-zinc-950 border border-zinc-800 rounded-lg overflow-hidden flex flex-col"
        style={{ gridColumn: "1", gridRow: "2 / 4" }}
      >
        <Tabs
          defaultValue="files"
          className="flex-1 flex flex-col overflow-hidden"
        >
          <TabsList className="grid grid-cols-6 bg-zinc-900/40 border-b border-zinc-800 p-0 rounded-none h-11">
            <TabsTrigger
              value="files"
              className="text-[8px] tracking-wider font-semibold rounded-none py-3 text-slate-400 data-[state=active]:text-white data-[state=active]:bg-zinc-900"
            >
              FILES
            </TabsTrigger>
            <TabsTrigger
              value="wizard"
              className="text-[8px] tracking-wider font-semibold rounded-none py-3 text-slate-400 data-[state=active]:text-white data-[state=active]:bg-zinc-900"
            >
              WIZARD
            </TabsTrigger>
            <TabsTrigger
              value="snippets"
              className="text-[8px] tracking-wider font-semibold rounded-none py-3 text-slate-400 data-[state=active]:text-white data-[state=active]:bg-zinc-900"
            >
              SNIPPETS
            </TabsTrigger>
            <TabsTrigger
              value="latex"
              className="text-[8px] tracking-wider font-semibold rounded-none py-3 text-slate-400 data-[state=active]:text-white data-[state=active]:bg-zinc-900"
            >
              LATEX
            </TabsTrigger>
            <TabsTrigger
              value="assets"
              className="text-[8px] tracking-wider font-semibold rounded-none py-3 text-slate-400 data-[state=active]:text-white data-[state=active]:bg-zinc-900"
            >
              ASSETS
            </TabsTrigger>
            <TabsTrigger
              value="diags"
              className="text-[8px] tracking-wider font-semibold rounded-none py-3 text-slate-400 data-[state=active]:text-white data-[state=active]:bg-zinc-900"
            >
              DIAGS
            </TabsTrigger>
          </TabsList>

          <div className="flex-1 overflow-y-auto p-3">
            <TabsContent value="files" className="mt-0 space-y-4 outline-none">
              <div>
                <div className="flex justify-between items-center mb-2">
                  <h3 className="text-xs font-semibold text-slate-400 tracking-wider">
                    Python Scripts
                  </h3>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setShowNewFileDialog(true)}
                    className="h-6 px-2 text-[10px] bg-zinc-900 border-zinc-800 text-slate-200 hover:bg-zinc-800"
                  >
                    <Plus size={10} className="mr-1" /> New
                  </Button>
                </div>

                <div className="space-y-1">
                  {files.scripts.map((script) => (
                    <div
                      key={script.name}
                      onClick={() => loadFileContent(script.name)}
                      onDoubleClick={() => {
                        setRenamingFile(script.name);
                        setRenameValue(script.name);
                      }}
                      className={`p-2 rounded-lg cursor-pointer flex items-center justify-between border transition-all duration-200 ${activeFile === script.name ? "bg-zinc-900 border-zinc-700 text-white" : "bg-transparent border-transparent hover:bg-zinc-900/40 text-slate-400"}`}
                    >
                      <div className="flex items-center gap-2 min-w-0 flex-1">
                        <FileCode
                          size={14}
                          className={
                            activeFile === script.name
                              ? "text-white"
                              : "text-slate-500"
                          }
                        />
                        {renamingFile === script.name ? (
                          <input
                            type="text"
                            value={renameValue}
                            onChange={(e) => setRenameValue(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") {
                                e.currentTarget.blur();
                              } else if (e.key === "Escape") {
                                shouldCancelRenameRef.current = true;
                                setRenamingFile(null);
                              }
                            }}
                            onBlur={() => {
                              if (shouldCancelRenameRef.current) {
                                shouldCancelRenameRef.current = false;
                                return;
                              }
                              handleRename(script.name, renameValue);
                            }}
                            onClick={(e) => e.stopPropagation()}
                            onDoubleClick={(e) => e.stopPropagation()}
                            onMouseDown={(e) => e.stopPropagation()}
                            autoFocus
                            className="bg-black border border-zinc-700 text-xs text-white px-1 py-0.5 rounded focus:outline-none w-full font-sans"
                          />
                        ) : (
                          <span className="text-xs truncate font-medium">
                            {script.name}
                          </span>
                        )}
                      </div>
                      {renamingFile !== script.name && (
                        <span className="text-[10px] text-slate-500 font-mono shrink-0">
                          {Math.round((script.size / 1024) * 10) / 10} KB
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <h3 className="text-xs font-semibold text-slate-400 tracking-wider mb-2">
                  Rendered Videos
                </h3>
                <div className="space-y-1">
                  {files.media.length === 0 ? (
                    <span className="text-xs text-slate-600 italic block pl-1">
                      No videos rendered yet.
                    </span>
                  ) : (
                    files.media.map((vid) => (
                      <div
                        key={vid.url}
                        onClick={() => {
                          if (vid.url) {
                            setVideoUrl(
                              `${API_BASE}${vid.url}?t=${Date.now()}`,
                            );
                            setVideoKey((prev) => prev + 1);
                            addLog("info", `Loading video file: ${vid.name}`);
                            setSavedPath(`workspace${vid.url}`);
                          }
                        }}
                        className={`p-2 rounded-lg cursor-pointer flex items-center justify-between border transition-all duration-200 ${videoUrl.split("?")[0].endsWith(vid.url || "") ? "bg-zinc-900 border-zinc-700 text-white" : "bg-zinc-950/40 border-zinc-900 hover:bg-zinc-900/30 text-slate-400"}`}
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <Video size={14} className="text-slate-400" />
                          <span className="text-xs truncate">{vid.name}</span>
                        </div>
                        {vid.url && (
                          <a
                            href={`${API_BASE}${vid.url}`}
                            download
                            className="text-slate-500 hover:text-slate-200"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <Download size={12} />
                          </a>
                        )}
                      </div>
                    ))
                  )}
                </div>
              </div>
            </TabsContent>

            <TabsContent
              value="wizard"
              className="mt-0 space-y-3.5 outline-none text-[11px]"
            >
              <div className="flex justify-between items-center mb-1">
                <h3 className="text-xs font-semibold text-slate-400 tracking-wider">
                  Shape Wizard
                </h3>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleInsertSnippet(getGeneratedWizardCode())}
                  className="h-6 px-2 text-[9px] bg-white border-white text-black hover:bg-slate-200 font-bold"
                >
                  <Plus size={10} className="mr-1" /> Insert Code
                </Button>
              </div>

              {/* Form Controls */}
              <div className="space-y-2.5 bg-zinc-950 p-2.5 rounded-lg border border-zinc-900">
                {/* Shape Selector */}
                <div className="space-y-1">
                  <span className="text-[9px] text-slate-500 font-medium uppercase tracking-wider block">
                    Shape Type
                  </span>
                  <Select value={wizardShape} onValueChange={setWizardShape}>
                    <SelectTrigger className="w-full h-7 bg-zinc-900 border-zinc-800 text-[11px] text-slate-200">
                      <SelectValue placeholder="Select Shape" />
                    </SelectTrigger>
                    <SelectContent className="bg-zinc-900 border-zinc-800 text-[11px]">
                      {[
                        "Circle",
                        "Square",
                        "Rectangle",
                        "Triangle",
                        "Line",
                        "Arrow",
                        "Text",
                        "MathTex",
                      ].map((shape) => (
                        <SelectItem
                          key={shape}
                          value={shape}
                          className="text-[11px]"
                        >
                          {shape}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* Conditional Fields: Text */}
                {wizardShape === "Text" && (
                  <div className="space-y-1">
                    <span className="text-[9px] text-slate-500 font-medium uppercase tracking-wider block">
                      Text Content
                    </span>
                    <input
                      type="text"
                      value={wizardText}
                      onChange={(e) => setWizardText(e.target.value)}
                      className="w-full bg-black border border-zinc-800 rounded px-2 py-1 text-[11px] text-slate-200 focus:outline-none focus:border-zinc-700"
                    />
                  </div>
                )}

                {wizardShape === "MathTex" && (
                  <div className="space-y-1">
                    <span className="text-[9px] text-slate-500 font-medium uppercase tracking-wider block">
                      LaTeX Equation
                    </span>
                    <input
                      type="text"
                      value={wizardLatex}
                      onChange={(e) => setWizardLatex(e.target.value)}
                      className="w-full bg-black border border-zinc-800 rounded px-2 py-1 text-[11px] text-slate-200 focus:outline-none focus:border-zinc-700 font-mono"
                    />
                  </div>
                )}

                {/* Color Selector */}
                <div className="space-y-1">
                  <span className="text-[9px] text-slate-500 font-medium uppercase tracking-wider block">
                    Color Preset
                  </span>
                  <Select value={wizardColor} onValueChange={setWizardColor}>
                    <SelectTrigger className="w-full h-7 bg-zinc-900 border-zinc-800 text-[11px] text-slate-200">
                      <SelectValue placeholder="Select Color" />
                    </SelectTrigger>
                    <SelectContent className="bg-zinc-900 border-zinc-800 text-[11px]">
                      {[
                        "BLUE",
                        "PINK",
                        "YELLOW",
                        "RED",
                        "GREEN",
                        "PURPLE",
                        "ORANGE",
                        "TEAL",
                        "WHITE",
                        "GOLD",
                        "GREY",
                      ].map((color) => (
                        <SelectItem
                          key={color}
                          value={color}
                          className="text-[11px]"
                        >
                          {color}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* Transformation Fields in a Grid */}
                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-1">
                    <span className="text-[9px] text-slate-500 font-medium uppercase tracking-wider block">
                      Scale
                    </span>
                    <input
                      type="text"
                      value={wizardScale}
                      onChange={(e) => setWizardScale(e.target.value)}
                      className="w-full bg-black border border-zinc-800 rounded px-2 py-1 text-[11px] text-slate-200 focus:outline-none focus:border-zinc-700 font-mono"
                    />
                  </div>
                  <div className="space-y-1">
                    <span className="text-[9px] text-slate-500 font-medium uppercase tracking-wider block">
                      Rotation (deg)
                    </span>
                    <input
                      type="text"
                      value={wizardRotation}
                      onChange={(e) => setWizardRotation(e.target.value)}
                      className="w-full bg-black border border-zinc-800 rounded px-2 py-1 text-[11px] text-slate-200 focus:outline-none focus:border-zinc-700 font-mono"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-1">
                    <span className="text-[9px] text-slate-500 font-medium uppercase tracking-wider block">
                      Shift X
                    </span>
                    <input
                      type="text"
                      value={wizardShiftX}
                      onChange={(e) => setWizardShiftX(e.target.value)}
                      className="w-full bg-black border border-zinc-800 rounded px-2 py-1 text-[11px] text-slate-200 focus:outline-none focus:border-zinc-700 font-mono"
                    />
                  </div>
                  <div className="space-y-1">
                    <span className="text-[9px] text-slate-500 font-medium uppercase tracking-wider block">
                      Shift Y
                    </span>
                    <input
                      type="text"
                      value={wizardShiftY}
                      onChange={(e) => setWizardShiftY(e.target.value)}
                      className="w-full bg-black border border-zinc-800 rounded px-2 py-1 text-[11px] text-slate-200 focus:outline-none focus:border-zinc-700 font-mono"
                    />
                  </div>
                </div>
              </div>

              {/* Animations Section */}
              <div className="space-y-2.5 bg-zinc-950 p-2.5 rounded-lg border border-zinc-900">
                <div className="space-y-1">
                  <span className="text-[9px] text-slate-500 font-medium uppercase tracking-wider block">
                    Entry Animation
                  </span>
                  <Select
                    value={wizardEntryAnim}
                    onValueChange={setWizardEntryAnim}
                  >
                    <SelectTrigger className="w-full h-7 bg-zinc-900 border-zinc-800 text-[11px] text-slate-200">
                      <SelectValue placeholder="Entry" />
                    </SelectTrigger>
                    <SelectContent className="bg-zinc-900 border-zinc-800 text-[11px]">
                      {[
                        "Create",
                        "Write",
                        "FadeIn",
                        "GrowFromCenter",
                        "none",
                      ].map((anim) => (
                        <SelectItem
                          key={anim}
                          value={anim}
                          className="text-[11px]"
                        >
                          {anim}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1">
                  <span className="text-[9px] text-slate-500 font-medium uppercase tracking-wider block">
                    Action Animation
                  </span>
                  <Select
                    value={wizardActionAnim}
                    onValueChange={setWizardActionAnim}
                  >
                    <SelectTrigger className="w-full h-7 bg-zinc-900 border-zinc-800 text-[11px] text-slate-200">
                      <SelectValue placeholder="Action" />
                    </SelectTrigger>
                    <SelectContent className="bg-zinc-900 border-zinc-800 text-[11px]">
                      {["none", "Rotate", "ScaleUp", "ColorChange"].map(
                        (anim) => (
                          <SelectItem
                            key={anim}
                            value={anim}
                            className="text-[11px]"
                          >
                            {anim}
                          </SelectItem>
                        ),
                      )}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1">
                  <span className="text-[9px] text-slate-500 font-medium uppercase tracking-wider block">
                    Exit Animation
                  </span>
                  <Select
                    value={wizardExitAnim}
                    onValueChange={setWizardExitAnim}
                  >
                    <SelectTrigger className="w-full h-7 bg-zinc-900 border-zinc-800 text-[11px] text-slate-200">
                      <SelectValue placeholder="Exit" />
                    </SelectTrigger>
                    <SelectContent className="bg-zinc-900 border-zinc-800 text-[11px]">
                      {["FadeOut", "Uncreate", "none"].map((anim) => (
                        <SelectItem
                          key={anim}
                          value={anim}
                          className="text-[11px]"
                        >
                          {anim}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {/* Code Preview Block */}
              <div className="space-y-1">
                <span className="text-[9px] text-slate-500 font-medium uppercase tracking-wider block">
                  Generated Code Block
                </span>
                <pre className="p-2 bg-black border border-zinc-900 rounded font-mono text-[9px] text-slate-300 overflow-x-auto select-text whitespace-pre">
                  {getGeneratedWizardCode()}
                </pre>
              </div>
            </TabsContent>

            <TabsContent
              value="snippets"
              className="mt-0 space-y-2 outline-none"
            >
              <span className="text-[10px] text-slate-500 block mb-2">
                Use ready-to-render templates or insert specific scenes.
              </span>
              <div className="space-y-2">
                {SNIPPETS.map((snippet) => (
                  <div
                    key={snippet.title}
                    className="p-3 rounded-lg bg-zinc-950 border border-zinc-900 flex flex-col gap-2.5"
                  >
                    <div>
                      <div className="flex justify-between items-center mb-1">
                        <h4 className="text-xs font-semibold text-slate-200">
                          {snippet.title}
                        </h4>
                        <span className="text-[9px] bg-zinc-900 border border-zinc-800 text-slate-300 px-1.5 py-0.5 rounded font-semibold">
                          {snippet.category}
                        </span>
                      </div>
                      <p className="text-[10px] text-slate-400 leading-normal">
                        {snippet.description}
                      </p>
                    </div>
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleLoadTemplate(snippet.code)}
                        className="flex-1 h-6 text-[9px] bg-zinc-900 border-zinc-800 text-slate-200 hover:bg-zinc-850 font-semibold"
                      >
                        Load Script
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleInsertSnippet(snippet.code)}
                        className="flex-1 h-6 text-[9px] bg-zinc-900 border-zinc-800 text-slate-200 hover:bg-zinc-850 font-semibold"
                      >
                        Insert Cursor
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </TabsContent>

            <TabsContent
              value="latex"
              className="mt-0 space-y-4 outline-none flex flex-col h-[calc(100vh-180px)]"
            >
              <div className="space-y-3 shrink-0">
                <div className="flex justify-between items-center">
                  <h3 className="text-xs font-semibold text-slate-400 tracking-wider">
                    LaTeX Sandbox
                  </h3>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleInsertMathTex(latexInput)}
                    className="h-6 px-2 text-[9px] bg-zinc-900 border-zinc-800 text-slate-200 hover:bg-zinc-800"
                  >
                    <Plus size={10} className="mr-1" /> Insert MathTex
                  </Button>
                </div>

                <textarea
                  value={latexInput}
                  onChange={(e) => setLatexInput(e.target.value)}
                  placeholder="Type LaTeX formula, e.g. e^{i\pi} + 1 = 0"
                  className="w-full bg-black border border-zinc-800 rounded-md p-2 text-[11px] text-slate-200 focus:outline-none focus:border-zinc-700 font-mono h-16 resize-none"
                />

                <div className="p-3 bg-zinc-950 border border-zinc-900 rounded-md flex items-center justify-center min-h-[50px] max-h-[80px] overflow-auto text-white">
                  <LaTeX math={latexInput} block />
                </div>
              </div>

              <div className="flex-1 overflow-y-auto min-h-[120px] mt-3">
                <h4 className="text-[10px] font-semibold text-slate-500 tracking-wider mb-2">
                  Equation Templates
                </h4>
                <div className="grid grid-cols-1 gap-1">
                  {LATEX_TEMPLATES.map((tmpl) => (
                    <div
                      key={tmpl.name}
                      onClick={() => setLatexInput(tmpl.code)}
                      className="p-1.5 rounded border border-zinc-900 hover:border-zinc-800 bg-zinc-950 hover:bg-zinc-900/30 cursor-pointer transition-all flex justify-between items-center"
                    >
                      <div className="text-[10px] text-slate-350 truncate pr-1">
                        <span className="font-semibold block text-[9px] text-slate-400">
                          {tmpl.name}
                        </span>
                        <code className="text-slate-500 text-[9px] font-mono">
                          {tmpl.code}
                        </code>
                      </div>
                      <span
                        onClick={(e) => {
                          e.stopPropagation();
                          handleInsertMathTex(tmpl.code);
                        }}
                        className="text-[9px] text-slate-400 hover:text-white bg-zinc-900 hover:bg-zinc-800 px-1.5 py-0.5 border border-zinc-800 rounded shrink-0 font-medium cursor-pointer"
                      >
                        Insert
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </TabsContent>

            <TabsContent value="assets" className="mt-0 space-y-3 outline-none">
              <label className="border border-dashed border-zinc-800 bg-zinc-950/40 rounded-lg p-5 text-center flex flex-col items-center gap-2 cursor-pointer hover:border-zinc-700 hover:bg-zinc-900/20 transition-all">
                <Upload size={20} className="text-slate-400" />
                <span className="text-xs font-medium">Upload Asset</span>
                <span className="text-[10px] text-slate-500">
                  SVG, PNG, MP3, WAV
                </span>
                <input
                  type="file"
                  onChange={handleAssetUpload}
                  className="hidden"
                />
              </label>

              <div>
                <h3 className="text-xs font-semibold text-slate-400 tracking-wider mb-2">
                  Library Assets
                </h3>
                <div className="space-y-1">
                  {files.assets.length === 0 ? (
                    <span className="text-xs text-slate-600 italic block pl-1">
                      No assets uploaded yet.
                    </span>
                  ) : (
                    files.assets.map((asset) => (
                      <div
                        key={asset.name}
                        className="p-2 rounded-lg bg-zinc-950 border border-zinc-900 flex items-center justify-between gap-2 text-xs text-slate-400 group"
                      >
                        <div className="flex items-center gap-2 min-w-0 flex-1">
                          <Layers
                            size={12}
                            className="text-slate-500 shrink-0"
                          />
                          <span className="truncate" title={asset.name}>
                            {asset.name}
                          </span>
                        </div>

                        <div className="flex items-center gap-1.5 shrink-0">
                          <span className="text-[9px] text-slate-600 font-mono group-hover:hidden">
                            {Math.round((asset.size / 1024) * 10) / 10} KB
                          </span>
                          <button
                            onClick={() => handleInsertAssetPath(asset.name)}
                            title="Insert asset path at cursor"
                            className="p-1 hover:text-white rounded bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 cursor-pointer hidden group-hover:block transition-all"
                          >
                            <Plus size={10} />
                          </button>
                          <button
                            onClick={() => handleCopyAssetPath(asset.name)}
                            title="Copy path to clipboard"
                            className="p-1 hover:text-white rounded bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 cursor-pointer hidden group-hover:block transition-all"
                          >
                            {copiedAsset === asset.name ? (
                              <Check size={10} className="text-emerald-500" />
                            ) : (
                              <Copy size={10} />
                            )}
                          </button>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </TabsContent>

            <TabsContent value="diags" className="mt-0 space-y-4 outline-none">
              {diagnostics ? (
                <div className="space-y-4 text-xs">
                  <div>
                    <h4 className="font-semibold text-slate-400 mb-1">
                      PC Description Profile
                    </h4>
                    <p className="text-slate-300 text-[11px] leading-relaxed">
                      {diagnostics.description}
                    </p>
                  </div>

                  <hr className="border-zinc-800" />

                  <div>
                    <h4 className="font-semibold text-slate-400 mb-2">
                      Hardware Specs
                    </h4>
                    <div className="space-y-1.5 text-[11px]">
                      <div className="flex justify-between">
                        <span className="text-slate-500">CPU Name:</span>
                        <span className="text-slate-250 font-medium text-right max-w-[160px] truncate">
                          {diagnostics.hardware.cpu.model}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">Logical Threads:</span>
                        <span className="text-slate-250 font-mono">
                          {diagnostics.hardware.cpu.logical_threads} Threads
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">RAM capacity:</span>
                        <span className="text-slate-250 font-mono">
                          {diagnostics.hardware.ram_gb} GB
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">Graphics Device:</span>
                        <span className="text-slate-250 text-right max-w-[160px] truncate">
                          {diagnostics.hardware.gpu.devices[0]?.name || "N/A"}
                        </span>
                      </div>
                    </div>
                  </div>

                  <hr className="border-zinc-800" />

                  <div>
                    <h4 className="font-semibold text-slate-400 mb-2">
                      Software Environment
                    </h4>
                    <div className="space-y-1.5 text-[11px]">
                      <div className="flex justify-between items-center">
                        <span>Manim CE CLI:</span>
                        <span
                          className={
                            diagnostics.dependencies.manim !== "Not Found"
                              ? "text-slate-200 font-semibold"
                              : "text-zinc-500"
                          }
                        >
                          {diagnostics.dependencies.manim !== "Not Found"
                            ? "Detected"
                            : "Not Found"}
                        </span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span>FFmpeg Binaries:</span>
                        <span
                          className={
                            diagnostics.dependencies.ffmpeg !== "Not Found"
                              ? "text-slate-200 font-semibold"
                              : "text-zinc-500"
                          }
                        >
                          {diagnostics.dependencies.ffmpeg !== "Not Found"
                            ? "Detected"
                            : "Not Found"}
                        </span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span>LaTeX Compiler:</span>
                        <span
                          className={
                            diagnostics.dependencies.latex !== "Not Found"
                              ? "text-slate-200"
                              : "text-zinc-500"
                          }
                        >
                          {diagnostics.dependencies.latex !== "Not Found"
                            ? "Installed"
                            : "Missing"}
                        </span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span>dvisvgm Converter:</span>
                        <span
                          className={
                            diagnostics.dependencies.dvisvgm !== "Not Found"
                              ? "text-slate-200"
                              : "text-zinc-500"
                          }
                        >
                          {diagnostics.dependencies.dvisvgm !== "Not Found"
                            ? "Installed"
                            : "Missing"}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="mt-4 pt-1">
                    <Button
                      variant="outline"
                      onClick={() => setShowOnboarding(true)}
                      className="w-full text-xs h-8 border-zinc-800 text-slate-350 hover:bg-zinc-900 hover:text-white font-semibold font-outfit"
                    >
                      Launch Setup Wizard
                    </Button>
                  </div>
                </div>
              ) : (
                <span className="text-xs text-slate-600 block">
                  Querying diagnostics profile...
                </span>
              )}
            </TabsContent>
          </div>
        </Tabs>
      </aside>

      {/* 3. Center Panel: Code Editor */}
      <main
        className="glass-panel bg-zinc-950 border border-zinc-800 rounded-lg overflow-hidden flex flex-col"
        style={{ gridColumn: "2", gridRow: "2" }}
      >
        {diagnostics && !diagnostics.dependencies.latex_available && (
          <div className="bg-white text-black px-4 py-2.5 flex items-center justify-between text-xs border-b border-zinc-800 shrink-0 select-text">
            <div className="flex items-center gap-2 font-semibold">
              <AlertTriangle size={14} className="stroke-[2.5]" />
              <span>
                LaTeX compiler is required for math symbols rendering. Live
                preview fallback is standard Text.
              </span>
            </div>
            <Button
              size="sm"
              onClick={handleInstallLatex}
              disabled={isInstallingLatex}
              className="h-6 px-2.5 text-[10px] font-bold bg-black text-white hover:bg-zinc-900 border border-black font-mono"
            >
              {isInstallingLatex ? "Installing..." : "Install LaTeX Now"}
            </Button>
          </div>
        )}

        {/* Editor Action Bar */}
        <div className="flex justify-between items-center flex-wrap gap-2 px-4 py-3 bg-zinc-950 border-b border-zinc-800">
          <div className="flex items-center gap-2 flex-wrap">
            <FileText size={14} className="text-slate-400" />
            <span className="text-xs font-semibold text-slate-200">
              {activeFile || "No Active File"}
            </span>

            <Button
              variant="outline"
              size="sm"
              onClick={() => handleSave(false)}
              disabled={isSaving}
              className="h-7 text-xs bg-zinc-900 border-zinc-800 hover:bg-zinc-800"
            >
              <Save size={12} className="mr-1" /> {isSaving ? "Saving" : "Save"}
            </Button>

            {/* Glowing B&W Render Button */}
            {isRendering ? (
              <Button
                size="sm"
                onClick={cancelRender}
                className="h-7 text-xs font-bold bg-zinc-800 hover:bg-zinc-700 text-white border border-zinc-700 transition-all"
              >
                <Square size={12} className="mr-1" /> Cancel
              </Button>
            ) : (
              <Button
                size="sm"
                onClick={startRender}
                disabled={!wsConnected}
                className={`h-7 text-xs font-bold transition-all duration-200 border ${wsConnected ? "bg-white hover:bg-slate-200 text-black border-white shadow-sm" : "bg-zinc-900 text-zinc-600 border-zinc-800 cursor-not-allowed"}`}
              >
                <Play size={12} className="mr-1 fill-current" /> Render
              </Button>
            )}

            <label className="flex items-center gap-1.5 text-xs text-slate-400 cursor-pointer ml-2 shrink-0">
              <input
                type="checkbox"
                checked={autoRender}
                onChange={(e) => setAutoRender(e.target.checked)}
                className="rounded border-zinc-800 bg-zinc-900 focus:ring-0 text-white w-3 h-3"
              />
              <span
                className={
                  autoRender ? "text-white font-medium" : "text-slate-400"
                }
              >
                Auto-Render
              </span>
            </label>
          </div>

          <div className="flex items-center gap-3 flex-wrap">
            {/* Scene Selector */}
            <div className="flex items-center gap-2 text-xs">
              <span className="text-slate-500">Scene:</span>
              <Select
                value={selectedScene}
                onValueChange={setSelectedScene}
                disabled={scenes.length === 0}
              >
                <SelectTrigger className="w-[150px] h-7 bg-zinc-900 border-zinc-800 text-xs text-slate-200">
                  <SelectValue
                    placeholder={
                      scenes.length === 0 ? "No scenes" : "Select Scene"
                    }
                  />
                </SelectTrigger>
                <SelectContent className="bg-zinc-900 border-zinc-800 text-xs">
                  {scenes.map((scene) => (
                    <SelectItem key={scene} value={scene} className="text-xs">
                      {scene}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Quality Selector */}
            <div className="flex items-center gap-2 text-xs">
              <span className="text-slate-500">Quality:</span>
              <Select value={quality} onValueChange={setQuality}>
                <SelectTrigger className="w-[140px] h-7 bg-zinc-900 border-zinc-800 text-xs text-slate-200">
                  <SelectValue placeholder="Select Quality" />
                </SelectTrigger>
                <SelectContent className="bg-zinc-900 border-zinc-800 text-xs">
                  <SelectItem value="l" className="text-xs">
                    Low (480p 15fps)
                  </SelectItem>
                  <SelectItem value="m" className="text-xs">
                    Medium (720p 30fps)
                  </SelectItem>
                  <SelectItem value="h" className="text-xs">
                    High (1080p 60fps)
                  </SelectItem>
                  <SelectItem value="k" className="text-xs">
                    4K (2160p 60fps)
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* OpenGL Hardware check */}
            {diagnostics?.opengl_supported && (
              <label className="flex items-center gap-1.5 text-[11px] text-slate-400 cursor-pointer">
                <input
                  type="checkbox"
                  checked={useOpengl}
                  onChange={(e) => setUseOpengl(e.target.checked)}
                  className="rounded border-zinc-800 bg-zinc-900"
                />
                <span className={useOpengl ? "text-white" : "text-slate-500"}>
                  OpenGL HW
                </span>
              </label>
            )}
          </div>
        </div>

        {/* Monaco Editor Buffer */}
        <div className="flex-1 relative">
          <Editor
            height="100%"
            language="python"
            theme="vs-dark"
            value={code}
            onChange={(val) => {
              const newCode = val || "";
              setCode(newCode);

              if (autoRender && selectedScene && wsConnected) {
                if (autoRenderTimeoutRef.current) {
                  clearTimeout(autoRenderTimeoutRef.current);
                }
                autoRenderTimeoutRef.current = setTimeout(() => {
                  if (startRenderRef.current) {
                    startRenderRef.current();
                  }
                }, 2000);
              }
            }}
            onMount={handleEditorDidMount}
            options={{
              fontSize: 13,
              fontFamily: "Fira Code, monospace",
              minimap: { enabled: false },
              wordWrap: "on",
              scrollBeyondLastLine: false,
              automaticLayout: true,
              tabSize: 4,
              padding: { top: 8 },
            }}
          />
        </div>
      </main>

      {/* 4. Right Panel: Video Previewer */}
      <section
        className="glass-panel bg-zinc-950 border border-zinc-800 rounded-lg overflow-hidden flex flex-col"
        style={{ gridColumn: "3", gridRow: "2" }}
      >
        <div className="flex items-center justify-between px-4 py-3 bg-zinc-950 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <Video size={14} className="text-slate-400" />
            <h3 className="text-xs font-semibold text-slate-200">
              Live Video Preview
            </h3>
          </div>
          {files.media.length > 0 && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setShowCompareDialog(true);
                if (files.media.length > 0) {
                  setCompareVideoA(`${API_BASE}${files.media[0].url}`);
                  if (files.media.length > 1) {
                    setCompareVideoB(`${API_BASE}${files.media[1].url}`);
                  } else {
                    setCompareVideoB(`${API_BASE}${files.media[0].url}`);
                  }
                }
              }}
              className="h-6 px-2 text-[10px] bg-zinc-900 border-zinc-800 text-slate-300 hover:bg-zinc-800"
            >
              Compare Renders
            </Button>
          )}
        </div>

        <div className="flex-1 bg-black flex items-center justify-center relative border-t border-zinc-900">
          {videoUrl ? (
            <video
              key={videoKey}
              src={videoUrl}
              controls
              className="w-full h-full max-h-full object-contain"
              autoPlay
              muted
              playsInline
            >
              Browser tag error.
            </video>
          ) : (
            <div className="text-center p-5 text-slate-500 flex flex-col items-center gap-2">
              <Video size={32} className="opacity-30" />
              <span className="text-xs">
                No video loaded. Complete a render to preview.
              </span>
            </div>
          )}
        </div>
        {savedPath && (
          <div className="bg-zinc-950 border-t border-zinc-900 px-4 py-2 text-[10px] text-slate-400 font-mono truncate select-text shrink-0">
            <span className="text-slate-500">Path: </span>
            <span className="text-white">{savedPath}</span>
          </div>
        )}
      </section>

      {/* 5. Bottom Panel: Console logs */}
      <section
        className="glass-panel bg-zinc-950 border border-zinc-800 rounded-lg overflow-hidden flex flex-col"
        style={{ gridColumn: "2 / 4", gridRow: "3" }}
      >
        <Tabs
          defaultValue="console"
          className="flex-1 flex flex-col overflow-hidden"
        >
          <div className="flex justify-between items-center px-4 py-1.5 bg-zinc-950 border-b border-zinc-800 shrink-0">
            <TabsList className="bg-zinc-900/40 p-0 h-8 border border-zinc-800">
              <TabsTrigger
                value="console"
                className="text-xs px-4 h-full data-[state=active]:bg-zinc-900 data-[state=active]:text-white"
              >
                Console Logs
              </TabsTrigger>
              <TabsTrigger
                value="timeline"
                className="text-xs px-4 h-full data-[state=active]:bg-zinc-900 data-[state=active]:text-white"
              >
                Visual Timeline
              </TabsTrigger>
            </TabsList>
            <div className="flex items-center gap-4">
              {isRendering && (
                <div className="flex items-center gap-3">
                  <Progress value={renderPercent} className="w-[120px] h-1.5" />
                  <span className="text-xs text-white font-bold font-mono">
                    {renderPercent}%
                  </span>
                </div>
              )}
              <button
                onClick={() => setLogs([])}
                className="text-[10px] text-slate-500 hover:text-slate-300"
              >
                Clear Console
              </button>
            </div>
          </div>

          <TabsContent
            value="console"
            className="flex-1 bg-black/90 p-3 font-mono text-[11px] overflow-y-auto space-y-1 select-text outline-none mt-0"
          >
            {logs.length === 0 ? (
              <div className="text-slate-600 italic font-sans pl-1">
                Console idle. Start rendering a scene to view render logs...
              </div>
            ) : (
              logs.map((log, idx) => {
                let color = "text-slate-400";
                if (log.type === "error")
                  color =
                    "text-white underline decoration-dotted font-semibold bg-zinc-950 px-1 border-l-2 border-white";
                else if (log.type === "info") color = "text-slate-400";
                else if (log.type === "success")
                  color = "text-white font-semibold";
                else if (log.type === "warning")
                  color = "text-slate-200 italic font-medium";
                else if (log.stream === "stderr")
                  color = "text-slate-300 italic";

                const lineMatch = log.message?.match(/line (\d+)/i);
                const lineNumber = lineMatch
                  ? parseInt(lineMatch[1], 10)
                  : null;

                return (
                  <div
                    key={idx}
                    className={`${color} wrap-break-word ${lineNumber ? "cursor-pointer hover:bg-zinc-900/60 hover:text-white transition-all pl-1 border-l border-zinc-800" : ""}`}
                    onClick={() => {
                      if (lineNumber && editorRef.current) {
                        const editor =
                          editorRef.current as MonacoEditorInstance;
                        editor.setPosition({ lineNumber, column: 1 });
                        editor.revealLineInCenter(lineNumber);
                        editor.focus();
                        addLog(
                          "info",
                          `Jumped to line ${lineNumber} from compiler log.`,
                        );
                      }
                    }}
                    title={
                      lineNumber
                        ? `Click to jump to line ${lineNumber} in editor`
                        : undefined
                    }
                  >
                    {log.type === "info" && "[INFO] "}
                    {log.type === "error" && "[ERROR] "}
                    {log.type === "success" && "[SUCCESS] "}
                    {log.type === "warning" && "[WARNING] "}
                    {log.message}
                  </div>
                );
              })
            )}
            <div ref={logEndRef} />
          </TabsContent>

          <TabsContent
            value="timeline"
            className="flex-1 bg-black p-3 overflow-x-auto flex flex-col justify-center outline-none mt-0 select-none"
          >
            {!selectedScene ||
            !animations[selectedScene] ||
            animations[selectedScene].length === 0 ? (
              <div className="text-center text-slate-500 text-xs py-4 font-sans">
                No animations parsed for Scene &ldquo;
                {selectedScene || "None Selected"}&rdquo;.
                <br />
                Save your file to compile animations or declare `self.play(...)`
                / `self.wait(...)` in `construct()`.
              </div>
            ) : (
              <div className="flex flex-col gap-2 min-w-max pb-2">
                <div className="text-[10px] text-slate-500 uppercase tracking-widest font-mono pl-1">
                  Animation Sequence &mdash; Scene: {selectedScene}
                </div>
                <div className="flex items-center gap-3 py-1">
                  {animations[selectedScene].map((anim, idx) => {
                    const isPlay = anim.type === "play";
                    return (
                      <div
                        key={idx}
                        onClick={() => {
                          if (editorRef.current) {
                            const editor =
                              editorRef.current as MonacoEditorInstance;
                            editor.setPosition({
                              lineNumber: anim.line,
                              column: 1,
                            });
                            editor.revealLineInCenter(anim.line);
                            editor.focus();
                            addLog(
                              "info",
                              `Jumped to line ${anim.line}: ${anim.label}`,
                            );
                          }
                        }}
                        className={`group relative flex flex-col justify-between p-3 rounded-lg border transition-all duration-200 cursor-pointer h-20 w-48 ${
                          isPlay
                            ? "bg-zinc-900 hover:bg-zinc-800 border-zinc-800 hover:border-zinc-700 text-white shadow-sm"
                            : "bg-zinc-950 hover:bg-zinc-900 border-zinc-900 hover:border-zinc-800 border-dashed text-slate-400"
                        }`}
                      >
                        <div className="flex items-start justify-between">
                          <span className="text-[10px] font-semibold font-mono text-slate-500">
                            STEP {idx + 1}
                          </span>
                          <span className="text-[9px] text-slate-500 bg-zinc-950 px-1 border border-zinc-900 rounded group-hover:border-zinc-800 font-mono">
                            L{anim.line}
                          </span>
                        </div>
                        <div className="text-xs truncate font-medium mt-1 font-mono">
                          {isPlay
                            ? anim.label.replace("Play: ", "")
                            : anim.label}
                        </div>
                        <div className="text-[9px] text-slate-500 font-mono text-right mt-1">
                          {isPlay ? "play()" : "wait()"}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </TabsContent>
        </Tabs>
      </section>

      {/* 6. Footer / Status Telemetry */}
      <footer
        className="glass-panel h-10 flex items-center justify-between px-6 bg-zinc-950 border border-zinc-900 rounded-lg text-[11px] text-slate-400"
        style={{ gridColumn: "1 / 4", gridRow: "4" }}
      >
        <div className="flex items-center gap-5">
          <span>
            Workspace: <strong className="text-slate-200">workspace/</strong>
          </span>
          {diagnostics && (
            <>
              <div className="flex items-center gap-1">
                <Cpu size={12} className="text-slate-500" />
                <span>
                  Threads Allocation: {diagnostics.recommended_threads} worker
                  threads
                </span>
              </div>
              <div className="flex items-center gap-1">
                <HardDrive size={12} className="text-slate-500" />
                <span>
                  Resolution Default: {diagnostics.default_resolution} (
                  {diagnostics.default_fps}fps)
                </span>
              </div>
            </>
          )}
        </div>

        {diagnostics && !diagnostics.dependencies.latex_available && (
          <div className="flex items-center gap-2.5 text-white bg-zinc-900 px-2.5 py-1 rounded border border-zinc-800">
            <AlertTriangle size={12} className="text-white" />
            <span>
              LaTeX not detected. Formulas rendered with standard Text.
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={handleInstallLatex}
              disabled={isInstallingLatex}
              className="h-5 px-1.5 text-[9px] border-zinc-700 text-white bg-zinc-950 hover:bg-white hover:text-black font-semibold"
            >
              {isInstallingLatex ? "Installing..." : "Install LaTeX"}
            </Button>
          </div>
        )}
      </footer>

      {/* Dialog for Creating New File */}
      <Dialog open={showNewFileDialog} onOpenChange={setShowNewFileDialog}>
        <DialogContent className="bg-zinc-950 border-zinc-800 text-slate-100 max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-sm font-semibold tracking-tight text-slate-200 font-outfit">
              Create New Python Script
            </DialogTitle>
          </DialogHeader>
          <form onSubmit={handleCreateFile} className="space-y-4 py-2">
            <div className="space-y-1">
              <label className="text-xs text-slate-400">File Name</label>
              <input
                type="text"
                placeholder="scene_name.py"
                value={newFileName}
                onChange={(e) => setNewFileName(e.target.value)}
                autoFocus
                className="w-full bg-black border border-zinc-800 rounded-md px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-zinc-500"
              />
            </div>
            <DialogFooter className="flex justify-end gap-2 pt-2">
              <DialogClose asChild>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="bg-transparent border-zinc-800 h-8 text-xs"
                >
                  Cancel
                </Button>
              </DialogClose>
              <Button
                type="submit"
                size="sm"
                className="bg-white hover:bg-slate-200 text-black border border-white font-bold h-8 text-xs"
              >
                Create File
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Dialog for Loading Template Confirmation */}
      <Dialog
        open={showLoadTemplateDialog}
        onOpenChange={setShowLoadTemplateDialog}
      >
        <DialogContent className="bg-zinc-950 border-zinc-800 text-slate-100 max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-sm font-semibold tracking-tight text-slate-200 font-outfit">
              Load Template
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <p className="text-xs text-slate-400 leading-relaxed">
              Are you sure you want to load this template? It will replace all
              code in the current editor buffer.
            </p>
            <DialogFooter className="flex justify-end gap-2 pt-2">
              <DialogClose asChild>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="bg-transparent border-zinc-800 h-8 text-xs"
                >
                  Cancel
                </Button>
              </DialogClose>
              <Button
                size="sm"
                onClick={confirmLoadTemplate}
                className="bg-white hover:bg-slate-200 text-black border border-white font-bold h-8 text-xs"
              >
                Load Template
              </Button>
            </DialogFooter>
          </div>
        </DialogContent>
      </Dialog>

      {/* Dialog for Synchronized Video Comparison */}
      <Dialog
        open={showCompareDialog}
        onOpenChange={(open) => {
          setShowCompareDialog(open);
          if (!open) {
            videoARef.current?.pause();
            videoBRef.current?.pause();
            setComparePlaying(false);
          }
        }}
      >
        <DialogContent className="bg-zinc-950 border-zinc-800 text-slate-100 max-w-5xl w-[90vw] h-[85vh] flex flex-col p-4">
          <DialogHeader className="shrink-0 flex flex-row items-center justify-between pb-2 border-b border-zinc-900">
            <DialogTitle className="text-sm font-semibold tracking-tight text-slate-200 font-outfit">
              Synchronized Render Comparison
            </DialogTitle>
          </DialogHeader>

          {/* Target Selectors */}
          <div className="flex gap-4 py-2 shrink-0 bg-zinc-950 z-10">
            <div className="flex-1 flex items-center gap-2 text-xs">
              <span className="text-slate-500 shrink-0">Left Video (A):</span>
              <Select value={compareVideoA} onValueChange={setCompareVideoA}>
                <SelectTrigger className="w-full h-8 bg-zinc-900 border-zinc-800 text-xs text-slate-200">
                  <SelectValue placeholder="Select Video A" />
                </SelectTrigger>
                <SelectContent className="bg-zinc-900 border-zinc-800 text-xs">
                  {files.media.map((vid) => (
                    <SelectItem
                      key={vid.url}
                      value={`${API_BASE}${vid.url}`}
                      className="text-xs"
                    >
                      {vid.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex-1 flex items-center gap-2 text-xs">
              <span className="text-slate-500 shrink-0">Right Video (B):</span>
              <Select value={compareVideoB} onValueChange={setCompareVideoB}>
                <SelectTrigger className="w-full h-8 bg-zinc-900 border-zinc-800 text-xs text-slate-200">
                  <SelectValue placeholder="Select Video B" />
                </SelectTrigger>
                <SelectContent className="bg-zinc-900 border-zinc-800 text-xs">
                  {files.media.map((vid) => (
                    <SelectItem
                      key={vid.url}
                      value={`${API_BASE}${vid.url}`}
                      className="text-xs"
                    >
                      {vid.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Video Frames Side-by-Side */}
          <div className="flex-1 min-h-0 grid grid-cols-2 gap-4 bg-black rounded-lg border border-zinc-900 p-2 overflow-hidden items-center justify-center">
            <div className="w-full h-full flex flex-col justify-center items-center relative overflow-hidden bg-zinc-950/40 rounded">
              {compareVideoA ? (
                <video
                  ref={videoARef}
                  src={compareVideoA}
                  onTimeUpdate={handleVideoTimeUpdate}
                  onLoadedMetadata={handleVideoLoadedMetadata}
                  className="w-full h-full max-h-full object-contain"
                  muted
                  playsInline
                />
              ) : (
                <span className="text-xs text-slate-600">
                  Select left video
                </span>
              )}
              <div className="absolute top-2 left-2 px-2 py-0.5 bg-black/80 rounded border border-zinc-800 text-[10px] text-white font-mono">
                VIDEO A
              </div>
            </div>

            <div className="w-full h-full flex flex-col justify-center items-center relative overflow-hidden bg-zinc-950/40 rounded">
              {compareVideoB ? (
                <video
                  ref={videoBRef}
                  src={compareVideoB}
                  onLoadedMetadata={handleVideoLoadedMetadata}
                  className="w-full h-full max-h-full object-contain"
                  muted
                  playsInline
                />
              ) : (
                <span className="text-xs text-slate-600">
                  Select right video
                </span>
              )}
              <div className="absolute top-2 left-2 px-2 py-0.5 bg-black/80 rounded border border-zinc-800 text-[10px] text-white font-mono">
                VIDEO B
              </div>
            </div>
          </div>

          {/* Timeline & Playback Controls */}
          <div className="shrink-0 pt-3 space-y-3 bg-zinc-950 z-10 border-t border-zinc-900 mt-2">
            <div className="flex items-center gap-4">
              <Button
                type="button"
                onClick={handleComparePlayToggle}
                className="h-8 w-24 bg-white text-black font-bold hover:bg-slate-200 border border-white text-xs flex items-center justify-center gap-1.5"
              >
                {comparePlaying ? (
                  <>
                    <Square size={12} className="fill-current" /> Pause
                  </>
                ) : (
                  <>
                    <Play size={12} className="fill-current" /> Play Sync
                  </>
                )}
              </Button>

              {/* Master Scrubber Timeline */}
              <div className="flex-1 flex items-center gap-2 text-xs">
                <span className="font-mono text-slate-500 text-[10px]">
                  {Math.round(compareTime * 10) / 10}s
                </span>
                <input
                  type="range"
                  min={0}
                  max={compareDuration}
                  step={0.02}
                  value={compareTime}
                  onChange={(e) =>
                    handleCompareTimeChange(parseFloat(e.target.value))
                  }
                  className="flex-1 h-1.5 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-white"
                />
                <span className="font-mono text-slate-500 text-[10px]">
                  {Math.round(compareDuration * 10) / 10}s
                </span>
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Onboarding Setup Wizard Dialog */}
      <Dialog open={showOnboarding} onOpenChange={setShowOnboarding}>
        <DialogContent className="bg-zinc-950 border-zinc-800 text-slate-100 max-w-lg select-text">
          <DialogHeader>
            <DialogTitle className="text-lg font-bold tracking-tight text-white font-outfit flex items-center gap-2">
              <Sparkles className="text-slate-400 h-5 w-5" /> Setup Environment
              Wizard
            </DialogTitle>
          </DialogHeader>

          <div className="py-4 space-y-4 text-xs">
            <p className="text-slate-400 leading-relaxed font-sans">
              Welcome to <strong>Manim Composer</strong>! To compile math
              animations, we need some system components. Check the status of
              your environment and install missing dependencies below:
            </p>

            <div className="space-y-3 bg-zinc-900/60 p-4 rounded-lg border border-zinc-800 font-mono">
              {/* Python Status */}
              <div className="flex items-center justify-between border-b border-zinc-800/40 pb-2.5">
                <div>
                  <div className="text-white font-semibold flex items-center gap-1.5 font-outfit">
                    Python Runtime
                  </div>
                  <div className="text-[10px] text-slate-500 mt-0.5">
                    Required for backend operations
                  </div>
                </div>
                <span className="text-[10px] bg-zinc-800 text-slate-300 px-2 py-0.5 rounded border border-zinc-800 font-sans font-medium">
                  Detected
                </span>
              </div>

              {/* FFmpeg Status */}
              <div className="flex items-center justify-between border-b border-zinc-800/40 pb-2.5">
                <div>
                  <div className="text-white font-semibold flex items-center gap-1.5 font-outfit">
                    FFmpeg Media Encoder
                  </div>
                  <div className="text-[10px] text-slate-500 mt-0.5 max-w-[320px] truncate">
                    {diagnostics?.dependencies.ffmpeg &&
                    diagnostics.dependencies.ffmpeg !== "Not Found"
                      ? `Installed: ${diagnostics.dependencies.ffmpeg}`
                      : "Required for video rendering & stitching"}
                  </div>
                </div>
                {diagnostics?.dependencies.ffmpeg &&
                diagnostics.dependencies.ffmpeg !== "Not Found" ? (
                  <span className="text-[10px] bg-white text-black font-semibold px-2 py-0.5 rounded border border-white font-sans">
                    Detected
                  </span>
                ) : (
                  <Button
                    onClick={handleInstallFFmpeg}
                    disabled={isInstallingFFmpeg}
                    className="h-6 px-2 text-[10px] bg-white text-black hover:bg-slate-200 border border-white font-semibold font-sans"
                  >
                    {isInstallingFFmpeg ? "Installing..." : "Install (winget)"}
                  </Button>
                )}
              </div>

              {/* Manim CE Status */}
              <div className="flex items-center justify-between border-b border-zinc-800/40 pb-2.5">
                <div>
                  <div className="text-white font-semibold flex items-center gap-1.5 font-outfit">
                    Manim Community Edition
                  </div>
                  <div className="text-[10px] text-slate-500 mt-0.5 max-w-[320px] truncate">
                    {diagnostics?.dependencies.manim &&
                    diagnostics.dependencies.manim !== "Not Found"
                      ? `Installed: ${diagnostics.dependencies.manim}`
                      : "Core animation engine"}
                  </div>
                </div>
                {diagnostics?.dependencies.manim &&
                diagnostics.dependencies.manim !== "Not Found" ? (
                  <span className="text-[10px] bg-white text-black font-semibold px-2 py-0.5 rounded border border-white font-sans">
                    Detected
                  </span>
                ) : (
                  <Button
                    onClick={handleInstallManim}
                    disabled={isInstallingManim}
                    className="h-6 px-2 text-[10px] bg-white text-black hover:bg-slate-200 border border-white font-semibold font-sans"
                  >
                    {isInstallingManim ? "Installing..." : "Install (pip)"}
                  </Button>
                )}
              </div>

              {/* LaTeX Status */}
              <div className="flex items-center justify-between pb-0">
                <div>
                  <div className="text-white font-semibold flex items-center gap-1.5 font-outfit">
                    LaTeX Math Tools (Optional)
                  </div>
                  <div className="text-[10px] text-slate-500 mt-0.5 max-w-[320px] truncate font-sans">
                    {diagnostics?.dependencies.latex_available
                      ? "Installed and active"
                      : "Required for formula typesetting"}
                  </div>
                </div>
                {diagnostics?.dependencies.latex_available ? (
                  <span className="text-[10px] bg-white text-black font-semibold px-2 py-0.5 rounded border border-white font-sans">
                    Detected
                  </span>
                ) : (
                  <Button
                    onClick={handleInstallLatex}
                    disabled={isInstallingLatex}
                    className="h-6 px-2 text-[10px] bg-zinc-900 text-white hover:bg-zinc-800 border border-zinc-800 font-semibold font-sans"
                  >
                    {isInstallingLatex ? "Installing..." : "Install (winget)"}
                  </Button>
                )}
              </div>
            </div>

            <div className="text-[10px] text-slate-500 leading-relaxed font-sans">
              * Note: Installations using winget/pip are supported automatically
              on Windows. If you are on Linux or macOS, please follow the manual
              install steps listed in the README.md.
            </div>
          </div>

          <DialogFooter className="border-t border-zinc-900 pt-3 flex justify-end gap-2">
            <Button
              variant="outline"
              onClick={() => setShowOnboarding(false)}
              className="h-8 px-4 text-xs border-zinc-800 text-slate-400 hover:text-white hover:bg-zinc-900 font-semibold font-outfit"
            >
              Skip Setup
            </Button>
            <Button
              onClick={() => setShowOnboarding(false)}
              disabled={
                !diagnostics?.dependencies.manim ||
                diagnostics.dependencies.manim === "Not Found" ||
                !diagnostics?.dependencies.ffmpeg ||
                diagnostics.dependencies.ffmpeg === "Not Found"
              }
              className="h-8 px-4 text-xs bg-white text-black hover:bg-slate-200 border border-white font-bold font-outfit"
            >
              Let's Go
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
