/** The editor: a form on the left, the live preview on the right, export on top. */
import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, ArrowLeft, Check, CloudOff, Download, FolderDown, Palette, PenLine, RotateCw, Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

import { createProject, friendlyError, getProject, updateProject } from "./api";
import { Autosaver, type SaveStatus } from "./autosave";
import { FrameIcon, Segments, Spinner } from "./components";
import { fieldErrorsOf, hasErrorsUnder, matchErrors } from "./errors";
import { ExportDialog, ExportsPanel } from "./exports";
import { FormContext } from "./form/context";
import { SchemaForm } from "./form/SchemaForm";
import { useLivePreview } from "./hooks";
import { LookPanel } from "./LookPanel";
import { ASPECTS, initialSettings, isPortrait } from "./options";
import { stableKey } from "./preview";
import { PreviewPanel, type PreviewView } from "./PreviewPanel";
import type { Route } from "./router";
import { fieldPaths, fieldsOf, initialParams } from "./schemaForm";
import type { Aspect, Catalog, FieldError, Params, PreviewRequest, RenderSettings, TemplateInfo } from "./types";

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
];

interface InitialState {
  title: string;
  params: Params;
  settings: RenderSettings;
  projectId: string | null;
}

interface EditorPageProps {
  catalog: Catalog;
  route: Extract<Route, { kind: "new" } | { kind: "project" }>;
  onProjectCreated: (id: string) => void;
}

function Message({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
      <h1 className="text-lg font-semibold text-fg">{title}</h1>
      {children}
      <Button asChild variant="secondary" size="md">
        <a href="#/">
          <ArrowLeft /> Back to all designs
        </a>
      </Button>
    </div>
  );
}

/** Picks what to edit: a new video from a card, or a saved project. */
export function EditorPage({ catalog, route, onProjectCreated }: EditorPageProps) {
  // The route this editor opened with. Saving a new video renames the URL to #/project/<id>;
  // that must not reload the editor.
  const [opened] = useState(route);
  if (opened.kind === "new") {
    const template = catalog.templates.find((item) => item.id === opened.template);
    if (!template) return <Message title="This design isn't available anymore." />;
    const card = template.presets.find((item) => item.id === opened.preset);
    const initial: InitialState = {
      title: card?.title ?? template.title,
      params: initialParams(template.defaults, card?.params),
      settings: initialSettings(template, card?.settings),
      projectId: null,
    };
    return <EditorBody catalog={catalog} template={template} initial={initial} onProjectCreated={onProjectCreated} />;
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
      <Message title={missing ? "This video couldn't be found." : "Couldn't open this video."}>
        {!missing && <p className="text-sm text-fg-muted">{friendlyError(state.error)}</p>}
      </Message>
    );
  }
  return <EditorBody catalog={catalog} template={state.template} initial={state.initial} onProjectCreated={onProjectCreated} />;
}

function SaveIndicator({ status, hasProject }: { status: SaveStatus; hasProject: boolean }) {
  if (status === "pending" || status === "saving") {
    return (
      <span className="flex items-center gap-1.5 text-xs text-fg-subtle" role="status">
        <Spinner className="size-3" /> Saving…
      </span>
    );
  }
  if (status === "error") {
    return (
      <span className="flex items-center gap-1.5 text-xs text-danger" role="status">
        <CloudOff className="size-3.5" /> Not saved
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
        <span className="hidden xl:inline">{item.label}</span>
        <span className="text-fg-subtle">{item.value}</span>
      </>
    ),
  }));
  if (options.length < 2) return null;
  return <Segments value={value} options={options} onChange={onChange} aria-label="Format" size="sm" className="w-auto" />;
}

interface EditorBodyProps {
  catalog: Catalog;
  template: TemplateInfo;
  initial: InitialState;
  onProjectCreated: (id: string) => void;
}

