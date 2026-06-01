import React, { useState, useEffect, useRef, useCallback } from "react";
import Editor from "@monaco-editor/react";
import {
  Play,
  Square,
  Terminal,
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
  FileCode
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
const BACKEND_HOST = "localhost:8000";
const API_BASE = `http://${BACKEND_HOST}`;
const WS_BASE = `ws://${BACKEND_HOST}`;

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
  type: "log" | "error" | "info" | "status" | "progress" | "file_ready" | "latex_error_warning" | "warning" | "success" | "result";
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
    }>
  ) => void;
}

interface MonacoGlobal {
  Range: new (
    startLine: number,
    startCol: number,
    endLine: number,
    endCol: number
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
    code: `from manim import *\n\nclass SquareToCircle(Scene):\n    def construct(self):\n        circle = Circle(color=PINK)\n        square = Square(color=BLUE)\n        square.flip(RIGHT)\n        square.rotate(PI / 8)\n        self.play(Create(square))\n        self.play(Transform(square, circle))\n        self.play(FadeOut(square))\n`
  },
  {
    title: "Kinetic Typography",
    description: "Write styled header text and draw background accent rings.",
    category: "Text",
    code: `from manim import *\n\nclass KineticTitle(Scene):\n    def construct(self):\n        title = Text("MANIM COMPOSER", font="Outfit", font_size=48, color=YELLOW)\n        subtitle = Text("Hardware Optimized Video Editor", font_size=28, color=LIGHT_GRAY)\n        title.shift(UP * 0.5)\n        subtitle.next_to(title, DOWN)\n        ring = Circle(radius=3.5, color=BLUE_E, stroke_width=2)\n        self.play(Create(ring), run_time=1.5)\n        self.play(Write(title))\n        self.play(FadeIn(subtitle, shift=UP * 0.5))\n        self.wait(1)\n        self.play(ring.animate.scale(1.2).set_opacity(0), FadeOut(title, shift=LEFT * 2), FadeOut(subtitle, shift=RIGHT * 2))\n`
  },
  {
    title: "Mathematical Plotting",
    description: "Plot functions (Sine & Cosine waves) using axes, grids and labels.",
    category: "Math",
    code: `from manim import *\n\nclass PlotSineCosine(Scene):\n    def construct(self):\n        axes = Axes(x_range=[-3, 10, 1], y_range=[-1.5, 1.5, 0.5], x_length=10, y_length=5, axis_config={"color": BLUE})\n        labels = axes.get_axis_labels(x_label="x", y_label="f(x)")\n        sine_curve = axes.plot(lambda x: np.sin(x), color=GREEN)\n        cosine_curve = axes.plot(lambda x: np.cos(x), color=RED)\n        sine_label = axes.get_graph_label(sine_curve, label="sin(x)", x_val=7.5, direction=UP)\n        cosine_label = axes.get_graph_label(cosine_curve, label="cos(x)", x_val=2.5, direction=DOWN)\n        self.play(Create(axes), Write(labels))\n        self.play(Create(sine_curve), run_time=2)\n        self.play(Write(sine_label))\n        self.wait(0.5)\n        self.play(Create(cosine_curve), run_time=2)\n        self.play(Write(cosine_label))\n        self.wait(1.5)\n`
  },
  {
    title: "3D Coordinate Grid",
    description: "Initialize a ThreeDScene and perform camera rotation around objects.",
    category: "3D",
    code: `from manim import *\n\nclass ThreeDExample(ThreeDScene):\n    def construct(self):\n        axes = ThreeDAxes()\n        cylinder = Cylinder(radius=1.5, height=3, stroke_width=1, fill_color=PURPLE)\n        cylinder.set_opacity(0.6)\n        self.set_camera_orientation(phi=75 * DEGREES, theta=30 * DEGREES)\n        self.play(Create(axes))\n        self.play(Create(cylinder))\n        self.begin_ambient_camera_rotation(rate=0.2)\n        self.wait(3.0)\n        self.stop_ambient_camera_rotation()\n        self.wait(1.0)\n`
  }
];

