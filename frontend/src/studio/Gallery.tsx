/** Library pages inside the persistent Studio shell. */
import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, Check, Clapperboard, RotateCw, Search, Video, X } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiUrl } from "@/lib/api";

import { friendlyError, getProject } from "./api";
import { inputClass, SectionHeading } from "./components";
import { ExportsPage } from "./exports";
import { useExports, useNearViewport, usePoster } from "./hooks";
import { cardSettings, filterCards, timeAgo, toDate } from "./options";
import { ProjectMenu } from "./ProjectMenu";
import { routeHash, type Route } from "./router";
import type { Card, Catalog, PreviewRequest, PreviewResponse, ProjectSummary, TemplateInfo } from "./types";
import type { Library } from "./useLibrary";

function PosterImage({ url, response, error }: { url?: string | null; response?: PreviewResponse | null; error?: unknown }) {
  const source = url || response?.url;
  const [loaded, setLoaded] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const ready = loaded === source;
  if (source && failed !== source) return <>
    <img src={apiUrl(source)} alt="" width={response?.width} height={response?.height} loading="lazy" decoding="async" className="studio-poster-image" data-ready={ready} onLoad={() => setLoaded(source)} onError={() => setFailed(source)} />
    <img src={apiUrl(source)} alt="" aria-hidden loading="lazy" decoding="async" className="studio-poster-ambient" data-ready={ready} />
    {!ready && <span className="studio-shimmer absolute inset-0" aria-hidden />}
  </>;
  if (error || source && failed === source) return <span className="studio-poster-unavailable"><Clapperboard aria-hidden /><span>Preview unavailable</span></span>;
  return <span className="studio-shimmer absolute inset-0" aria-hidden />;
}

function Poster({ card, template }: { card: Card; template: TemplateInfo | undefined }) {
  const ref = useRef<HTMLDivElement>(null);
  const near = useNearViewport(ref);
  const request = near ? { template: card.template, params: card.params, settings: cardSettings(card, template), mode: "poster" as const } : null;
  const { response, error } = usePoster(request);
  return <div ref={ref} className="studio-poster-well"><PosterImage response={response} error={error} /></div>;
}

function CardTile({ card, template }: { card: Card; template: TemplateInfo | undefined }) {
  return <li><a href={routeHash({ kind: "new", template: card.template, preset: card.id })} className="studio-card">
    <Poster card={card} template={template} />
    <span className="studio-card-copy"><span className="studio-card-title">{card.title}</span><span className="studio-card-summary">{card.summary}</span></span>
  </a></li>;
}

