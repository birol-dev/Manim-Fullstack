import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Group, Panel, Separator, useDefaultLayout, usePanelRef } from "react-resizable-panels";
import { toast, Toaster } from "sonner";

import { BottomPanel, type BottomTab } from "@/components/console/BottomPanel";
import { CompareDialog } from "@/components/dialogs/CompareDialog";
import { ConfirmDialog, type ConfirmRequest } from "@/components/dialogs/ConfirmDialog";
import { NewFileDialog, type NewFileRequest } from "@/components/dialogs/NewFileDialog";
import { SetupDialog } from "@/components/dialogs/SetupDialog";
import { EditorPane } from "@/components/editor/EditorPane";
import type { CodeEditorHandle, InsertMode } from "@/components/editor/types";
import { ActivityBar, type SidebarView } from "@/components/layout/ActivityBar";
import { StatusBar } from "@/components/layout/StatusBar";
import { TopBar } from "@/components/layout/TopBar";
import { PreviewPane } from "@/components/preview/PreviewPane";
import { AssetsPanel } from "@/components/sidebar/AssetsPanel";
import { FilesPanel } from "@/components/sidebar/FilesPanel";
import { SettingsPanel, type Settings } from "@/components/sidebar/SettingsPanel";
import { ShapeBuilderPanel } from "@/components/sidebar/ShapeBuilderPanel";
import { SystemPanel } from "@/components/sidebar/SystemPanel";
import { TemplatesPanel } from "@/components/sidebar/TemplatesPanel";
import { TooltipProvider } from "@/components/ui/tooltip";
import { isInstalled, useDiagnostics } from "@/hooks/useDiagnostics";
import { useLogs } from "@/hooks/useLogs";
import { useMinimumStopping } from "@/hooks/useMinimumStopping";
import { usePersistentState } from "@/hooks/usePersistentState";
import { useRenderSession, type ActiveRender, type RenderOutcome, type RenderOutput } from "@/hooks/useRenderSession";
import { useViewportHeight } from "@/hooks/useViewportHeight";
import { SaveConflictError, useWorkspace } from "@/hooks/useWorkspace";
import { apiUrl, errorMessage } from "@/lib/api";
import { MOD_KEY, QUALITY_FOR_PROFILE } from "@/lib/constants";
import { classNameFromFile } from "@/lib/format";
import { workPanelSizes } from "@/lib/layout";
import { findErrorLocation } from "@/lib/logs";
import { latestRenderFor, previewBelongsTo, previewFromMedia } from "@/lib/preview";
import { overallPercent, risingPercent } from "@/lib/progress";
import { expandedStepCount, stepIndexForAnimation } from "@/lib/timeline";
import { STORAGE_KEYS } from "@/lib/storage";
import { newSceneCode, type SceneTemplate } from "@/lib/templates";
import type { AssetFile, MediaFile, ParseResult, PreviewItem, Quality, StorageMode, WorkspaceFiles } from "@/lib/types";

// KaTeX is only needed by this panel.
const LatexPanel = lazy(() => import("@/components/sidebar/LatexPanel").then((module) => ({ default: module.LatexPanel })));

const AUTO_RENDER_DELAY_MS = 1500;
const SETUP_SHOWN_KEY = "mc.setupShown";

function uniqueName(base: string, existing: string[]): string {
  const taken = new Set(existing.map((name) => name.toLowerCase()));
  if (!taken.has(base.toLowerCase())) return base;
  const stem = base.replace(/\.py$/i, "");
  for (let index = 2; ; index += 1) {
    const candidate = `${stem}_${index}.py`;
    if (!taken.has(candidate.toLowerCase())) return candidate;
  }
}