const LATEX_TEMPLATES = [
  { name: "Euler's Identity", code: "e^{i\\pi} + 1 = 0" },
  { name: "Quadratic Formula", code: "x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}" },
  { name: "Maxwell's Equations", code: "\\nabla \\cdot \\mathbf{E} = \\frac{\\rho}{\\varepsilon_0}" },
  { name: "Schrödinger Equation", code: "i\\hbar\\frac{\\partial}{\\partial t}\\Psi = \\hat{H}\\Psi" },
  { name: "Gaussian Integral", code: "\\int_{-\\infty}^{\\infty} e^{-x^2} dx = \\sqrt{\\pi}" },
  { name: "Matrix", code: "\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}" },
  { name: "Fraction", code: "\\frac{a}{b}" },
  { name: "Summation", code: "\\sum_{i=1}^{n} i = \\frac{n(n+1)}{2}" }
];

interface LaTeXProps {
  math: string;
  block?: boolean;
}

function LaTeX({ math, block = false }: LaTeXProps) {
  const containerRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (containerRef.current) {
      const globalWindow = window as any;
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
  const [files, setFiles] = useState<FileListResponse>({ scripts: [], assets: [], media: [] });
  const [activeFile, setActiveFile] = useState<string>("example.py");
  const [code, setCode] = useState<string>("");
  const [scenes, setScenes] = useState<string[]>([]);
  const [selectedScene, setSelectedScene] = useState<string>("");
  
  const [quality, setQuality] = useState<string>("m");
  const [useOpengl, setUseOpengl] = useState<boolean>(false);
  const [isRendering, setIsRendering] = useState<boolean>(false);
  const [renderPercent, setRenderPercent] = useState<number>(0);
  
  const [logs, setLogs] = useState<LogLine[]>([]);
  const [diagnostics, setDiagnostics] = useState<DiagnosticInfo | null>(null);
  const [wsConnected, setWsConnected] = useState<boolean>(false);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [isInstallingLatex, setIsInstallingLatex] = useState<boolean>(false);
  
  const [videoUrl, setVideoUrl] = useState<string>("");
  const [videoKey, setVideoKey] = useState<number>(0);
  
  const [showNewFileDialog, setShowNewFileDialog] = useState<boolean>(false);
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
  const autoRenderTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const startRenderRef = useRef<(() => void) | null>(null);

  const addLog = useCallback((type: LogLine["type"], msg: string, stream?: string) => {
    setLogs((prev) => [...prev, { type, message: msg, stream }]);
  }, []);

  const fetchDiagnostics = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/diagnostics`);
      if (!res.ok) throw new Error();
      const data = await res.json();
      setDiagnostics(data);
      setBackendError(false);
      
      if (data.profile === "eco") setQuality("l");
      else if (data.profile === "workstation") setQuality("h");
      else setQuality("m");
    } catch {
      setBackendError(true);
    }
  }, []);

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
      if ((data.scenes as string[]).length > 0) {
        setSelectedScene(data.scenes[0]);
      } else {
        setSelectedScene("");
      }
    } catch {
      console.error("Failed to load file contents.");
    }
  }, []);

  const handleSave = useCallback(async (silent = false) => {
    if (!activeFile) return;
    setIsSaving(true);
    try {
      const res = await fetch(`${API_BASE}/api/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: activeFile, code })
      });
      const data = await res.json();
      if (data.success) {
        setScenes(data.scenes as string[]);
        if ((data.scenes as string[]).length > 0 && !(data.scenes as string[]).includes(selectedScene)) {
          setSelectedScene(data.scenes[0]);
        }
        if (!silent) {
          addLog("info", `File "${activeFile}" saved successfully. Found scenes: ${(data.scenes as string[]).join(", ")}`);
        }
        fetchFiles();
      }
    } catch {
      addLog("error", "Error saving file to workspace.");
    } finally {
      setIsSaving(false);
    }
  }, [activeFile, code, selectedScene, fetchFiles, addLog]);

  const handleCreateFile = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newFileName.trim()) return;
    let name = newFileName.trim();
    if (!name.endsWith(".py")) name += ".py";

    const defaultCode = `from manim import *\n\nclass NewScene(Scene):\n    def construct(self):\n        text = Text("New Project", font_size=36)\n        self.play(Write(text))\n        self.wait(1)\n        self.play(FadeOut(text))\n`;

    try {
      const res = await fetch(`${API_BASE}/api/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: name, code: defaultCode })
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
  }, [newFileName, fetchFiles, loadFileContent, addLog]);

  const handleRename = useCallback(async (oldName: string, newName: string) => {
    setRenamingFile(null);
    if (!newName.trim() || newName.trim() === oldName) return;
    let name = newName.trim();
    if (!name.endsWith(".py")) name += ".py";
    
    try {
      const res = await fetch(`${API_BASE}/api/rename`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ old_name: oldName, new_name: name })
      });
      
      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "Rename failed.");
      }
      
      const data = await res.json();
      if (data.success) {
        addLog("info", `Renamed file: ${oldName} -> ${name}`);
        if (activeFile === oldName) {
          setActiveFile(name);
        }
        fetchFiles();
      }
    } catch (error) {
      const msg = error instanceof Error ? error.message : "Error renaming file.";
      addLog("error", msg);
    }
  }, [activeFile, fetchFiles, addLog]);

  const handleAssetUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    const file = e.target.files[0];
    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API_BASE}/api/upload-asset`, {
        method: "POST",
        body: formData
      });
      const data = await res.json();
      if (data.success) {
        addLog("info", `Asset uploaded: ${data.filename}`);
        fetchFiles();
      }
    } catch {
      addLog("error", "Failed to upload asset.");
    }
  }, [fetchFiles, addLog]);

  const sendRenderRequest = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({
          type: "start",
          filename: activeFile,
          scene: selectedScene,
          quality: quality,
          use_opengl: useOpengl
        })
      );
    } else {
      addLog("error", "WebSocket render request failed: server connection closed.");
      setIsRendering(false);
    }
  }, [activeFile, selectedScene, quality, useOpengl, addLog]);

  const connectWebSocket = useCallback((onConnectCallback?: () => void) => {
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
            setVideoKey(prev => prev + 1);
            setSavedPath(`workspace/${data.rel_path}`);
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
  }, [fetchFiles, addLog]);

  const startRender = useCallback(async () => {
    if (isRendering) return;
    await handleSave(true);

    if (!selectedScene) {
      addLog("error", "Please select or write a valid Scene class in the editor before rendering.");
      return;
    }

    setIsRendering(true);
    setRenderPercent(0);
    setLogs([]);
    addLog("info", `Initiating render for Scene "${selectedScene}" from file "${activeFile}"...`);

    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      connectWebSocket(() => {
        sendRenderRequest();
      });
    } else {
      sendRenderRequest();
    }
  }, [isRendering, activeFile, selectedScene, handleSave, connectWebSocket, sendRenderRequest, addLog]);

  const cancelRender = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "cancel" }));
      addLog("info", "Cancelling render operation...");
    }
  }, [addLog]);

  const handleInstallLatex = useCallback(async () => {
    if (isInstallingLatex) return;
    setIsInstallingLatex(true);
    addLog("info", "Starting MiKTeX LaTeX installation in the background via winget...");
    try {
      const res = await fetch(`${API_BASE}/api/install-latex`, { method: "POST" });
      const data = await res.json();
      if (data.success) {
        addLog("success", data.message);
        addLog("info", "You will be prompted for UAC permissions. After approval, the installation executes silently.");
      } else {
        addLog("error", "LaTeX setup call returned failure state.");
        setIsInstallingLatex(false);
      }
    } catch {
      addLog("error", "Failed to contact backend to install LaTeX.");
      setIsInstallingLatex(false);
    }
  }, [isInstallingLatex, addLog]);

  const handleInsertSnippet = useCallback((snippetCode: string) => {
    if (editorRef.current) {
      const editor = editorRef.current as MonacoEditorInstance;
      const selection = editor.getSelection();
      
      const globalWindow = window as unknown as GlobalWindow;
      if (globalWindow.monaco) {
        const range = new globalWindow.monaco.Range(
          selection.startLineNumber,
          selection.startColumn,
          selection.endLineNumber,
          selection.endColumn
        );
        const id = { major: 1, minor: 1 };
        const op = { identifier: id, range: range, text: snippetCode, forceMoveMarkers: true };
        editor.executeEdits("my-source", [op]);
        addLog("info", "Inserted template snippet into active buffer.");
      }
    } else {
      setCode(snippetCode);
      addLog("info", "Loaded template script.");
    }
  }, [addLog]);

  const handleInsertMathTex = useCallback((latexCode: string) => {
    const snippet = `MathTex(r"${latexCode}")`;
    handleInsertSnippet(snippet);
  }, [handleInsertSnippet]);

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
        const exists = files.scripts.some(f => f.name === activeFile);
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
      <header className="glass-panel h-14 flex items-center justify-between px-6 bg-zinc-950 border border-zinc-800 rounded-lg" style={{ gridColumn: "1 / 4", gridRow: "1" }}>
        <div className="flex items-center gap-3">
          <Sparkles className="text-slate-400 h-5 w-5" />
          <h1 className="font-extrabold text-lg tracking-tight text-white font-outfit">
            MANIM COMPOSER
          </h1>
          <span className="text-[10px] text-slate-500 font-mono">v0.18.1 CE</span>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-xs">
            <span className={`h-2 w-2 rounded-full ${wsConnected ? "bg-white" : "bg-zinc-700"}`} />
            <span className="text-slate-200">
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

          {diagnostics && (
            <div className="bg-zinc-900/60 border border-zinc-800 px-3 py-1 rounded-full text-xs flex items-center gap-2">
              <Cpu size={12} className="text-slate-400" />
              <span className="text-slate-400">Profile:</span>
              <strong className="text-white font-mono tracking-wider uppercase font-semibold">{diagnostics.profile}</strong>
            </div>
          )}
        </div>
      </header>

      {/* 2. Left Panel: File Browser / Snippets / Assets / Diagnostics */}
      <aside className="glass-panel bg-zinc-950 border border-zinc-800 rounded-lg overflow-hidden flex flex-col" style={{ gridColumn: "1", gridRow: "2 / 4" }}>
        <Tabs defaultValue="files" className="flex-1 flex flex-col overflow-hidden">
          <TabsList className="grid grid-cols-5 bg-zinc-900/40 border-b border-zinc-800 p-0 rounded-none h-11">
            <TabsTrigger value="files" className="text-[9px] tracking-wider font-semibold rounded-none py-3 text-slate-400 data-[state=active]:text-white data-[state=active]:bg-zinc-900">FILES</TabsTrigger>
            <TabsTrigger value="snippets" className="text-[9px] tracking-wider font-semibold rounded-none py-3 text-slate-400 data-[state=active]:text-white data-[state=active]:bg-zinc-900">SNIPPETS</TabsTrigger>
            <TabsTrigger value="latex" className="text-[9px] tracking-wider font-semibold rounded-none py-3 text-slate-400 data-[state=active]:text-white data-[state=active]:bg-zinc-900">LATEX</TabsTrigger>
            <TabsTrigger value="assets" className="text-[9px] tracking-wider font-semibold rounded-none py-3 text-slate-400 data-[state=active]:text-white data-[state=active]:bg-zinc-900">ASSETS</TabsTrigger>
            <TabsTrigger value="diags" className="text-[9px] tracking-wider font-semibold rounded-none py-3 text-slate-400 data-[state=active]:text-white data-[state=active]:bg-zinc-900">DIAGS</TabsTrigger>
          </TabsList>

          <div className="flex-1 overflow-y-auto p-3">
            <TabsContent value="files" className="mt-0 space-y-4 outline-none">
              <div>
                <div className="flex justify-between items-center mb-2">
                  <h3 className="text-xs font-semibold text-slate-400 tracking-wider">Python Scripts</h3>
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
                        <FileCode size={14} className={activeFile === script.name ? "text-white" : "text-slate-650"} />
                        {renamingFile === script.name ? (
                          <input
                            type="text"
                            value={renameValue}
                            onChange={(e) => setRenameValue(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") handleRename(script.name, renameValue);
                              else if (e.key === "Escape") setRenamingFile(null);
                            }}
                            onBlur={() => handleRename(script.name, renameValue)}
                            onClick={(e) => e.stopPropagation()}
                            autoFocus
                            className="bg-black border border-zinc-700 text-xs text-white px-1 py-0.5 rounded focus:outline-none w-full font-sans"
                          />
                        ) : (
                          <span className="text-xs truncate font-medium">{script.name}</span>
                        )}
                      </div>
                      {renamingFile !== script.name && (
                        <span className="text-[10px] text-slate-650 font-mono flex-shrink-0">{Math.round(script.size / 102) / 10} KB</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <h3 className="text-xs font-semibold text-slate-400 tracking-wider mb-2">Rendered Videos</h3>
                <div className="space-y-1">
                  {files.media.length === 0 ? (
                    <span className="text-xs text-slate-600 italic block pl-1">No videos rendered yet.</span>
                  ) : (
                    files.media.map((vid) => (
                      <div
                        key={vid.url}
                        onClick={() => {
                          if (vid.url) {
                            setVideoUrl(`${API_BASE}${vid.url}?t=${Date.now()}`);
                            setVideoKey(prev => prev + 1);
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
                          <a href={`${API_BASE}${vid.url}`} download className="text-slate-500 hover:text-slate-200" onClick={(e) => e.stopPropagation()}>
                            <Download size={12} />
                          </a>
                        )}
                      </div>
                    ))
                  )}
                </div>
              </div>
            </TabsContent>

            <TabsContent value="snippets" className="mt-0 space-y-2 outline-none">
              <span className="text-[10px] text-slate-500 block mb-2">Click snippet to load in editor buffer.</span>
              {SNIPPETS.map((snippet) => (
                <div
                  key={snippet.title}
                  onClick={() => handleInsertSnippet(snippet.code)}
                  className="p-3 rounded-lg bg-zinc-950 border border-zinc-900 hover:border-zinc-700 hover:bg-zinc-900/30 cursor-pointer transition-all duration-200"
                >
                  <div className="flex justify-between items-center mb-1">
                    <h4 className="text-xs font-semibold text-slate-200">{snippet.title}</h4>
                    <span className="text-[9px] bg-zinc-900 border border-zinc-800 text-slate-300 px-1.5 py-0.5 rounded font-semibold">{snippet.category}</span>
                  </div>
                  <p className="text-[10px] text-slate-400">{snippet.description}</p>
                </div>
              ))}
            </TabsContent>

            <TabsContent value="latex" className="mt-0 space-y-4 outline-none flex flex-col h-[calc(100vh-180px)]">
              <div className="space-y-3 flex-shrink-0">
                <div className="flex justify-between items-center">
                  <h3 className="text-xs font-semibold text-slate-400 tracking-wider">LaTeX Sandbox</h3>
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
                <h4 className="text-[10px] font-semibold text-slate-500 tracking-wider mb-2">Equation Templates</h4>
                <div className="grid grid-cols-1 gap-1">
                  {LATEX_TEMPLATES.map((tmpl) => (
                    <div
                      key={tmpl.name}
                      onClick={() => setLatexInput(tmpl.code)}
                      className="p-1.5 rounded border border-zinc-900 hover:border-zinc-800 bg-zinc-950 hover:bg-zinc-900/30 cursor-pointer transition-all flex justify-between items-center"
                    >
                      <div className="text-[10px] text-slate-350 truncate pr-1">
                        <span className="font-semibold block text-[9px] text-slate-400">{tmpl.name}</span>
                        <code className="text-slate-500 text-[9px] font-mono">{tmpl.code}</code>
                      </div>
                      <span className="text-[9px] text-slate-500 bg-zinc-900 px-1 border border-zinc-850 rounded flex-shrink-0">Use</span>
                    </div>
                  ))}
                </div>
              </div>
            </TabsContent>

            <TabsContent value="assets" className="mt-0 space-y-3 outline-none">
              <label className="border border-dashed border-zinc-800 bg-zinc-950/40 rounded-lg p-5 text-center flex flex-col items-center gap-2 cursor-pointer hover:border-zinc-700 hover:bg-zinc-900/20 transition-all">
                <Upload size={20} className="text-slate-400" />
                <span className="text-xs font-medium">Upload Asset</span>
                <span className="text-[10px] text-slate-500">SVG, PNG, MP3, WAV</span>
                <input type="file" onChange={handleAssetUpload} className="hidden" />
              </label>

              <div>
                <h3 className="text-xs font-semibold text-slate-400 tracking-wider mb-2">Library Assets</h3>
                <div className="space-y-1">
                  {files.assets.length === 0 ? (
                    <span className="text-xs text-slate-600 italic block pl-1">No assets uploaded yet.</span>
                  ) : (
                    files.assets.map((asset) => (
                      <div
                        key={asset.name}
                        className="p-2 rounded-lg bg-zinc-950 border border-zinc-900 flex items-center justify-between text-xs text-slate-400"
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <Layers size={12} className="text-slate-500" />
                          <span className="truncate">{asset.name}</span>
                        </div>
                        <span className="text-[10px] text-slate-500 font-mono">{Math.round(asset.size / 1024 * 10) / 10} KB</span>
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
                    <h4 className="font-semibold text-slate-400 mb-1">PC Description Profile</h4>
                    <p className="text-slate-300 text-[11px] leading-relaxed">{diagnostics.description}</p>
                  </div>

                  <hr className="border-zinc-850" />

                  <div>
                    <h4 className="font-semibold text-slate-400 mb-2">Hardware Specs</h4>
                    <div className="space-y-1.5 text-[11px]">
                      <div className="flex justify-between"><span className="text-slate-500">CPU Name:</span><span className="text-slate-250 font-medium text-right max-w-[160px] truncate">{diagnostics.hardware.cpu.model}</span></div>
                      <div className="flex justify-between"><span className="text-slate-500">Logical Threads:</span><span className="text-slate-250 font-mono">{diagnostics.hardware.cpu.logical_threads} Threads</span></div>
                      <div className="flex justify-between"><span className="text-slate-500">RAM capacity:</span><span className="text-slate-250 font-mono">{diagnostics.hardware.ram_gb} GB</span></div>
                      <div className="flex justify-between"><span className="text-slate-500">Graphics Device:</span><span className="text-slate-250 text-right max-w-[160px] truncate">{diagnostics.hardware.gpu.devices[0]?.name || "N/A"}</span></div>
                    </div>
                  </div>

                  <hr className="border-zinc-850" />

                  <div>
                    <h4 className="font-semibold text-slate-400 mb-2">Software Environment</h4>
                    <div className="space-y-1.5 text-[11px]">
                      <div className="flex justify-between items-center"><span>Manim CE CLI:</span><span className={diagnostics.dependencies.manim !== "Not Found" ? "text-slate-200 font-semibold" : "text-zinc-650"}>{diagnostics.dependencies.manim !== "Not Found" ? "Detected" : "Not Found"}</span></div>
                      <div className="flex justify-between items-center"><span>FFmpeg Binaries:</span><span className={diagnostics.dependencies.ffmpeg !== "Not Found" ? "text-slate-200 font-semibold" : "text-zinc-650"}>{diagnostics.dependencies.ffmpeg !== "Not Found" ? "Detected" : "Not Found"}</span></div>
                      <div className="flex justify-between items-center"><span>LaTeX Compiler:</span><span className={diagnostics.dependencies.latex !== "Not Found" ? "text-slate-200" : "text-zinc-650"}>{diagnostics.dependencies.latex !== "Not Found" ? "Installed" : "Missing"}</span></div>
                      <div className="flex justify-between items-center"><span>dvisvgm Converter:</span><span className={diagnostics.dependencies.dvisvgm !== "Not Found" ? "text-slate-200" : "text-zinc-650"}>{diagnostics.dependencies.dvisvgm !== "Not Found" ? "Installed" : "Missing"}</span></div>
                    </div>
                  </div>
                </div>
              ) : (
                <span className="text-xs text-slate-600 block">Querying diagnostics profile...</span>
              )}
            </TabsContent>
          </div>
        </Tabs>
      </aside>

      {/* 3. Center Panel: Code Editor */}
      <main className="glass-panel bg-zinc-950 border border-zinc-800 rounded-lg overflow-hidden flex flex-col" style={{ gridColumn: "2", gridRow: "2" }}>
        {diagnostics && !diagnostics.dependencies.latex_available && (
          <div className="bg-white text-black px-4 py-2.5 flex items-center justify-between text-xs border-b border-zinc-800 flex-shrink-0 select-text">
            <div className="flex items-center gap-2 font-semibold">
              <AlertTriangle size={14} className="stroke-[2.5]" />
              <span>LaTeX compiler is required for math symbols rendering. Live preview fallback is standard Text.</span>
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
            <span className="text-xs font-semibold text-slate-200">{activeFile || "No Active File"}</span>
            
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

            <label className="flex items-center gap-1.5 text-xs text-slate-400 cursor-pointer ml-2 flex-shrink-0">
              <input
                type="checkbox"
                checked={autoRender}
                onChange={(e) => setAutoRender(e.target.checked)}
                className="rounded border-zinc-800 bg-zinc-900 focus:ring-0 text-white w-3 h-3"
              />
              <span className={autoRender ? "text-white font-medium" : "text-slate-400"}>Auto-Render</span>
            </label>
          </div>

          <div className="flex items-center gap-3 flex-wrap">
            {/* Scene Selector */}
            <div className="flex items-center gap-2 text-xs">
              <span className="text-slate-500">Scene:</span>
              <Select value={selectedScene} onValueChange={setSelectedScene} disabled={scenes.length === 0}>
                <SelectTrigger className="w-[150px] h-7 bg-zinc-900 border-zinc-800 text-xs text-slate-200">
                  <SelectValue placeholder={scenes.length === 0 ? "No scenes" : "Select Scene"} />
                </SelectTrigger>
                <SelectContent className="bg-zinc-900 border-zinc-800 text-xs">
                  {scenes.map((scene) => (
                    <SelectItem key={scene} value={scene} className="text-xs">{scene}</SelectItem>
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
                  <SelectItem value="l" className="text-xs">Low (480p 15fps)</SelectItem>
                  <SelectItem value="m" className="text-xs">Medium (720p 30fps)</SelectItem>
                  <SelectItem value="h" className="text-xs">High (1080p 60fps)</SelectItem>
                  <SelectItem value="k" className="text-xs">4K (2160p 60fps)</SelectItem>
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
                  className="rounded border-zinc-850 bg-zinc-900"
                />
                <span className={useOpengl ? "text-white" : "text-slate-500"}>OpenGL HW</span>
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
              padding: { top: 8 }
            }}
          />
        </div>
      </main>

      {/* 4. Right Panel: Video Previewer */}
      <section className="glass-panel bg-zinc-950 border border-zinc-800 rounded-lg overflow-hidden flex flex-col" style={{ gridColumn: "3", gridRow: "2" }}>
        <div className="flex items-center gap-2 px-4 py-3 bg-zinc-950 border-b border-zinc-800">
          <Video size={14} className="text-slate-400" />
          <h3 className="text-xs font-semibold text-slate-200">Live Video Preview</h3>
        </div>

        <div className="flex-1 bg-black flex items-center justify-center relative border-t border-zinc-900">
          {videoUrl ? (
            <video
              key={videoKey}
              controls
              className="w-full h-full max-h-full object-contain"
              autoPlay
              muted
              playsInline
            >
              <source src={videoUrl} type="video/mp4" />
              Browser tag error.
            </video>
          ) : (
            <div className="text-center p-5 text-slate-500 flex flex-col items-center gap-2">
              <Video size={32} className="opacity-30" />
              <span className="text-xs">No video loaded. Complete a render to preview.</span>
            </div>
          )}
        </div>
        {savedPath && (
          <div className="bg-zinc-950 border-t border-zinc-900 px-4 py-2 text-[10px] text-slate-400 font-mono truncate select-text flex-shrink-0">
            <span className="text-slate-500">Path: </span>
            <span className="text-white">{savedPath}</span>
          </div>
        )}
      </section>

      {/* 5. Bottom Panel: Console logs */}
      <section className="glass-panel bg-zinc-950 border border-zinc-800 rounded-lg overflow-hidden flex flex-col" style={{ gridColumn: "2 / 4", gridRow: "3" }}>
        <div className="flex justify-between items-center px-4 py-2.5 bg-zinc-950 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <Terminal size={14} className="text-slate-400" />
            <h3 className="text-xs font-semibold text-slate-200">Render Output Console</h3>
          </div>
          {isRendering && (
            <div className="flex items-center gap-3">
              <Progress value={renderPercent} className="w-[120px] h-1.5" />
              <span className="text-xs text-white font-bold font-mono">{renderPercent}%</span>
            </div>
          )}
          <button
            onClick={() => setLogs([])}
            className="text-[10px] text-slate-500 hover:text-slate-300"
          >
            Clear Console
          </button>
        </div>

        <div className="flex-1 bg-black/90 p-3 font-mono text-[11px] overflow-y-auto space-y-1 select-text">
          {logs.length === 0 ? (
            <div className="text-slate-655 italic">
              Console idle. Start rendering a scene to view render logs...
            </div>
          ) : (
            logs.map((log, idx) => {
              let color = "text-slate-400";
              if (log.type === "error") color = "text-white underline decoration-dotted font-semibold bg-zinc-950 px-1 border-l-2 border-white";
              else if (log.type === "info") color = "text-slate-400";
              else if (log.type === "success") color = "text-white font-semibold";
              else if (log.type === "warning") color = "text-slate-200 italic font-medium";
              else if (log.stream === "stderr") color = "text-slate-300 italic";

              return (
                <div key={idx} className={`${color} wrap-break-word`}>
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
        </div>
      </section>

      {/* 6. Footer / Status Telemetry */}
      <footer className="glass-panel h-10 flex items-center justify-between px-6 bg-zinc-950 border border-zinc-900 rounded-lg text-[11px] text-slate-400" style={{ gridColumn: "1 / 4", gridRow: "4" }}>
        <div className="flex items-center gap-5">
          <span>Workspace: <strong className="text-slate-200">workspace/</strong></span>
          {diagnostics && (
            <>
              <div className="flex items-center gap-1">
                <Cpu size={12} className="text-slate-500" />
                <span>Threads Allocation: {diagnostics.recommended_threads} worker threads</span>
              </div>
              <div className="flex items-center gap-1">
                <HardDrive size={12} className="text-slate-500" />
                <span>Resolution Default: {diagnostics.default_resolution} ({diagnostics.default_fps}fps)</span>
              </div>
            </>
          )}
        </div>

        {diagnostics && !diagnostics.dependencies.latex_available && (
          <div className="flex items-center gap-2.5 text-white bg-zinc-900 px-2.5 py-1 rounded border border-zinc-800">
            <AlertTriangle size={12} className="text-white" />
            <span>LaTeX not detected. Formulas rendered with standard Text.</span>
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
            <DialogTitle className="text-sm font-semibold tracking-tight text-slate-200 font-outfit">Create New Python Script</DialogTitle>
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
                className="w-full bg-black border border-zinc-800 rounded-md px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-zinc-650"
              />
            </div>
            <DialogFooter className="flex justify-end gap-2 pt-2">
              <DialogClose asChild>
                <Button type="button" variant="outline" size="sm" className="bg-transparent border-zinc-800 h-8 text-xs">
                  Cancel
                </Button>
              </DialogClose>
              <Button type="submit" size="sm" className="bg-white hover:bg-slate-200 text-black border border-white font-bold h-8 text-xs">
                Create File
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
