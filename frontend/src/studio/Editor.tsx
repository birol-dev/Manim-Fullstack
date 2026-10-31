/** The editor: a form on the left, the live preview on the right, export on top. */
import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, ArrowLeft, Check, CloudOff, Download, FileDown, Film, FolderDown, Layers, Palette, PenLine, Redo2, Sparkles, Undo2, Volume2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError } from "@/lib/api";

import { createProject, friendlyError, getProject, updateProject } from "./api";
import { saveProjectFile } from "./portableFile";
import { ActionMenu } from "./ProjectMenu";
import { Autosaver, type SaveStatus } from "./autosave";
import { FrameIcon, Segments, Spinner } from "./components";
import { fieldErrorsOf, hasErrorsUnder, matchErrors } from "./errors";
import { ExportDialog, ExportsPanel } from "./exports";
import { FormContext } from "./form/context";
import { SchemaForm } from "./form/SchemaForm";
import { useExportActivity, useLivePreview } from "./hooks";
import { isTextEditor } from "./editorHistory";
import { useEditorHistory } from "./useEditorHistory";
import "./editor.css";
import { LookPanel } from "./LookPanel";
import { SoundPanel } from "./SoundPanel";
import { ASPECTS, initialSettings, isPortrait } from "./options";
import { readBrandKit, readDefaultFormat, readDefaultTheme } from "./preferences";
import { stableKey } from "./preview";
import { PreviewPanel, type PreviewView } from "./PreviewPanel";
import { navigate, type Route } from "./router";
import { fieldPaths, fieldsOf, initialParams } from "./schemaForm";
import type { Aspect, Catalog, FieldError, Params, PreviewRequest, Project, RenderSettings, TemplateInfo, Theme } from "./types";

const SETTINGS_PATHS = [
  "settings",
  "settings.aspect",
  "settings.length",
  "settings.theme",
  "settings.background",
  "settings.background.kind",
  "settings.background.color",
  "settings.background.color2",
  "settings.energy",
  "settings.ending",
  "settings.safe_zone",
  "settings.locale",
  "settings.sound",
  "settings.sound.effects",
  "settings.sound.effects_volume",
  "settings.sound.music",
  "settings.sound.music.asset",
  "settings.sound.music.track",
  "settings.sound.music.volume",
  "settings.sound.music.fade_out",
  "settings.sound.music.loop",
];

interface InitialState {
  title: string;
  params: Params;
  settings: RenderSettings;
  projectId: string | null;
  updated: Project["updated"] | null;
}

/** How often an open project checks for changes saved elsewhere (an AI agent, another window). */
export const REMOTE_CHECK_MS = 4000;

/** ISO timestamps from the server sort as text; numbers (tests) as numbers. */
function isNewer(a: Project["updated"], b: Project["updated"]) {
  return typeof a === "number" && typeof b === "number" ? a > b : String(a) > String(b);
}

interface EditorPageProps {
  catalog: Catalog;
  route: Extract<Route, { kind: "new" } | { kind: "project" }>;
  onProjectCreated: (id: string) => void;
}

function Message({ title, line }: { title: string; line: string }) {
  return (
    <div className="studio-empty h-full">
      <div className="studio-empty-picture" aria-hidden>
        <Film />
      </div>
      <h1 className="studio-empty-title">{title}</h1>
      <p className="studio-empty-line">{line}</p>
      <div className="studio-empty-actions">
        <Button asChild variant="primary" size="md">
          <a href="#/">
            <ArrowLeft /> Back to all designs
          </a>
        </Button>
      </div>
    </div>
  );
}

/**
 * A new video starts from its card, then from the workspace's defaults where they fit: a format
 * this template offers, a theme that exists, and a snapshot of the brand kit. Saved projects skip
 * this, so later brand changes never drift into an existing video.
 */
function newVideoSettings(template: TemplateInfo, card: Partial<RenderSettings> | undefined, themes: Theme[]): RenderSettings {
  const settings = initialSettings(template, card);
  const format = readDefaultFormat();
  if (format && template.aspects.includes(format as Aspect)) settings.aspect = format as Aspect;
  const theme = readDefaultTheme();
  if (theme && themes.some((item) => item.id === theme)) settings.theme = theme;
  const kit = readBrandKit();
  if (kit) settings.brand = { ...settings.brand, ...kit };
  return settings;
}

