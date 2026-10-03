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
import { usePersistentState } from "@/hooks/usePersistentState";
import { useRenderSession, type ActiveRender, type RenderOutcome, type RenderOutput } from "@/hooks/useRenderSession";
import { useWorkspace } from "@/hooks/useWorkspace";
import { apiUrl, errorMessage } from "@/lib/api";
import { QUALITY_FOR_PROFILE } from "@/lib/constants";
import { classNameFromFile } from "@/lib/format";
import { findErrorLocation } from "@/lib/logs";
import { overallPercent } from "@/lib/progress";
import { STORAGE_KEYS } from "@/lib/storage";
import { newSceneCode, type SceneTemplate } from "@/lib/templates";
import type { AssetFile, MediaFile, PreviewItem, Quality, StorageMode } from "@/lib/types";

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

function previewFromMedia(item: MediaFile): PreviewItem {
  return {
    url: `${apiUrl(item.url)}?v=${Math.round(item.modified)}`,
    kind: item.type,
    title: item.scene,
    location: `workspace/media/${item.path}`,
    mediaPath: item.path,
    downloadName: item.name,
  };
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
  const [preview, setPreview] = useState<PreviewItem | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const [lastOutcome, setLastOutcome] = useState<RenderOutcome | null>(null);
  const [cursor, setCursor] = useState<{ line: number; column: number } | null>(null);
  const [bottomTab, setBottomTab] = useState<BottomTab>("console");
  const [bottomCollapsed, setBottomCollapsed] = useState(false);
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

  const showPreview = useCallback((item: PreviewItem) => {
    if (objectUrlRef.current && objectUrlRef.current !== item.url) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
    if (item.url.startsWith("blob:")) objectUrlRef.current = item.url;
    setPreview(item);
  }, []);

  const expandBottom = useCallback(() => {
    if (bottomPanelRef.current?.isCollapsed()) bottomPanelRef.current.expand();
  }, [bottomPanelRef]);

  // ---- Render session ----------------------------------------------------
  const { refreshFiles } = workspace;
  const activeFileRef = useRef(workspace.activeFile);
  const pendingAutoRender = useRef(false);
  const startRenderRef = useRef<() => Promise<void>>(async () => {});

  const handleOutput = useCallback(
    async (output: RenderOutput, render: ActiveRender) => {
      const title = render.request.scene;
      if (output.temporary) {
        try {
          const response = await fetch(apiUrl(output.url));
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          const url = URL.createObjectURL(await response.blob());
          showPreview({ url, kind: output.kind, title, location: "Downloaded · not kept on the server", downloadName: output.filename });
          triggerDownload(url, output.filename);
        } catch {
          toast.error("The render finished, but downloading it failed.");
        }
        return;
      }
      showPreview({
        url: `${apiUrl(output.url)}?v=${Date.now()}`,
        kind: output.kind,
        title,
        location: `workspace/${output.relPath}`,
        mediaPath: output.relPath.replace(/^media\//, ""),
        downloadName: output.filename,
      });
      void refreshFiles();
    },
    [refreshFiles, showPreview],
  );

  const handleFinished = useCallback(
    (outcome: RenderOutcome) => {
      setLastOutcome(outcome);
      if (!outcome.success && outcome.status !== "cancelled") {
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
          description: location ? `${location.message} (line ${location.line})` : "See the console for details.",
          action: location
            ? { label: "Go to line", onClick: () => editorRef.current?.revealLine(location.line) }
            : undefined,
        });
      } else if (outcome.success && !outcome.output) {
        toast.warning("Manim finished but produced no output file.");
      }
      if (pendingAutoRender.current) {
        pendingAutoRender.current = false;
        setTimeout(() => void startRenderRef.current(), 0);
      }
    },
    [expandBottom, logSnapshot],
  );

  const session = useRenderSession({ log, onOutput: handleOutput, onFinished: handleFinished });
  const sessionActiveRef = useRef(session.active);
  const lastRenderedCode = useRef<string | null>(null);

  const startRender = useCallback(async () => {
    const filename = workspace.activeFile;
    if (sessionActiveRef.current || !filename) return;
    editorRef.current?.clearMarkers();

    let scenes = workspace.scenes;
    let code: string | undefined;
    const buffer = workspace.code;
    try {
      if (storageMode === "disk" && autoSave) {
        scenes = (workspace.isDirty ? await workspace.save() : await workspace.parseNow())?.scenes ?? scenes;
      } else {
        scenes = (await workspace.parseNow())?.scenes ?? scenes;
        // Send the buffer unless it is identical to the file on disk.
        if (storageMode === "browser" || workspace.isDirty) code = buffer;
      }
    } catch (err) {
      toast.error(errorMessage(err, "Couldn't save before rendering."));
      return;
    }

    const scene = scenes.includes(workspace.selectedScene) ? workspace.selectedScene : scenes[0];
    if (!scene) {
      toast.error("No scene to render", { description: "Add a class that inherits from Scene, e.g. class Intro(Scene)." });
      return;
    }
    if (scene !== workspace.selectedScene) workspace.setSelectedScene(scene);

    clearLogs();
    lastRenderedCode.current = buffer;
    session.start({ filename, scene, quality, useOpenGL: useOpenGL && openGLSupported, downloadOnly, code });
  }, [workspace, storageMode, autoSave, clearLogs, session, quality, useOpenGL, openGLSupported, downloadOnly]);

  useEffect(() => {
    activeFileRef.current = workspace.activeFile;
    sessionActiveRef.current = session.active;
    startRenderRef.current = startRender;
  });

  const save = useCallback(async () => {
    if (!workspace.activeFile) return;
    try {
      await workspace.save();
    } catch (err) {
      toast.error(errorMessage(err, "Couldn't save the file."));
    }
  }, [workspace]);
  const saveRef = useRef(save);
  useEffect(() => {
    saveRef.current = save;
  });

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

  const jumpToLine = (line: number) => editorRef.current?.revealLine(line);

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
      onConfirm: () => workspace.deleteFile(name),
    });

  const requestDeleteMedia = (item: MediaFile) =>
    setConfirm({
      title: `Delete this render?`,
      description: `${item.scene}${item.quality ? ` (${item.quality})` : ""} will be removed from workspace/media.`,
      confirmLabel: "Delete",
      tone: "danger",
      onConfirm: async () => {
        await workspace.deleteMedia(item);
        if (preview?.mediaPath === item.path) setPreview(null);
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
      description: `${workspace.activeFile} will show the “${template.title}” template. Undo with Ctrl+Z, or don't save to keep the file as it is.`,
      confirmLabel: "Replace",
      onConfirm: () => workspace.setCode(template.code),
    });

  const createFile = async (name: string) => {
    await workspace.createFile(name, newFile?.code ?? newSceneCode(classNameFromFile(name)));
  };

  const activeSteps = workspace.animations[workspace.selectedScene] ?? [];
  const renderingSteps = session.active ? (workspace.animations[session.active.request.scene] ?? []) : [];
  const renderPercent = session.active ? (overallPercent(session.active, renderingSteps.length) ?? 0) : null;
  const activeStep =
    session.active && session.active.request.scene === workspace.selectedScene
      ? (session.active.progress?.animation ?? null)
      : null;
  const canRender = online && Boolean(workspace.activeFile) && !session.active;
  const linkFiles = useMemo(
    () => [lastOutcome?.request.filename, session.active?.request.filename, workspace.activeFile].filter((name): name is string => Boolean(name)),
    [lastOutcome, session.active, workspace.activeFile],
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
            onRename={(oldName, newName) => workspace.renameFile(oldName, newName)}
            onDelete={requestDeleteScript}
            onRefresh={() => void workspace.refreshFiles()}
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
              onInsert={(code) => insertCode(code, "inline")}
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
            onInsert={(code) => insertCode(code, code.startsWith("self.") ? "block" : "inline")}
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
        <TopBar needsSetup={manimMissing || !latexAvailable} onOpenSetup={() => setSetupOpen(true)} />

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
              defaultSize="280px"
              minSize="220px"
              maxSize="480px"
              collapsible
              groupResizeBehavior="preserve-pixel-size"
              onResize={(size) => setSidebarOpen(size.inPixels > 0)}
            >
              {sidebarContent}
            </Panel>
            <ResizeHandle direction="horizontal" />
            <Panel id="work" minSize="480px">
              <Group orientation="vertical" id="mc-layout-work" {...workLayout}>
                <Panel id="top" minSize="200px">
                  <Group orientation="horizontal" id="mc-layout-top" {...topLayout}>
                    <Panel id="editor" minSize="280px">
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
                        active={session.active}
                        latexAvailable={latexAvailable}
                        canRender={canRender}
                        fontSize={editorFontSize}
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
                        active={session.active}
                        stepCount={renderingSteps.length}
                        lastOutcome={lastOutcome}
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
                  defaultSize="220px"
                  minSize="120px"
                  collapsible
                  collapsedSize="36px"
                  groupResizeBehavior="preserve-pixel-size"
                  onResize={(size) => setBottomCollapsed(size.inPixels <= 40)}
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
                    onClearLogs={clearLogs}
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
        offset={{ bottom: 36, right: 16 }}
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