function ProjectTile({ project, library, onDelete }: { project: ProjectSummary; library: Library; onDelete: (project: ProjectSummary) => void }) {
  const ref = useRef<HTMLLIElement>(null);
  const near = useNearViewport(ref);
  const [preview, setPreview] = useState<{ key: string; request?: PreviewRequest; error?: unknown } | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const title = project.title || "Untitled video";
  const projectKey = `${project.id}/${project.updated}`;
  useEffect(() => {
    if (!near || project.poster_url) return;
    let live = true;
    getProject(project.id).then(
      (full) => live && setPreview({ key: projectKey, request: { template: full.template, params: full.params, settings: full.settings, mode: "poster" } }),
      (error) => live && setPreview({ key: projectKey, error }),
    );
    return () => { live = false; };
  }, [near, project.id, project.poster_url, projectKey]);
  const current = preview?.key === projectKey ? preview : null;
  const { response, error } = usePoster(project.poster_url ? null : current?.request ?? null);
  const focusOptions = () => ref.current?.querySelector<HTMLButtonElement>('[aria-haspopup="menu"]')?.focus();
  const rename = async () => {
    if (!draft.trim()) return;
    setBusy(true);
    try { await library.rename(project.id, draft.trim()); setRenaming(false); requestAnimationFrame(focusOptions); }
    catch (error) { toast.error(friendlyError(error, "Couldn't rename that video.")); }
    finally { setBusy(false); }
  };
  const duplicate = async () => {
    setBusy(true);
    try { await library.duplicate(project.id); toast.success("Video duplicated"); }
    catch (error) { toast.error(friendlyError(error, "Couldn't duplicate that video.")); }
    finally { setBusy(false); }
  };
  return <li ref={ref} className="studio-project-tile" aria-busy={busy}>
    <a href={routeHash({ kind: "project", id: project.id })} className="studio-card" tabIndex={renaming ? -1 : undefined}>
      <span className="studio-poster-well"><PosterImage url={project.poster_url} response={response} error={current?.error || error} /></span>
      <span className="studio-card-copy" style={renaming ? { visibility: "hidden" } : undefined}>
        <span className="studio-card-title truncate">{title}</span><span className="studio-card-meta">Edited {timeAgo(project.updated)}</span>
      </span>
    </a>
    {!renaming && <ProjectMenu title={title} disabled={busy} onRename={() => { setDraft(title); setRenaming(true); }} onDuplicate={duplicate} onDelete={() => onDelete(project)} />}
    {renaming && <form className="studio-project-rename" aria-label={`Rename ${title}`} onSubmit={(event) => { event.preventDefault(); void rename(); }} onKeyDown={(event) => {
      if (event.key === "Escape" && !busy) { event.preventDefault(); setRenaming(false); requestAnimationFrame(focusOptions); }
    }}>
      <input ref={(node) => { if (node && document.activeElement !== node) { node.focus(); node.select(); } }} value={draft} onChange={(event) => setDraft(event.target.value)} aria-label="Video name" className={inputClass} maxLength={80} disabled={busy} />
      <button type="submit" className="studio-shell-icon" aria-label="Save name" disabled={busy || !draft.trim()}><Check /></button>
      <button type="button" className="studio-shell-icon" aria-label="Cancel rename" disabled={busy} onClick={() => { setRenaming(false); requestAnimationFrame(focusOptions); }}><X /></button>
    </form>}
  </li>;
}