/** Picks what to edit: a new video from a card, or a saved project. */
export function EditorPage({ catalog, route, onProjectCreated }: EditorPageProps) {
  // The route this editor opened with. Saving a new video renames the URL to #/project/<id>;
  // that must not reload the editor.
  const [opened] = useState(route);
  if (opened.kind === "new") {
    const template = catalog.templates.find((item) => item.id === opened.template);
    if (!template) {
      return <Message title="This design isn't available anymore." line="The designs have changed. Pick another one to start from." />;
    }
    const card = template.presets.find((item) => item.id === opened.preset);
    const initial: InitialState = {
      title: card?.title ?? template.title,
      params: initialParams(template.defaults, card?.params),
      settings: newVideoSettings(template, card?.settings, catalog.themes ?? []),
      projectId: null,
      updated: null,
    };
    return <EditorBody catalog={catalog} template={template} initial={initial} newPreset={opened.preset} onProjectCreated={onProjectCreated} />;
  }
  return <ProjectLoader catalog={catalog} id={opened.id} onProjectCreated={onProjectCreated} />;
}

function ProjectLoader({ catalog, id, onProjectCreated }: { catalog: Catalog; id: string; onProjectCreated: (id: string) => void }) {
  const [state, setState] = useState<{ initial: InitialState; template: TemplateInfo } | { error: unknown } | null>(null);
  useEffect(() => {
    let live = true;
    getProject(id).then(
      (project) => {
        if (!live) return;
        const template = catalog.templates.find((item) => item.id === project.template);
        if (!template) {
          setState({ error: new Error("This video uses a design that isn't available anymore.") });
          return;
        }
        setState({
          template,
          initial: {
            title: project.title,
            params: initialParams(template.defaults, project.params),
            settings: initialSettings(template, project.settings),
            projectId: project.id,
            updated: project.updated,
          },
        });
      },
      (error) => live && setState({ error }),
    );
    return () => {
      live = false;
    };
  }, [catalog, id]);
  if (!state) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-sm text-fg-muted">
        <Spinner /> Opening your video…
      </div>
    );
  }
  if ("error" in state) {
    const missing = state.error instanceof ApiError && state.error.status === 404;
    return (
      <Message
        title={missing ? "This video couldn't be found." : "Couldn't open this video."}
        line={missing ? "It may have been deleted, or saved on another computer." : friendlyError(state.error)}
      />
    );
  }
  return <EditorBody catalog={catalog} template={state.template} initial={state.initial} newPreset="" onProjectCreated={onProjectCreated} />;
}

function SaveIndicator({ status, hasProject, onRetry }: { status: SaveStatus; hasProject: boolean; onRetry: () => void }) {
  if (status === "pending" || status === "saving") {
    return (
      <span className="flex items-center gap-1.5 text-xs text-fg-subtle" role="status">
        <Spinner className="size-3" /> Saving…
      </span>
    );
  }
  if (status === "error") {
    return (
      <span className="studio-save-error" role="status">
        <CloudOff aria-hidden className="size-3.5" /> Not saved · <button type="button" aria-label="Retry save" onClick={onRetry}>Retry</button>
      </span>
    );
  }
  if (status === "saved" || hasProject) {
    return (
      <span className="flex items-center gap-1 text-xs text-fg-subtle" role="status">
        <Check className="size-3.5" /> Saved
      </span>
    );
  }
  return <span className="hidden text-xs text-fg-subtle sm:inline">Changes save automatically</span>;
}

function FormatPicker({ aspects, value, onChange }: { aspects: Aspect[]; value: Aspect; onChange: (aspect: Aspect) => void }) {
  const options = ASPECTS.filter((item) => aspects.includes(item.value)).map((item) => ({
    value: item.value,
    title: `${item.label} ${item.value}: ${item.hint}`,
    label: (
      <>
        <FrameIcon w={item.w} h={item.h} />
        <span className="studio-format-label">{item.label}</span>
        <span className="text-fg-subtle">{item.value}</span>
      </>
    ),
  }));
  if (options.length < 2) return null;
  return <Segments value={value} options={options} onChange={onChange} aria-label="Format" size="sm" className="studio-format-picker" />;
}