function EditorBody({ catalog, template, initial, onProjectCreated }: EditorBodyProps) {
  const [title, setTitle] = useState(initial.title);
  const [params, setParams] = useState<Params>(initial.params);
  const [settings, setSettings] = useState<RenderSettings>(initial.settings);
  const [initialProjectId] = useState(initial.projectId);
  const [hasProject, setHasProject] = useState(!!initial.projectId);
  const [tab, setTab] = useState("content");
  const [view, setView] = useState<PreviewView>("poster");
  const [exportOpen, setExportOpen] = useState(false);
  const [exportsOpen, setExportsOpen] = useState(false);
  const [exportsKey, setExportsKey] = useState(0);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [reloading, setReloading] = useState(false);
  const [reloadError, setReloadError] = useState<string | null>(null);
  const [formVersion, setFormVersion] = useState(0);
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
  const storyboard = useLivePreview(view === "storyboard" ? { ...posterRequest, mode: "storyboard" } : null);

  // ---- Autosave ---------------------------------------------------------------------------
  const touched = useRef(false);
  const editVersion = useRef(0);
  const markTouched = () => {
    touched.current = true;
    editVersion.current += 1;
  };
  const saver = useRef<Autosaver | null>(null);
  const createdRef = useRef(onProjectCreated);
  useEffect(() => {
    createdRef.current = onProjectCreated;
  });
  useEffect(() => {
    const autosaver = new Autosaver({
      projectId: initialProjectId,
      create: (snapshot, keepalive) => createProject(snapshot, keepalive),
      update: (id, snapshot, keepalive) => updateProject(id, { title: snapshot.title, params: snapshot.params, settings: snapshot.settings }, keepalive),
      onStatus: (status, error) => {
        setSaveStatus(status);
        setSaveError(status === "error" ? friendlyError(error, "Couldn't save this video.") : null);
      },
      onCreated: (project) => {
        setHasProject(true);
        createdRef.current(project.id);
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

  const setParam = (key: string, value: unknown) => {
    markTouched();
    setParams((prev) => ({ ...prev, [key]: value }));
  };
  const patchSettings = (patch: Partial<RenderSettings>) => {
    markTouched();
    setSettings((prev) => {
      const next = { ...prev, ...patch };
      if (patch.aspect && !isPortrait(patch.aspect)) next.safe_zone = false;
      return next;
    });
  };

  const reload = async () => {
    const id = saver.current?.id;
    if (!id || saver.current?.dirty || reloading) return;
    const version = editVersion.current;
    setReloading(true);
    setReloadError(null);
    try {
      const project = await getProject(id);
      if (editVersion.current !== version || saver.current?.dirty) {
        setReloadError("Your edits were kept. Save them before reloading.");
        return;
      }
      touched.current = false;
      setTitle(project.title);
      setParams(initialParams(template.defaults, project.params));
      setSettings(initialSettings(template, project.settings));
      setExportErrors(null);
      setFormVersion((value) => value + 1);
    } catch (error) {
      setReloadError(friendlyError(error, "Couldn't reload the saved video."));
    } finally {
      setReloading(false);
    }
  };

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
  const lookBroken = hasErrorsUnder(matched.byPath, "settings");
  const formContext = useMemo(
    () => ({ locale: settings.locale, theme, errors: matched.byPath }),
    [settings.locale, theme, matched.byPath],
  );

  const length = template.length_from_params ? null : (settings.length ?? template.default_length);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-2 border-b border-line bg-surface px-3 py-2">
        <Button asChild variant="ghost" size="md" className="-ml-1">
          <a href="#/" aria-label="Back to all designs">
            <ArrowLeft />
            <span className="hidden sm:inline">All designs</span>
          </a>
        </Button>
        <div className="flex min-w-40 flex-1 items-center gap-2">
          <PenLine aria-hidden className="size-3.5 shrink-0 text-fg-subtle" />
          <input
            value={title}
            maxLength={80}
            aria-label="Video title"
            placeholder="Untitled video"
            onChange={(event) => {
              markTouched();
              setTitle(event.target.value);
            }}
            className="h-8 min-w-0 flex-1 rounded-md border border-transparent bg-transparent px-1.5 text-[15px] font-semibold text-fg hover:border-line-strong focus-visible:border-accent focus-visible:outline-none"
          />
          <SaveIndicator status={saveStatus} hasProject={hasProject} />
        </div>
        <FormatPicker aspects={template.aspects} value={settings.aspect} onChange={(aspect) => patchSettings({ aspect })} />
        {hasProject && <Button variant="ghost" size="md" onClick={reload}
          disabled={reloading || saveStatus === "pending" || saveStatus === "saving" || saveStatus === "error"}
          title="Load changes saved by your AI. Save your own edits first.">
          {reloading ? <Spinner /> : <RotateCw />} Reload saved
        </Button>}
        <Button variant="secondary" size="md" disabled={saveStatus === "saving"} onClick={() => {
          saver.current?.change({ title: title.trim() || template.title, template: template.id, params, settings });
          saver.current?.flush();
        }}>
          <Save /> {saveStatus === "error" ? "Retry save" : "Save"}
        </Button>
        <Button variant="ghost" size="md" aria-label="Exports" onClick={() => setExportsOpen(true)}>
          <FolderDown />
          <span className="hidden md:inline">Exports</span>
        </Button>
        <Button variant="primary" size="md" onClick={() => setExportOpen(true)} className="px-4">
          <Download />
          Export
        </Button>
      </header>

      {saveError && <p role="alert" className="border-b border-danger/30 bg-danger-soft px-4 py-2 text-xs text-danger">{saveError} Use Retry save to try again.</p>}
      {reloadError && <p role="alert" className="border-b border-warning/30 bg-raised px-4 py-2 text-xs text-warning">{reloadError}</p>}

      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto lg:flex-row lg:overflow-hidden">
        <aside className="flex shrink-0 flex-col border-line lg:w-[400px] lg:overflow-y-auto lg:border-r xl:w-[440px]">
          <Tabs value={tab} onValueChange={setTab} className="flex flex-col">
            <TabsList className="sticky top-0 z-10 h-11 shrink-0 gap-2 border-b border-line bg-surface px-3">
              <TabsTrigger value="content" className="text-[13px]">
                <PenLine className="size-3.5" /> Content
                {contentBroken && <span className="size-1.5 rounded-full bg-danger" aria-label="has problems" />}
              </TabsTrigger>
              <TabsTrigger value="look" className="text-[13px]">
                <Palette className="size-3.5" /> Look
                {lookBroken && <span className="size-1.5 rounded-full bg-danger" aria-label="has problems" />}
              </TabsTrigger>
            </TabsList>
            <FormContext.Provider value={formContext}>
              <TabsContent value="content" className="p-4">
                {matched.unmatched.length > 0 && (
                  <div role="alert" className="mb-4 flex gap-2 rounded-lg border border-danger/30 bg-danger-soft px-3 py-2 text-xs text-fg-muted">
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
              <TabsContent value="look" className="p-4">
                <LookPanel settings={settings} onChange={patchSettings} template={template} themes={themes} errors={matched.byPath} />
              </TabsContent>
            </FormContext.Provider>
          </Tabs>
        </aside>

        <main className={cn("order-first flex h-[45vh] min-h-[260px] shrink-0 flex-col p-4 lg:order-none lg:h-auto lg:min-h-0 lg:flex-1 lg:shrink lg:p-6")}>
          <PreviewPanel
            view={view}
            onViewChange={setView}
            poster={poster}
            storyboard={storyboard}
            aspect={settings.aspect}
            transparent={settings.background?.kind === "transparent"}
            length={length}
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
      />
      <ExportsPanel open={exportsOpen} onOpenChange={setExportsOpen} refreshKey={exportsKey} />
    </div>
  );
}