function triggerDownload(url: string, filename: string) {
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

function ResizeHandle({ direction }: { direction: "horizontal" | "vertical" }) {
  return (
    <Separator
      className={
        direction === "horizontal"
          ? "relative w-px bg-line outline-none transition-colors data-[separator=active]:bg-accent data-[separator=focus]:bg-accent data-[separator=hover]:bg-accent/60"
          : "relative h-px bg-line outline-none transition-colors data-[separator=active]:bg-accent data-[separator=focus]:bg-accent data-[separator=hover]:bg-accent/60"
      }
    />
  );
}

export default function App() {
  // ---- Preferences -------------------------------------------------------
  const [storageMode, setStorageMode] = usePersistentState<StorageMode>(STORAGE_KEYS.storageMode, "disk");
  const [autoSave, setAutoSave] = usePersistentState(STORAGE_KEYS.autoSave, true);
  const [downloadOnly, setDownloadOnly] = usePersistentState(STORAGE_KEYS.downloadOnly, false);
  const [useOpenGL, setUseOpenGL] = usePersistentState(STORAGE_KEYS.useOpenGL, false);
  const [autoRender, setAutoRender] = usePersistentState(STORAGE_KEYS.autoRender, false);
  const [loopPreview, setLoopPreview] = usePersistentState(STORAGE_KEYS.loopPreview, true);
  const [editorFontSize, setEditorFontSize] = usePersistentState(STORAGE_KEYS.editorFontSize, 13);
  const [storedQuality, setQuality] = usePersistentState<Quality | null>(STORAGE_KEYS.quality, null);
  const [sidebarView, setSidebarView] = usePersistentState<SidebarView>(STORAGE_KEYS.sidebarView, "files");

  // ---- Data --------------------------------------------------------------
  const diagnostics = useDiagnostics();
  const online = diagnostics.status === "online";
  const workspace = useWorkspace({ mode: storageMode, online });
  const { logs, append: log, clear: clearLogs, snapshot: logSnapshot } = useLogs();
  const quality: Quality = storedQuality ?? QUALITY_FOR_PROFILE[diagnostics.data?.profile ?? ""] ?? "m";
  const latexAvailable = diagnostics.data?.dependencies.latex_available ?? true;
  const manimMissing = diagnostics.data !== null && !isInstalled(diagnostics.data, "manim");
  const openGLSupported = diagnostics.data?.opengl_supported ?? false;

  // ---- UI state ----------------------------------------------------------
  const editorRef = useRef<CodeEditorHandle>(null);
  const revealLine = useCallback((line: number) => {
    // After the toast button's click, so closing the toast doesn't steal focus.
    window.setTimeout(() => {
      editorRef.current?.revealLine(line);
      editorRef.current?.focus();
    }, 0);
  }, []);
  const [preview, setPreview] = useState<PreviewItem | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const [lastOutcome, setLastOutcome] = useState<RenderOutcome | null>(null);
  const [cursor, setCursor] = useState<{ line: number; column: number } | null>(null);
  // The script whose render output the console is showing.
  const [logsFile, setLogsFile] = useState<string | null>(null);
  const [bottomTab, setBottomTab] = useState<BottomTab>("console");
  const [bottomCollapsed, setBottomCollapsed] = useState(false);
  const [bottomPx, setBottomPx] = useState<number | null>(null);
  const workSizes = workPanelSizes(useViewportHeight());
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [newFile, setNewFile] = useState<(NewFileRequest & { code?: string }) | null>(null);
  const [confirm, setConfirm] = useState<ConfirmRequest | null>(null);
  const [setupOpen, setSetupOpen] = useState(false);
  const [compareOpen, setCompareOpen] = useState(false);

  const sidebarPanelRef = usePanelRef();
  const bottomPanelRef = usePanelRef();
  const mainLayout = useDefaultLayout({ id: "mc-layout-main", storage: localStorage });
  const workLayout = useDefaultLayout({ id: "mc-layout-work", storage: localStorage });
  const topLayout = useDefaultLayout({ id: "mc-layout-top", storage: localStorage });

  const previewRef = useRef<PreviewItem | null>(null);
  const showPreview = useCallback((item: PreviewItem | null) => {
    if (objectUrlRef.current && objectUrlRef.current !== item?.url) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
    if (item?.url.startsWith("blob:")) objectUrlRef.current = item.url;
    previewRef.current = item;
    setPreview(item);
  }, []);

  const expandBottom = useCallback(() => {
    if (bottomPanelRef.current?.isCollapsed()) bottomPanelRef.current.expand();
  }, [bottomPanelRef]);

  // ---- Render session ----------------------------------------------------
  const { refreshFiles } = workspace;
  const activeFileRef = useRef(workspace.activeFile);
  const filesRef = useRef<WorkspaceFiles>(workspace.files);
  const pendingAutoRender = useRef(false);
  const startRenderRef = useRef<() => Promise<void>>(async () => {});

  const handleOutput = useCallback(
    async (output: RenderOutput, render: ActiveRender) => {
      const { filename: file, scene } = render.request;
      const title = scene;
      // The preview follows the open file; a render of a file you switched away from only lands in Renders.
      const stillOpen = () => file === activeFileRef.current;
      if (output.temporary) {
        try {
          const response = await fetch(apiUrl(output.url));
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          const url = URL.createObjectURL(await response.blob());
          if (stillOpen()) {
            showPreview({ url, kind: output.kind, title, location: "Downloaded · not kept on the server", downloadName: output.filename, file, scene });
          }
          triggerDownload(url, output.filename);
          if (!stillOpen()) URL.revokeObjectURL(url);
        } catch {
          toast.error("The render finished, but downloading it failed.");
        }
        return;
      }
      if (stillOpen()) {
        showPreview({
          url: `${apiUrl(output.url)}?v=${Date.now()}`,
          kind: output.kind,
          title,
          location: `workspace/${output.relPath}`,
          mediaPath: output.relPath.replace(/^media\//, ""),
          downloadName: output.filename,
          file,
          scene,
        });
      } else {
        toast.success(`${scene} rendered`, { description: `${file} isn't open, so it's in the Renders list.` });
      }
      void refreshFiles();
    },
    [refreshFiles, showPreview],
  );

  const handleFinished = useCallback(
    (outcome: RenderOutcome) => {
      setLastOutcome(outcome);
      const { filename, scene } = outcome.request;
      const failed = !outcome.success && outcome.status !== "cancelled";
      if (!(outcome.success && outcome.output) && filename === activeFileRef.current) {
        // No new clip. Keep (and flag) this scene's current clip, or fall back to its
        // last good render instead of whatever unrelated clip was showing before.
        const failedOrEmpty = failed || outcome.success;
        const current = previewRef.current;
        if (previewBelongsTo(current, filename, scene)) {
          if (failedOrEmpty && current && !current.stale) showPreview({ ...current, stale: true });
        } else {
          const last = latestRenderFor(filesRef.current.media, filename, scene);
          showPreview(last ? { ...previewFromMedia(last), stale: failedOrEmpty } : null);
        }
      }
      if (failed) {
        setBottomTab("console");
        expandBottom();
        const location = findErrorLocation(
          logSnapshot().map((entry) => entry.text),
          [outcome.request.filename],
        );
        if (location && outcome.request.filename === activeFileRef.current) {
          editorRef.current?.setErrorMarker(location.line, location.message);
        }
        toast.error(`${outcome.request.scene} didn't render`, {
          id: "render-failed",
          description: location ? `${location.message} (line ${location.line})` : "See the console for details.",
          action: location ? { label: "Go to line", onClick: () => revealLine(location.line) } : undefined,
        });
      } else if (outcome.success && !outcome.output) {
        toast.warning("Manim finished but produced no output file.", { id: "render-failed" });
      } else if (outcome.success) {
        toast.dismiss("render-failed");
      }
      if (pendingAutoRender.current) {
        pendingAutoRender.current = false;
        setTimeout(() => void startRenderRef.current(), 0);
      }
    },
    [expandBottom, logSnapshot, revealLine, showPreview],
  );

  const session = useRenderSession({ log, onOutput: handleOutput, onFinished: handleFinished });
  // What the toolbar and preview overlay show: a quick cancel keeps "Stopping…" up for a moment.
  const shownRender = useMinimumStopping(session.active, session.stopping);

  // The socket is the first to notice a server going away or coming back.
  const { refresh: refreshDiagnostics } = diagnostics;
  useEffect(() => {
    if (session.connection !== "connecting") void refreshDiagnostics();
  }, [session.connection, refreshDiagnostics]);
  const sessionActiveRef = useRef(session.active);
  const lastRenderedCode = useRef<string | null>(null);
  const startingRef = useRef(false);

  const saveRef = useRef<(options?: { force?: boolean }) => Promise<void>>(async () => {});
  /** Toast a failed save, or ask what to do when the file changed or vanished on disk. */
  const reportSaveError = useCallback(
    (err: unknown, fallback: string) => {
      if (!(err instanceof SaveConflictError)) {
        toast.error(errorMessage(err, fallback), { id: "save-error" });
        return;
      }
      const name = err.filename;
      setConfirm(
        err.reason === "missing"
          ? {
              title: `${name} no longer exists`,
              description: "It was renamed or deleted in another tab or program. Your text is still in the editor.",
              confirmLabel: "Recreate file",
              onConfirm: () => saveRef.current({ force: true }),
            }
          : {
              title: `${name} changed in another tab`,
              description:
                "It was saved somewhere else after you opened it. Reload it to get that version (your unsaved edits here are dropped), or overwrite it with yours.",
              confirmLabel: "Overwrite",
              tone: "danger",
              secondaryLabel: "Reload theirs",
              onConfirm: () => saveRef.current({ force: true }),
              onSecondary: () => workspace.reloadFromDisk(),
            },
      );
    },
    [workspace],
  );

  const startRender = useCallback(async () => {
    const filename = workspace.activeFile;
    // Ctrl+Enter can arrive twice (editor and window) while the first call is still saving.
    if (sessionActiveRef.current || startingRef.current || !filename) return;
    startingRef.current = true;
    try {
      editorRef.current?.clearMarkers();
      let scenes = workspace.scenes;
      let parsed: ParseResult | null;
      let code: string | undefined;
      const buffer = workspace.code;
      try {
        if (storageMode === "disk" && autoSave) {
          // Check first: a render refused for a syntax error must not write the broken buffer to disk.
          parsed = await workspace.parseNow();
          if (workspace.isDirty && !parsed?.syntaxError) parsed = await workspace.save();
        } else {
          parsed = await workspace.parseNow();
          // Send the buffer unless it is identical to the file on disk.
          if (storageMode === "browser" || workspace.isDirty) code = buffer;
        }
      } catch (err) {
        reportSaveError(err, "Couldn't save before rendering.");
        return;
      }
      scenes = parsed?.scenes ?? scenes;
      if (parsed?.syntaxError) {
        const syntax = parsed.syntaxError;
        toast.error("This file has a syntax error", {
          id: "syntax-error",
          description: `Line ${syntax.line}: ${syntax.message}`,
          action: { label: "Go to line", onClick: () => revealLine(syntax.line) },
        });
        return;
      }

      const typed = workspace.selectedSceneTyped;
      const scene = typed || scenes.includes(workspace.selectedScene) ? workspace.selectedScene : scenes[0];
      if (!scene) {
        toast.error("No scene to render", {
          id: "no-scene",
          description: "Add a class that inherits from Scene, e.g. class Intro(Scene), or pick “Other scene…” and type its name.",
        });
        return;
      }
      if (scene !== workspace.selectedScene) workspace.setSelectedScene(scene);

      clearLogs();
      setLogsFile(filename);
      lastRenderedCode.current = buffer;
      session.start({ filename, scene, quality, useOpenGL: useOpenGL && openGLSupported, downloadOnly, code });
    } finally {
      startingRef.current = false;
    }
  }, [workspace, storageMode, autoSave, clearLogs, session, quality, useOpenGL, openGLSupported, downloadOnly, revealLine, reportSaveError]);

  useEffect(() => {
    activeFileRef.current = workspace.activeFile;
    filesRef.current = workspace.files;
    sessionActiveRef.current = session.active;
    startRenderRef.current = startRender;
  });

  const save = useCallback(
    async (options?: { force?: boolean }) => {
      if (!workspace.activeFile) return;
      try {
        const result = await workspace.save(options);
        if (result.syntaxError) {
          const syntax = result.syntaxError;
          toast.warning("Saved, but this file has a syntax error", {
            id: "syntax-error",
            description: `Line ${syntax.line}: ${syntax.message}`,
            action: { label: "Go to line", onClick: () => revealLine(syntax.line) },
          });
        }
      } catch (err) {
        reportSaveError(err, "Couldn't save the file.");
      }
    },
    [workspace, revealLine, reportSaveError],
  );
  useEffect(() => {
    saveRef.current = save;
  });

  // A syntax-error toast is stale once the error is fixed.
  const hasSyntaxError = workspace.syntaxError !== null;
  useEffect(() => {
    if (!hasSyntaxError) toast.dismiss("syntax-error");
  }, [hasSyntaxError]);

  // ---- Preview follows the open file ---------------------------------------
  // Opening a file (or reloading the page) shows that scene's newest render
  // instead of "Nothing rendered yet" or a clip from another file.
  const filesReady = workspace.filesStatus === "ready";
  const bindKey = filesReady && workspace.activeFile ? `${storageMode}\n${workspace.activeFile}\n${workspace.selectedScene}` : null;
  useEffect(() => {
    const file = activeFileRef.current;
    if (!bindKey || !file) return;
    const scene = workspace.selectedScene;
    if (previewBelongsTo(previewRef.current, file, scene)) return;
    const last = latestRenderFor(filesRef.current.media, file, scene);
    showPreview(last ? previewFromMedia(last) : null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bindKey, showPreview]);

  // ---- Auto-render -------------------------------------------------------
  const codeRef = useRef(workspace.code);
  useEffect(() => {
    codeRef.current = workspace.code;
  });
  // Opening a file is not an edit: don't auto-render just because one loaded.
  useEffect(() => {
    lastRenderedCode.current = codeRef.current;
  }, [workspace.activeFile]);

  useEffect(() => {
    if (!autoRender || !workspace.activeFile || workspace.code === lastRenderedCode.current) return;
    const timer = setTimeout(() => {
      if (sessionActiveRef.current) pendingAutoRender.current = true;
      else void startRenderRef.current();
    }, AUTO_RENDER_DELAY_MS);
    return () => clearTimeout(timer);
  }, [autoRender, workspace.code, workspace.activeFile]);

  // ---- Global shortcuts & unload guard -----------------------------------
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
      if (event.key.toLowerCase() === "s") {
        event.preventDefault();
        void saveRef.current();
      } else if (event.key === "Enter") {
        event.preventDefault();
        void startRenderRef.current();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const hasUnsavedWork = workspace.hasUnsavedWork;
  useEffect(() => {
    if (!hasUnsavedWork) return;
    const onBeforeUnload = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [hasUnsavedWork]);

  // Offer setup once per browser session when Manim itself is missing.
  useEffect(() => {
    if (!manimMissing) return;
    try {
      if (sessionStorage.getItem(SETUP_SHOWN_KEY)) return;
      sessionStorage.setItem(SETUP_SHOWN_KEY, "1");
    } catch {
      // ignore
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSetupOpen(true);
  }, [manimMissing]);

  useEffect(
    () => () => {
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
    },
    [],
  );

  // ---- Actions -----------------------------------------------------------
  const scriptNames = workspace.files.scripts.map((script) => script.name);
  const videos = useMemo(() => workspace.files.media.filter((item) => item.type === "video"), [workspace.files.media]);

  const openFile = (name: string) => {
    if (name === workspace.activeFile) return;
    workspace.openFile(name).catch((err) => toast.error(errorMessage(err, `Couldn't open ${name}.`)));
  };

  const insertCode = (code: string, mode: InsertMode) => {
    if (!editorRef.current?.insertText(code, mode)) toast.error("Open a script to insert code into.");
  };

  const jumpToLine = (line: number) => revealLine(line);

  const selectSidebarView = (view: SidebarView) => {
    const panel = sidebarPanelRef.current;
    if (view === sidebarView && panel && !panel.isCollapsed()) {
      panel.collapse();
      return;
    }
    setSidebarView(view);
    if (panel?.isCollapsed()) panel.expand();
  };

  const changeSetting = <K extends keyof Settings>(key: K, value: Settings[K]) => {
    const setters: { [P in keyof Settings]: (value: Settings[P]) => void } = {
      storageMode: setStorageMode,
      autoSave: setAutoSave,
      downloadOnly: setDownloadOnly,
      useOpenGL: setUseOpenGL,
      loopPreview: setLoopPreview,
      editorFontSize: setEditorFontSize,
    };
    setters[key](value);
  };

  const requestDeleteScript = (name: string) =>
    setConfirm({
      title: `Delete ${name}?`,
      description:
        storageMode === "browser"
          ? "The script is removed from this browser. This can't be undone."
          : "The file is removed from the workspace folder. Its renders are kept. This can't be undone.",
      confirmLabel: "Delete",
      tone: "danger",
      onConfirm: async () => {
        await workspace.deleteFile(name);
        // Nothing about the deleted file should linger in the preview or status bar.
        setLastOutcome((outcome) => (outcome?.request.filename === name ? null : outcome));
        setCursor(null);
        if (logsFile === name) {
          clearLogs();
          setLogsFile(null);
        }
        toast.dismiss("syntax-error");
        toast.dismiss("render-failed");
      },
    });

  const requestDeleteMedia = (item: MediaFile) =>
    setConfirm({
      title: `Delete this render?`,
      description: `${item.scene}${item.quality ? ` (${item.quality})` : ""} will be removed from workspace/media.`,
      confirmLabel: "Delete",
      tone: "danger",
      onConfirm: async () => {
        await workspace.deleteMedia(item);
        if (previewRef.current?.mediaPath === item.path) showPreview(null);
      },
    });

  const requestDeleteAsset = (asset: AssetFile) =>
    setConfirm({
      title: `Delete ${asset.name}?`,
      description: "Scenes that load this file will fail to render until you upload it again.",
      confirmLabel: "Delete",
      tone: "danger",
      onConfirm: () => workspace.deleteAsset(asset.name),
    });

  const requestReplaceWithTemplate = (template: SceneTemplate) =>
    setConfirm({
      title: "Replace the editor contents?",
      description: `${workspace.activeFile} will show the “${template.title}” template. Undo with ${MOD_KEY}+Z, or don't save to keep the file as it is.`,
      confirmLabel: "Replace",
      onConfirm: () => workspace.setCode(template.code),
    });

  const createFile = async (name: string) => {
    await workspace.createFile(name, newFile?.code ?? newSceneCode(classNameFromFile(name)));
  };

  const activeSteps = workspace.animations[workspace.selectedScene] ?? [];
  const renderingSteps = session.active ? (workspace.animations[session.active.request.scene] ?? []) : [];
  const [percentFloor, setPercentFloor] = useState<{ id: string; value: number } | null>(null);
  const rawPercent = session.active ? overallPercent(session.active, expandedStepCount(renderingSteps)) : null;
  let renderPercent: number | null = null;
  if (!session.active) {
    if (percentFloor !== null) setPercentFloor(null);
  } else {
    const previous = percentFloor?.id === session.active.id ? percentFloor.value : null;
    const next = risingPercent(previous, rawPercent) ?? 0;
    renderPercent = next;
    if (previous !== next) setPercentFloor({ id: session.active.id, value: next });
  }
  const activeStep =
    session.active && session.active.request.scene === workspace.selectedScene
      ? stepIndexForAnimation(activeSteps, session.active.progress?.animation)
      : null;
  const canRender = online && Boolean(workspace.activeFile) && !session.active;

  // The tab title shows unsaved changes and render progress, even in a background tab.
  const activeFileName = workspace.activeFile;
  const isDirty = workspace.isDirty;
  useEffect(() => {
    const file = activeFileName ? `${isDirty ? "● " : ""}${activeFileName} — ` : "";
    const progress = renderPercent !== null ? `${renderPercent}% · ` : "";
    document.title = `${progress}${file}Manim Composer`;
  }, [activeFileName, isDirty, renderPercent]);
  // Line links only make sense when the output belongs to the open file.
  const linkFiles = useMemo(
    () => (logsFile && logsFile === workspace.activeFile ? [logsFile] : []),
    [logsFile, workspace.activeFile],
  );

  // ---- Layout ------------------------------------------------------------
  const sidebarContent = (() => {
    switch (sidebarView) {
      case "files":
        return (
          <FilesPanel
            files={workspace.files}
            filesError={workspace.filesStatus === "error"}
            storageMode={storageMode}
            activeFile={workspace.activeFile}
            dirtyFiles={workspace.dirtyFiles}
            previewPath={preview?.mediaPath ?? null}
            onOpen={openFile}
            onNew={() => setNewFile({ suggestedName: uniqueName("scene.py", scriptNames) })}
            onRename={async (oldName, newName) => {
              await workspace.renameFile(oldName, newName);
              setLogsFile((file) => (file === oldName ? newName : file));
            }}
            onDelete={requestDeleteScript}
            onRefresh={() => void workspace.refresh()}
            onPreviewMedia={(item) => showPreview(previewFromMedia(item))}
            onDeleteMedia={requestDeleteMedia}
            onCompare={() => setCompareOpen(true)}
          />
        );
      case "templates":
        return (
          <TemplatesPanel
            latexAvailable={latexAvailable}
            canReplace={Boolean(workspace.activeFile)}
            onCreateFrom={(template) =>
              setNewFile({ suggestedName: uniqueName(template.filename, scriptNames), templateTitle: template.title, code: template.code })
            }
            onReplaceWith={requestReplaceWithTemplate}
          />
        );
      case "shapes":
        return <ShapeBuilderPanel canInsert={Boolean(workspace.activeFile)} onInsert={(code) => insertCode(code, "block")} />;
      case "latex":
        return (
          <Suspense fallback={<div className="h-full bg-surface" />}>
            <LatexPanel
              latexAvailable={latexAvailable}
              canInsert={Boolean(workspace.activeFile)}
              onInsert={(code) => insertCode(code, "block")}
              onOpenSetup={() => setSetupOpen(true)}
            />
          </Suspense>
        );
      case "assets":
        return (
          <AssetsPanel
            assets={workspace.files.assets}
            canInsert={Boolean(workspace.activeFile)}
            onUpload={workspace.uploadAsset}
            onInsert={(code) => insertCode(code, "block")}
            onDelete={requestDeleteAsset}
          />
        );
      case "system":
        return (
          <SystemPanel
            diagnostics={diagnostics.data}
            offline={diagnostics.status === "offline"}
            onRefresh={() => void diagnostics.refresh()}
            onOpenSetup={() => setSetupOpen(true)}
          />
        );
      case "settings":
        return (
          <SettingsPanel
            settings={{ storageMode, autoSave, downloadOnly, useOpenGL, loopPreview, editorFontSize }}
            openGLSupported={openGLSupported}
            onChange={changeSetting}
          />
        );
    }
  })();

  return (
    <TooltipProvider delayDuration={400} skipDelayDuration={200}>
      <div className="flex h-dvh min-h-0 flex-col bg-canvas text-fg">
        <button
          type="button"
          onClick={() => editorRef.current?.focus()}
          className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-[100] focus:rounded-md focus:bg-accent focus:px-3 focus:py-1.5 focus:text-xs focus:font-medium focus:text-accent-fg"
        >
          Skip to editor
        </button>
        <TopBar needsSetup={manimMissing} onOpenSetup={() => setSetupOpen(true)} />

        <div className="flex min-h-0 flex-1">
          <ActivityBar
            view={sidebarView}
            open={sidebarOpen}
            badges={{ system: manimMissing }}
            onSelect={selectSidebarView}
          />
          <Group orientation="horizontal" id="mc-layout-main" {...mainLayout} className="min-w-0 flex-1">
            <Panel
              id="sidebar"
              panelRef={sidebarPanelRef}
              defaultSize="240px"
              minSize="200px"
              maxSize="320px"
              collapsible
              onResize={(size) => setSidebarOpen(size.inPixels > 0)}
            >
              {sidebarContent}
            </Panel>
            <ResizeHandle direction="horizontal" />
            {/* Must cover the editor + preview minimums below, or the group fights itself at 1024 px. */}
            <Panel id="work" minSize="568px">
              <Group orientation="vertical" id="mc-layout-work" {...workLayout}>
                <Panel id="top" minSize={`${workSizes.topMinPx}px`}>
                  <Group orientation="horizontal" id="mc-layout-top" {...topLayout}>
                    <Panel id="editor" minSize="300px">
                      <EditorPane
                        ref={editorRef}
                        storageKey={storageMode}
                        activeFile={workspace.activeFile}
                        code={workspace.code}
                        isDirty={workspace.isDirty}
                        scenes={workspace.scenes}
                        selectedScene={workspace.selectedScene}
                        quality={quality}
                        autoRender={autoRender}
                        active={shownRender.active}
                        latexAvailable={latexAvailable}
                        canRender={canRender}
                        fontSize={editorFontSize}
                        syntaxError={workspace.syntaxError}
                        stopping={shownRender.stopping}
                        onCodeChange={workspace.setCode}
                        onCursorChange={setCursor}
                        onSceneChange={workspace.setSelectedScene}
                        onQualityChange={setQuality}
                        onAutoRenderChange={setAutoRender}
                        onSave={() => void save()}
                        onRender={() => void startRender()}
                        onCancel={session.cancel}
                        onNewFile={() => setNewFile({ suggestedName: uniqueName("scene.py", scriptNames) })}
                        onOpenSetup={() => setSetupOpen(true)}
                      />
                    </Panel>
                    <ResizeHandle direction="horizontal" />
                    <Panel id="preview" defaultSize="42%" minSize="260px">
                      <PreviewPane
                        preview={preview}
                        active={shownRender.active}
                        stopping={shownRender.stopping}
                        stepCount={expandedStepCount(renderingSteps)}
                        lastOutcome={lastOutcome?.request.filename === workspace.activeFile ? lastOutcome : null}
                        loop={loopPreview}
                        selectedScene={workspace.selectedScene}
                        canRender={canRender}
                        canCompare={videos.length > 1}
                        onRender={() => void startRender()}
                        onCancel={session.cancel}
                        onCompare={() => setCompareOpen(true)}
                        onShowConsole={() => {
                          setBottomTab("console");
                          expandBottom();
                        }}
                      />
                    </Panel>
                  </Group>
                </Panel>
                <ResizeHandle direction="vertical" />
                <Panel
                  id="bottom"
                  panelRef={bottomPanelRef}
                  defaultSize={`${workSizes.bottomDefaultPx}px`}
                  minSize="120px"
                  maxSize="60%"
                  collapsible
                  collapsedSize="36px"
                  groupResizeBehavior="preserve-pixel-size"
                  onResize={(size) => {
                    setBottomCollapsed(size.inPixels <= 40);
                    setBottomPx(size.inPixels);
                  }}
                >
                  <BottomPanel
                    tab={bottomTab}
                    onTabChange={(tab) => {
                      setBottomTab(tab);
                      expandBottom();
                    }}
                    collapsed={bottomCollapsed}
                    onToggleCollapsed={() => (bottomCollapsed ? bottomPanelRef.current?.expand() : bottomPanelRef.current?.collapse())}
                    logs={logs}
                    linkFiles={linkFiles}
                    logsFile={logsFile !== workspace.activeFile ? logsFile : null}
                    onOpenLogsFile={openFile}
                    onClearLogs={() => {
                      clearLogs();
                      setLogsFile(null);
                    }}
                    scene={workspace.selectedScene}
                    steps={activeSteps}
                    activeStep={activeStep}
                    renderPercent={renderPercent}
                    onJumpToLine={jumpToLine}
                  />
                </Panel>
              </Group>
            </Panel>
          </Group>
        </div>

        <StatusBar
          backend={diagnostics.status}
          connection={session.connection}
          active={session.active}
          renderPercent={renderPercent}
          lastOutcome={lastOutcome}
          storageMode={storageMode}
          cursor={workspace.activeFile ? cursor : null}
          diagnostics={diagnostics.data}
          onOpenSetup={() => setSetupOpen(true)}
          onShowConsole={() => {
            setBottomTab("console");
            expandBottom();
          }}
        />
      </div>

      <NewFileDialog request={newFile} existing={scriptNames} onClose={() => setNewFile(null)} onCreate={createFile} />
      <ConfirmDialog request={confirm} onClose={() => setConfirm(null)} />
      <CompareDialog open={compareOpen} onOpenChange={setCompareOpen} videos={videos} />
      <SetupDialog
        open={setupOpen}
        onOpenChange={setSetupOpen}
        diagnostics={diagnostics.data}
        offline={diagnostics.status === "offline"}
        isInstalling={diagnostics.isInstalling}
        onInstall={diagnostics.install}
        onRefresh={diagnostics.refresh}
      />
      <Toaster
        theme="dark"
        position="bottom-right"
        // Above the console/timeline panel, so an error toast never covers the traceback it points to.
        offset={{ bottom: bottomPx === null ? 36 : Math.round(bottomPx) + 24 + 12, right: 16 }}
        toastOptions={{
          classNames: {
            toast: "!bg-overlay !border-line-strong !text-fg !shadow-popover !rounded-lg !text-[13px]",
            description: "!text-fg-muted !text-xs",
            actionButton: "!bg-accent !text-accent-fg !font-medium",
            error: "[&_[data-icon]]:!text-danger",
            success: "[&_[data-icon]]:!text-success",
            warning: "[&_[data-icon]]:!text-warning",
          },
        }}
      />
    </TooltipProvider>
  );
}