interface EditorBodyProps {
  catalog: Catalog;
  template: TemplateInfo;
  initial: InitialState;
  /** The card this new video started from, so "Make many" can use its text. */
  newPreset: string;
  onProjectCreated: (id: string) => void;
}

function EditorBody({ catalog, template, initial, newPreset, onProjectCreated }: EditorBodyProps) {
  const { snapshot: { title, params, settings }, change, travel, history, canUndo, canRedo } = useEditorHistory({ title: initial.title, params: initial.params, settings: initial.settings });
  const [initialProjectId] = useState(initial.projectId);
  const [hasProject, setHasProject] = useState(!!initial.projectId);
  const [tab, setTab] = useState("content");
  const [view, setView] = useState<PreviewView>("poster");
  const [exportOpen, setExportOpen] = useState(false);
  const [exportsOpen, setExportsOpen] = useState(false);
  const [exportsKey, setExportsKey] = useState(0);
  const { activity: exportActivity, markSeen: markExportsSeen } = useExportActivity(exportsOpen, exportsKey);
  const changeExportsOpen = (open: boolean) => {
    markExportsSeen();
    setExportsOpen(open);
  };
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [remoteNote, setRemoteNote] = useState(false);
  const [formVersion, setFormVersion] = useState(0);
  const nativeHistory = useRef(new WeakSet<HTMLElement>());
  const shortcut = /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘" : "Ctrl+";
  const [exportErrors, setExportErrors] = useState<{ key: string; errors: FieldError[] } | null>(null);

  const fields = useMemo(() => fieldsOf(template.schema), [template.schema]);
  const themes = useMemo(() => catalog.themes ?? [], [catalog.themes]);
  const theme = themes.find((item) => item.id === settings.theme);

  // Safe zones only matter (and are only offered) for tall formats.
  const effectiveSettings = useMemo<RenderSettings>(
    () => ({ ...settings, safe_zone: isPortrait(settings.aspect) && settings.safe_zone }),
    [settings],
  );
  const posterRequest: PreviewRequest = { template: template.id, params, settings: effectiveSettings, mode: "poster" };
  const requestKey = stableKey(posterRequest);
  const poster = useLivePreview(posterRequest);
  const [motionSession] = useState(() => initial.projectId ?? `editor-${crypto.randomUUID()}`);
  // Content-timed templates report their actual duration in storyboard metadata.
  const storyboard = useLivePreview(view === "storyboard" || (template.length_from_params && !!poster.response) ? { ...posterRequest, mode: "storyboard" } : null);

  // ---- Autosave ---------------------------------------------------------------------------
  const touched = useRef(false);
  const editVersion = useRef(0);
  const markTouched = () => {
    touched.current = true;
    editVersion.current += 1;
  };
  const saver = useRef<Autosaver | null>(null);
  const manyAfterSave = useRef(false);
  // `updated` of the version on screen: a newer one on the server was saved by someone else.
  const knownUpdate = useRef(initial.updated);
  const createdRef = useRef(onProjectCreated);
  useEffect(() => {
    createdRef.current = onProjectCreated;
  });
  useEffect(() => {
    const remember = (project: Project) => {
      knownUpdate.current = project.updated;
      return project;
    };
    const autosaver = new Autosaver({
      projectId: initialProjectId,
      create: (snapshot, keepalive) => createProject(snapshot, keepalive).then(remember),
      update: (id, snapshot, keepalive) =>
        updateProject(id, { title: snapshot.title, params: snapshot.params, settings: snapshot.settings }, keepalive).then(remember),
      onStatus: (status, error) => {
        if (status === "error") manyAfterSave.current = false;
        setSaveStatus(status);
        setSaveError(status === "error" ? friendlyError(error, "Couldn't save this video.") : null);
      },
      onCreated: (project) => {
        setHasProject(true);
        createdRef.current(project.id);
        if (manyAfterSave.current) {
          manyAfterSave.current = false;
          navigate({ kind: "many-project", id: project.id });
        }
      },
    });
    saver.current = autosaver;
    const onPageHide = () => autosaver.flush(true);
    window.addEventListener("pagehide", onPageHide);
    return () => {
      window.removeEventListener("pagehide", onPageHide);
      autosaver.flush();
      autosaver.dispose();
      if (saver.current === autosaver) saver.current = null;
    };
  }, [initialProjectId]);
  useEffect(() => {
    if (touched.current) saver.current?.change({ title: title.trim() || template.title, template: template.id, params, settings });
  }, [title, params, settings, template.id, template.title]);

  useEffect(() => {
    document.title = `${title.trim() || "Untitled video"} · Studio`;
  }, [title]);

  const setParam = (key: string, value: unknown, related: Params = {}) => {
    if (change({ params: { ...history.current.params, ...related, [key]: value } })) markTouched();
  };
  const patchSettings = (patch: Partial<RenderSettings>) => {
    const next = { ...history.current.settings, ...patch };
    if (patch.aspect && !isPortrait(patch.aspect)) next.safe_zone = false;
    if (change({ settings: next })) markTouched();
  };

  const makeMany = () => {
    const saved = saver.current?.id ?? initialProjectId;
    if (saved) {
      saver.current?.flush();
      navigate({ kind: "many-project", id: saved });
      return;
    }
    // Keep the words and look on screen: save once, then open the list maker on that project.
    if (!saver.current) {
      navigate({ kind: "many", template: template.id, preset: newPreset });
      return;
    }
    manyAfterSave.current = true;
    saver.current.change({ title: title.trim() || template.title, template: template.id, params, settings });
    saver.current.flush();
  };

  const saveFile = async () => {
    try {
      let id = saver.current?.id ?? initialProjectId;
      if (!id && saver.current) {
        saver.current.change({ title: title.trim() || template.title, template: template.id, params, settings });
        saver.current.flush();
        for (let attempt = 0; attempt < 50 && !id; attempt += 1) {
          await new Promise((resolve) => setTimeout(resolve, 100));
          id = saver.current?.id;
        }
      }
      if (!id) {
        toast.error("This video is still being saved. Try again in a moment.");
        return;
      }
      await updateProject(id, { title: title.trim() || template.title, params, settings });
      await saveProjectFile(id);
    } catch (error) {
      toast.error(friendlyError(error, "Couldn't save this video as a file."));
    }
  };

  const restore = (direction: "undo" | "redo") => {
    if (!travel(direction)) return;
    markTouched();
    setRemoteNote(false);
    setExportErrors(null);
    setFormVersion((value) => value + 1);
  };
  const shortcutRef = useRef({ restore });
  useEffect(() => { shortcutRef.current = { restore }; });
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.isComposing || event.altKey || !(event.ctrlKey || event.metaKey)) return;
      const key = event.key.toLowerCase();
      if (event.target instanceof Element && event.target.closest('[role="dialog"], [role="alertdialog"]')) return;
      if (key === "e") { event.preventDefault(); setExportOpen(true); return; }
      if (key !== "z" && key !== "y") return;
      // Native undo stacks aren't exposed. After typing, keep shortcuts local
      // until blur; the header buttons always use editor history.
      if (isTextEditor(event.target) && nativeHistory.current.has(event.target)) return;
      event.preventDefault();
      shortcutRef.current.restore(key === "y" || event.shiftKey ? "redo" : "undo");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // ---- Changes saved elsewhere (an AI agent over MCP) ---------------------------------------
  // Checked when the window comes back into focus and every few seconds while it's visible.
  // They're applied only while nothing typed here is waiting to be saved; your own edits win.
  const templateRef = useRef(template);
  useEffect(() => {
    templateRef.current = template;
  });
  useEffect(() => {
    if (!hasProject) return;
    let stopped = false;
    let checking = false;
    let noteTimer: ReturnType<typeof setTimeout> | undefined;
    const check = async () => {
      const id = saver.current?.id;
      if (stopped || checking || !id || document.hidden || saver.current?.dirty) return;
      const version = editVersion.current;
      const known = knownUpdate.current;
      checking = true;
      try {
        const project = await getProject(id);
        // Stale if anything was typed or saved here meanwhile.
        if (stopped || editVersion.current !== version || saver.current?.dirty || knownUpdate.current !== known) return;
        if (known !== null && !isNewer(project.updated, known)) return;
        knownUpdate.current = project.updated;
        if (known === null) return;
        const current = templateRef.current;
        touched.current = false;
        change({ title: project.title, params: initialParams(current.defaults, project.params), settings: initialSettings(current, project.settings) }, true);
        setExportErrors(null);
        setFormVersion((value) => value + 1);
        setRemoteNote(true);
        clearTimeout(noteTimer);
        noteTimer = setTimeout(() => setRemoteNote(false), 4000);
      } catch {
        // Offline or the server restarted: the next check tries again.
      } finally {
        checking = false;
      }
    };
    const onVisible = () => {
      if (!document.hidden) void check();
    };
    const timer = setInterval(() => void check(), REMOTE_CHECK_MS);
    window.addEventListener("focus", onVisible);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      stopped = true;
      clearInterval(timer);
      clearTimeout(noteTimer);
      window.removeEventListener("focus", onVisible);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [hasProject, change]);

  // ---- Errors -----------------------------------------------------------------------------
  const fieldErrors = useMemo(() => {
    const fromPreview = fieldErrorsOf(poster.error);
    const fromExport = exportErrors && exportErrors.key === requestKey ? exportErrors.errors : [];
    return [...fromPreview, ...fromExport.filter((error) => !fromPreview.some((item) => item.field === error.field))];
  }, [poster.error, exportErrors, requestKey]);
  const matched = useMemo(
    () => matchErrors(fieldErrors, [...fieldPaths(fields, params), ...SETTINGS_PATHS]),
    [fieldErrors, fields, params],
  );
  const contentBroken = hasErrorsUnder(matched.byPath, "params");
  const soundBroken = hasErrorsUnder(matched.byPath, "settings.sound");
  const lookBroken = Object.keys(matched.byPath).some((path) => path.startsWith("settings") && !path.startsWith("settings.sound"));
  const formContext = useMemo(
    () => ({ locale: settings.locale, theme, errors: matched.byPath }),
    [settings.locale, theme, matched.byPath],
  );

  const length = template.length_from_params
    ? storyboard.response?.storyboard?.length ?? template.default_length
    : settings.length ?? template.default_length;

  return (
    <div className="studio-editor" onInputCapture={(event) => { if (isTextEditor(event.target)) nativeHistory.current.add(event.target); }} onBlurCapture={(event) => { nativeHistory.current.delete(event.target); history.boundary(); }}>
      <header className="studio-editor-header">
        <div className="studio-editor-identity">
          <Button asChild variant="ghost" size="md" className="-ml-1">
            <a href="#/" aria-label="Back to all designs">
              <ArrowLeft />
              <span>All designs</span>
            </a>
          </Button>
          <div className="studio-title-group">
            <input
              value={title}
              maxLength={80}
              aria-label="Video title"
              placeholder="Untitled video"
              title={title || undefined}
              onChange={(event) => { if (change({ title: event.target.value })) markTouched(); }}
              className="studio-video-title"
              style={{ width: `calc(${Math.max(8, [...title].length + 1)}ch + 26px)` }}
            />
            {remoteNote ? (
              <span className="flex items-center gap-1 text-xs text-accent" role="status">
                <Sparkles className="size-3.5" /> Updated by your AI
              </span>
            ) : (
              <SaveIndicator status={saveStatus} hasProject={hasProject} onRetry={() => {
                saver.current?.change({ title: title.trim() || template.title, template: template.id, params, settings });
                saver.current?.flush();
              }} />
            )}
            <div className="studio-editor-history" role="group" aria-label="Edit history">
              <Tooltip content={`Undo (${shortcut}Z)`}><span><Button variant="ghost" size="icon" aria-label="Undo" disabled={!canUndo} onClick={() => restore("undo")}><Undo2 /></Button></span></Tooltip>
              <Tooltip content={`Redo (${shortcut}Shift+Z / ${shortcut}Y)`}><span><Button variant="ghost" size="icon" aria-label="Redo" disabled={!canRedo} onClick={() => restore("redo")}><Redo2 /></Button></span></Tooltip>
            </div>
          </div>
        </div>
        <FormatPicker aspects={template.aspects} value={settings.aspect} onChange={(aspect) => patchSettings({ aspect })} />
        <div className="studio-editor-actions">
          <ActionMenu
            className="studio-editor-file-menu"
            title={title.trim() || "this video"}
            items={[{ label: "Save as a file", icon: <FileDown aria-hidden />, onSelect: saveFile }]}
          />
          <Tooltip content="Your exports">
            <Button variant="ghost" size="icon" aria-label="Your exports" aria-description={exportActivity ? "An export is running or ready to open." : undefined} onClick={() => changeExportsOpen(true)} className="studio-exports-button">
              <FolderDown />
              {exportActivity && <span className="studio-export-activity" aria-hidden />}
            </Button>
          </Tooltip>
          <Button variant="secondary" size="md" onClick={makeMany} title="Make one video per row of a list" className="px-4">
            <Layers /> Make many
          </Button>
          <Button variant="primary" size="md" onClick={() => setExportOpen(true)} title={`Export (${shortcut}E)`} className="px-4">
            <Download /> Export
          </Button>
        </div>
      </header>

      {saveError && <p role="alert" className="studio-editor-save-error">{saveError} Use Retry save to try again.</p>}

      <div className="studio-editor-body">
        <aside className="studio-editor-sidebar">
          <Tabs value={tab} onValueChange={setTab} className="flex flex-col">
            <TabsList className="studio-editor-tabs">
              <TabsTrigger value="content" className="text-[13px]">
                <PenLine className="size-3.5" /> Content
                {contentBroken && <span className="size-1.5 rounded-full bg-danger" aria-label="has problems" />}
              </TabsTrigger>
              <TabsTrigger value="look" className="text-[13px]">
                <Palette className="size-3.5" /> Look
                {lookBroken && <span className="size-1.5 rounded-full bg-danger" aria-label="has problems" />}
              </TabsTrigger>
              <TabsTrigger value="sound" className="text-[13px]">
                <Volume2 className="size-3.5" /> Sound
                {soundBroken && <span className="size-1.5 rounded-full bg-danger" aria-label="has problems" />}
              </TabsTrigger>
            </TabsList>
            <FormContext.Provider value={formContext}>
              <TabsContent value="content" className="studio-editor-panel">
                {matched.unmatched.length > 0 && (
                  <div role="alert" className="studio-editor-problem">
                    <AlertTriangle aria-hidden className="mt-0.5 size-3.5 shrink-0 text-danger" />
                    <ul>
                      {matched.unmatched.map((error) => (
                        <li key={error.field + error.message}>{error.message}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {fields.length ? (
                  <SchemaForm key={formVersion} fields={fields} values={params} onChange={setParam} />
                ) : (
                  <p className="text-sm text-fg-muted">This design has nothing to fill in. Try the Look tab.</p>
                )}
              </TabsContent>
              <TabsContent value="look" className="studio-editor-panel">
                <LookPanel key={formVersion} settings={settings} onChange={patchSettings} template={template} themes={themes} errors={matched.byPath} />
              </TabsContent>
              <TabsContent value="sound" className="studio-editor-panel">
                <SoundPanel key={formVersion} value={settings.sound} onChange={(sound) => patchSettings({ sound })} tracks={catalog.music_tracks} errors={matched.byPath} />
              </TabsContent>
            </FormContext.Provider>
          </Tabs>
        </aside>

        <main className="studio-editor-preview">
          <PreviewPanel
            view={view}
            onViewChange={setView}
            poster={poster}
            storyboard={storyboard}
            aspect={settings.aspect}
            transparent={settings.background?.kind === "transparent"}
            length={length}
            motionRequest={posterRequest}
            motionSession={motionSession}
          />
        </main>
      </div>

      <ExportDialog
        open={exportOpen}
        onOpenChange={setExportOpen}
        request={() => ({ template: template.id, params, settings: effectiveSettings, title: title.trim() || template.title })}
        transparentBackground={settings.background?.kind === "transparent"}
        onFieldErrors={(errors) => setExportErrors({ key: requestKey, errors })}
        onActivity={() => setExportsKey((value) => value + 1)}
        onSeen={markExportsSeen}
        onStart={() => {
          if (!saver.current?.id) saver.current?.change({ title: title.trim() || template.title, template: template.id, params, settings });
          saver.current?.flush();
        }}
        posterUrl={poster.response?.url}
      />
      <ExportsPanel open={exportsOpen} onOpenChange={changeExportsOpen} refreshKey={exportsKey} />
    </div>
  );
}