function YourVideos({ library, home = false }: { library: Library; home?: boolean }) {
  const [confirm, setConfirm] = useState<ProjectSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [sort, setSort] = useState("edited");
  const { projects, error, retry } = library;
  const sorted = [...(projects ?? [])].sort((a, b) => !home && sort === "name" ? (a.title || "Untitled video").localeCompare(b.title || "Untitled video") : (toDate(b.updated)?.getTime() ?? 0) - (toDate(a.updated)?.getTime() ?? 0));
  if (home && projects?.length === 0 && !error) return <p className="studio-welcome">Welcome to your studio. Pick a template below to make your first video.</p>;
  const remove = async () => {
    if (!confirm) return;
    setBusy(true);
    try { await library.remove(confirm.id); setConfirm(null); }
    catch (error) { toast.error(friendlyError(error, "Couldn't delete that video.")); }
    finally { setBusy(false); }
  };
  return <section aria-labelledby="your-videos" className="studio-gallery-section">
    <SectionHeading id="your-videos" action={home ? <a href="#/videos" className="studio-see-all">See all <ArrowRight aria-hidden /></a> : <div className="studio-video-sort"><label htmlFor="video-sort">Sort by</label><Select value={sort} onValueChange={setSort}><SelectTrigger id="video-sort" aria-label="Sort videos"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="edited">Last edited</SelectItem><SelectItem value="name">Name</SelectItem></SelectContent></Select></div>}>
      {home ? "Continue editing" : projects ? `${projects.length} ${projects.length === 1 ? "video" : "videos"}` : "Your library"}
    </SectionHeading>
    {!!error && <div role="alert" className="studio-inline-error"><span>Couldn't load your videos. {friendlyError(error)}</span><Button size="sm" variant="secondary" onClick={retry}><RotateCw /> Try again</Button></div>}
    {projects === null && !error ? <div role="status" aria-label="Loading your videos"><ul className="studio-template-grid">{[0, 1, 2, 3].map((key) => <CardSkeleton key={key} />)}</ul></div> : projects?.length === 0 && !error ? <div className="studio-empty-state">
      <Video aria-hidden /><h2>No videos yet</h2><p>Pick a template to make your first one.</p><Button asChild size="md"><a href="#/templates">Browse templates <ArrowRight /></a></Button>
    </div> : <ul className={`studio-template-grid${home ? " studio-home-row" : ""}`}>{(home ? sorted.slice(0, 4) : sorted).map((project) => <ProjectTile key={project.id} project={project} library={library} onDelete={setConfirm} />)}</ul>}
    <Dialog open={!!confirm} onOpenChange={(open) => { if (!open && !busy) setConfirm(null); }}>
      <DialogContent onFocusFallback={() => document.getElementById("studio-main")?.focus()} onEscapeKeyDown={(event) => { if (busy) event.preventDefault(); }} onPointerDownOutside={(event) => { if (busy) event.preventDefault(); }}>
        <DialogHeader><DialogTitle>Delete "{confirm?.title || "Untitled video"}"?</DialogTitle><DialogDescription>This removes the video from Your videos. Files you've already downloaded are kept.</DialogDescription></DialogHeader>
        <DialogFooter><Button variant="ghost" size="md" onClick={() => setConfirm(null)} disabled={busy}>Keep it</Button><Button variant="danger" size="md" onClick={remove} disabled={busy}>Delete</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  </section>;
}

export function Gallery({ catalog, route, library, exports }: { catalog: Catalog; route: Route; library: Library; exports: ReturnType<typeof useExports> }) {
  const templates = useMemo(() => new Map(catalog.templates.map((template) => [template.id, template])), [catalog.templates]);
  if (route.kind === "videos") return <YourVideos library={library} />;
  if (route.kind === "exports") return <ExportsPage exports={exports} />;
  const home = route.kind === "gallery";
  const category = route.kind === "templates" ? route.category : undefined;
  const query = route.kind === "templates" ? route.query ?? "" : "";
  const sections = catalog.sections.filter((section) => !category || section.id === category).map((section) => ({ ...section, cards: filterCards(section.cards, query, templates) })).filter((section) => section.cards.length);
  const cards = sections.flatMap((section) => section.cards);
  return <div className="studio-gallery-content">
    {home ? <>
      <header className="studio-gallery-hero"><h1>What are you making?</h1><p>Pick a starting point. You can change every word, color and format, then export a video.</p></header>
      <YourVideos library={library} home />
      <div className="studio-template-intro"><h2>Start from a template</h2></div>
      {sections.map((section) => <section key={section.id} aria-labelledby={`section-${section.id}`} className="studio-gallery-section">
        <SectionHeading id={`section-${section.id}`} action={<a href={routeHash({ kind: "templates", category: section.id })} className="studio-see-all" aria-label={`See all ${section.title}`}>See all <ArrowRight aria-hidden /></a>}>{section.title}</SectionHeading>
        <ul className="studio-template-grid studio-home-row">{section.cards.slice(0, 4).map((card) => <CardTile key={`${card.template}/${card.id}`} card={card} template={templates.get(card.template)} />)}</ul>
      </section>)}
    </> : cards.length === 0 ? <div className="studio-empty-state" role="status"><Search aria-hidden /><p>{query ? `Nothing matches "${query}". Try another word.` : "No designs in this category yet."}</p><Button asChild variant="secondary" size="md"><a href="#/templates">Show all designs</a></Button></div> : <section className="studio-gallery-section" aria-label="Templates">
      <p className="studio-results-count" role="status">{cards.length} {cards.length === 1 ? "template" : "templates"}{query && <> matching “{query}”</>}</p>
      <ul className="studio-template-grid">{cards.map((card) => <CardTile key={`${card.template}/${card.id}`} card={card} template={templates.get(card.template)} />)}</ul>
    </section>}
  </div>;
}

function CardSkeleton() {
  return <li aria-hidden><div className="studio-poster-well"><span className="studio-shimmer absolute inset-0" /></div><div className="studio-card-copy"><span className="studio-skeleton-line studio-shimmer" /><span className="studio-skeleton-line studio-shimmer" /></div></li>;
}

export function GalleryLoading() {
  return <div className="studio-gallery-section" role="status" aria-label="Loading designs…" aria-busy="true"><span className="studio-skeleton-line studio-shimmer" aria-hidden /><ul className="studio-template-grid">{[0, 1, 2, 3].map((key) => <CardSkeleton key={key} />)}</ul></div>;
}
