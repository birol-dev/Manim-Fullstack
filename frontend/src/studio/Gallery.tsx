/** Library pages inside the persistent Studio shell. */
import { useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { ArrowRight, Check, Clapperboard, Heart, LayoutGrid, RotateCw, Video, X } from "lucide-react";
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
import { readBrandName, readFavouriteDesigns, readPreference, toggleFavouriteDesign, writePreference } from "./preferences";
import { OpenProjectButton } from "./Portable";
import { dragHasFiles, usePortableOpener } from "./portableFile";
import { ProjectMenu } from "./ProjectMenu";
import { navigate, routeHash, type Route } from "./router";
import { useSetupStatus } from "./setup";
import type { Aspect, Card, Catalog, ExportJob, PreviewRequest, PreviewResponse, ProjectSummary, TemplateInfo } from "./types";
import type { Library } from "./useLibrary";
import { useCardPeek } from "./useCardPeek";
import "./home.css";

const ASPECT_RATIO: Record<Aspect, string> = { "16:9": "16 / 9", "9:16": "9 / 16", "1:1": "1 / 1", "4:5": "4 / 5" };

function PosterImage({ url, response, error, peek, priority = false, onUnavailable }: {
  url?: string | null;
  response?: Pick<PreviewResponse, "url" | "width" | "height"> | null;
  error?: unknown;
  peek?: ReactNode;
  priority?: boolean;
  onUnavailable?: () => void;
}) {
  const source = url || response?.url;
  const [loaded, setLoaded] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const ready = loaded === source;
  if (source && failed !== source) return <>
    <span className="studio-poster-artwork">
      <img src={apiUrl(source)} alt="" width={response?.width} height={response?.height} loading={priority ? "eager" : "lazy"} fetchPriority={priority ? "high" : undefined} decoding="async" className="studio-poster-image" data-ready={ready} onLoad={() => setLoaded(source)} onError={() => { setFailed(source); onUnavailable?.(); }} />
      {peek}
    </span>
    <img src={apiUrl(source)} alt="" aria-hidden loading="lazy" decoding="async" className="studio-poster-ambient" data-ready={ready} />
    {!ready && <span className="studio-shimmer absolute inset-0" aria-hidden />}
  </>;
  if (error || source && failed === source) return <span className="studio-poster-unavailable"><Clapperboard aria-hidden /><span>Preview unavailable</span></span>;
  return <span className="studio-shimmer absolute inset-0" aria-hidden />;
}

function Poster({ card, template, peek, aspect, priority = false }: { card: Card; template: TemplateInfo | undefined; peek: ReactNode; aspect?: Aspect; priority?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const near = useNearViewport(ref);
  const [failedAsset, setFailedAsset] = useState<string | null>(null);
  const settings = { ...cardSettings(card, template), ...(aspect ? { aspect } : {}) };
  const asset = card.posters?.[settings.aspect ?? template?.default_aspect ?? "16:9"];
  const baked = asset && asset.url !== failedAsset ? asset : null;
  const request = !baked && near ? { template: card.template, params: card.params, settings, mode: "poster" as const } : null;
  const { response, error } = usePoster(request);
  return <div ref={ref} className="studio-poster-well" style={aspect ? { aspectRatio: ASPECT_RATIO[aspect] } : undefined}><PosterImage response={baked ?? response} error={error} peek={peek} priority={priority} onUnavailable={baked ? () => setFailedAsset(baked.url) : undefined} /></div>;
}

const designKey = (card: Card) => `${card.template}/${card.id}`;

function CardTile({ card, template, className, favourite, onFavourite }: {
  card: Card;
  template: TemplateInfo | undefined;
  className?: string;
  favourite?: boolean;
  onFavourite?: (card: Card) => void;
}) {
  const { video, visible, onCanPlay, onError, cardEvents } = useCardPeek(card.peek_url);
  return <li className={className}><a href={routeHash({ kind: "new", template: card.template, preset: card.id })} className="studio-card" {...cardEvents}>
    <Poster card={card} template={template} peek={card.peek_url && <video ref={video} className="studio-card-peek" data-visible={visible} preload="none" muted playsInline aria-hidden="true" tabIndex={-1} onCanPlay={onCanPlay} onError={onError} />} />
    <span className="studio-card-copy"><span className="studio-card-title">{card.title}</span><span className="studio-card-summary">{card.summary}</span></span>
  </a>
    {onFavourite && <button
      type="button"
      className="studio-card-favourite"
      aria-pressed={!!favourite}
      aria-label={favourite ? `Remove ${card.title} from favourites` : `Add ${card.title} to favourites`}
      onClick={() => onFavourite(card)}
    ><Heart aria-hidden fill={favourite ? "currentColor" : "none"} /></button>}
  </li>;
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

function ProjectTiles({ projects, library, home = false }: { projects: ProjectSummary[]; library: Library; home?: boolean }) {
  const [confirm, setConfirm] = useState<ProjectSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const remove = async () => {
    if (!confirm) return;
    setBusy(true);
    try { await library.remove(confirm.id); setConfirm(null); }
    catch (error) { toast.error(friendlyError(error, "Couldn't delete that video.")); }
    finally { setBusy(false); }
  };
  return <>
    <ul className={`studio-template-grid${home ? " studio-home-row" : ""}`}>{projects.map((project) => <ProjectTile key={project.id} project={project} library={library} onDelete={setConfirm} />)}</ul>
    <Dialog open={!!confirm} onOpenChange={(open) => { if (!open && !busy) setConfirm(null); }}>
      <DialogContent onFocusFallback={() => document.getElementById("studio-main")?.focus()} onEscapeKeyDown={(event) => { if (busy) event.preventDefault(); }} onPointerDownOutside={(event) => { if (busy) event.preventDefault(); }}>
        <DialogHeader><DialogTitle>Delete "{confirm?.title || "Untitled video"}"?</DialogTitle><DialogDescription>This removes the video from Your videos. Files you've already downloaded are kept.</DialogDescription></DialogHeader>
        <DialogFooter><Button variant="ghost" size="md" onClick={() => setConfirm(null)} disabled={busy}>Keep it</Button><Button variant="danger" size="md" onClick={remove} disabled={busy}>Delete</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  </>;
}

/** One card from each category, so the hero shows a spread of real work. */
function heroPicks(catalog: Catalog): Array<{ card: Card; template: TemplateInfo | undefined; aspect: Aspect }> {
  const pools = catalog.sections.map((section) => section.cards).filter((cards) => cards.length > 0);
  const picks: Card[] = [];
  for (let round = 0; round < 4 && picks.length < 3; round += 1) {
    for (const pool of pools) {
      const card = pool[round];
      if (card && !picks.some((picked) => picked.template === card.template && picked.id === card.id)) picks.push(card);
      if (picks.length === 3) break;
    }
  }
  const templates = new Map(catalog.templates.map((template) => [template.id, template]));
  return picks.map((card, index) => {
    const template = templates.get(card.template);
    const wanted: Aspect = index === 1 ? "9:16" : "16:9";
    const aspect = template?.aspects.includes(wanted) ? wanted : template?.default_aspect ?? wanted;
    return { card, template, aspect };
  });
}

const HERO_TILTS = [-4, 3, -2];

function HomeHero({ catalog }: { catalog: Catalog }) {
  const frames = useMemo(() => heroPicks(catalog), [catalog]);
  const brandName = readBrandName();
  return <section className="studio-home-hero" aria-labelledby="studio-home-title">
    <div className="studio-home-hero-copy">
      {brandName && <p className="studio-home-greeting">Welcome, {brandName}</p>}
      <h1 id="studio-home-title" className="studio-display studio-home-headline">
        <span className="studio-display-fade">What are you</span>{" "}
        <em className="studio-home-special">making?</em>
      </h1>
      <p className="studio-home-promise">Pick a template, change the words, and export a video. Everything is ready to go.</p>
      <a href="#/templates" className="studio-home-cta">Browse templates <ArrowRight aria-hidden /></a>
    </div>
    {frames.length > 0 && <div className="studio-home-hero-media" aria-hidden="true">
      {frames.map(({ card, template, aspect }, index) => <figure
        key={`${card.template}/${card.id}`}
        className={`studio-home-frame studio-home-frame-${index}`}
        style={{ "--frame-tilt": `${HERO_TILTS[index] ?? 0}deg` } as CSSProperties}
      >
        <Poster card={card} template={template} aspect={aspect} peek={null} priority />
      </figure>)}
    </div>}
  </section>;
}

/** Four small steps, hidden once completed or dismissed. */
function SetupTray({ projects, exports }: { projects: ProjectSummary[] | null; exports: ExportJob[] | null }) {
  const { status } = useSetupStatus();
  const [dismissed, setDismissed] = useState(() => readPreference("setup_dismissed") === true);
  const brandName = readBrandName();
  const steps = [
    { id: "video", title: "Make your first video", line: "Pick a template and make it yours.", done: (projects?.length ?? 0) > 0, href: "#/templates" },
    { id: "export", title: "Export a video", line: "Turn it into a file you can share.", done: exports?.some((job) => job.status === "done") ?? false, href: "#/exports" },
    { id: "ai", title: "Connect your AI", line: "Let your assistant make videos with you.", done: status?.ai_apps.some((app) => app.connected) ?? false, href: "#/settings/ai" },
    { id: "name", title: "Tell us your name", line: "So we know what to call you.", done: !!brandName, href: "#/settings/profile" },
  ];
  const done = steps.filter((step) => step.done).length;
  if (dismissed || done === steps.length) return null;
  const next = steps.find((step) => !step.done)?.id;
  return <section className="studio-home-setup" aria-labelledby="studio-home-setup-title">
    <div className="studio-home-setup-head">
      <h2 id="studio-home-setup-title">Finish your setup — {done}/4</h2>
      <button type="button" className="studio-shell-icon studio-home-setup-close" aria-label="Dismiss setup" title="Dismiss setup" onClick={() => {
        writePreference("setup_dismissed", true);
        setDismissed(true);
        document.getElementById("studio-main")?.focus({ preventScroll: true });
      }}><X aria-hidden /></button>
    </div>
    <ul className="studio-home-setup-grid">
      {steps.map((step, index) => <li key={step.id}>
        <a href={step.href} className="studio-home-setup-card" data-done={step.done ? "true" : undefined} data-next={step.id === next ? "true" : undefined}>
          <span className="studio-home-setup-mark" aria-hidden>{step.done ? <Check /> : index + 1}</span>
          <span className="studio-home-setup-copy">
            <span className="studio-home-setup-title">{step.done && <span className="sr-only">Done: </span>}{step.title}</span>
            <span className="studio-home-setup-line">{step.line}</span>
          </span>
        </a>
      </li>)}
    </ul>
  </section>;
}

/** A row of designs in the quiet gallery style: a heading, then cards. */
function DesignRow({ id, title, cards, templates, favourites, onFavourite }: {
  id: string;
  title: string;
  cards: Card[];
  templates: Map<string, TemplateInfo>;
  favourites: Set<string>;
  onFavourite: (card: Card) => void;
}) {
  return <section className="studio-gallery-section" aria-labelledby={id}>
    <SectionHeading id={id}>{title}</SectionHeading>
    <ul className="studio-template-grid studio-home-row">
      {cards.map((card) => <CardTile key={designKey(card)} card={card} template={templates.get(card.template)} favourite={favourites.has(designKey(card))} onFavourite={onFavourite} />)}
    </ul>
  </section>;
}

function Home({ catalog, library, exports, favourites, favouriteSet, onFavourite }: {
  catalog: Catalog;
  library: Library;
  exports: ReturnType<typeof useExports>;
  favourites: string[];
  favouriteSet: Set<string>;
  onFavourite: (card: Card) => void;
}) {
  const templates = useMemo(() => new Map(catalog.templates.map((template) => [template.id, template])), [catalog.templates]);
  const chapters = catalog.sections.filter((section) => section.cards.length > 0);
  const jobs = Array.isArray(exports?.jobs) ? exports.jobs : null;
  const designs = useMemo(() => {
    const byKey = new Map<string, Card>();
    const firstByTemplate = new Map<string, Card>();
    for (const section of catalog.sections) for (const card of section.cards) {
      byKey.set(designKey(card), card);
      if (!firstByTemplate.has(card.template)) firstByTemplate.set(card.template, card);
    }
    return { byKey, firstByTemplate };
  }, [catalog.sections]);
  const favouriteCards = favourites.flatMap((key) => {
    const card = designs.byKey.get(key);
    return card ? [card] : [];
  });
  // One card per design the person worked on lately, newest first.
  const recentCards = useMemo(() => {
    const seen = new Set<string>();
    const picked: Card[] = [];
    const projects = [...(library.projects ?? [])]
      .sort((a, b) => (toDate(b.updated)?.getTime() ?? 0) - (toDate(a.updated)?.getTime() ?? 0));
    for (const project of projects) {
      const card = designs.firstByTemplate.get(project.template);
      if (!card || seen.has(project.template)) continue;
      seen.add(project.template);
      picked.push(card);
      if (picked.length === 4) break;
    }
    return picked;
  }, [designs, library.projects]);
  return <div className="studio-home">
    <HomeHero catalog={catalog} />
    <SetupTray projects={library.projects} exports={jobs} />
    <YourVideos library={library} home />
    {favouriteCards.length > 0 && <DesignRow id="studio-home-favourites" title="Your favourites" cards={favouriteCards} templates={templates} favourites={favouriteSet} onFavourite={onFavourite} />}
    {recentCards.length >= 2 && <DesignRow id="studio-home-recent-designs" title="Recently used" cards={recentCards} templates={templates} favourites={favouriteSet} onFavourite={onFavourite} />}
    {chapters.length > 0 && <div className="studio-home-chapters">
      {chapters.map((section, index) => <section key={section.id} className="studio-home-chapter" aria-labelledby={`home-section-${section.id}`}>
        <div className="studio-home-chapter-head">
          <div className="studio-index-line">
            <span className="studio-home-chapter-number" aria-hidden>{String(index + 1).padStart(2, "0")}</span>
            <h2 id={`home-section-${section.id}`} className="studio-home-chapter-title">{section.title}</h2>
          </div>
          <a className="studio-see-all" href={routeHash({ kind: "templates", category: section.id })}>See all {section.cards.length} <ArrowRight aria-hidden /></a>
        </div>
        <ul className="studio-home-zigzag">
          {section.cards.slice(0, 4).map((card, cardIndex) => <CardTile key={designKey(card)} card={card} template={templates.get(card.template)} className={`studio-home-zig-${cardIndex}`} favourite={favouriteSet.has(designKey(card))} onFavourite={onFavourite} />)}
        </ul>
      </section>)}
    </div>}
    <section className="studio-chapter-dark studio-home-ai" aria-labelledby="studio-home-ai-title">
      <h2 id="studio-home-ai-title" className="studio-display studio-home-ai-title">
        <span className="studio-display-fade">Let your AI assistant</span>{" "}
        <em className="studio-home-special">make</em> the video.
      </h2>
      <p className="studio-home-ai-line">Claude, Cursor, VS Code, Windsurf, Codex and Gemini can make videos with you. Connect the one you use.</p>
      <Button asChild size="md"><a href="#/settings/ai">Connect your AI <ArrowRight aria-hidden /></a></Button>
    </section>
  </div>;
}

function YourVideos({ library, home = false }: { library: Library; home?: boolean }) {
  const [sort, setSort] = useState("edited");
  const [dragging, setDragging] = useState(false);
  const openFile = usePortableOpener((result) => {
    if (result.notes?.length) toast(result.notes.join(" "));
    navigate({ kind: "project", id: result.project.id });
  });
  const { projects, error, retry } = library;
  const sorted = [...(projects ?? [])].sort((a, b) => !home && sort === "name" ? (a.title || "Untitled video").localeCompare(b.title || "Untitled video") : (toDate(b.updated)?.getTime() ?? 0) - (toDate(a.updated)?.getTime() ?? 0));
  const errorBanner = !!error && <div role="alert" className="studio-inline-error"><span>Couldn't load your videos. {friendlyError(error)}</span><Button size="sm" variant="secondary" onClick={retry}><RotateCw /> Try again</Button></div>;
  if (home) {
    if (!error && (!projects || projects.length === 0)) return null;
    return <section aria-labelledby="studio-home-recent" className="studio-gallery-section">
      <SectionHeading id="studio-home-recent" action={<a href="#/videos" className="studio-see-all">See all <ArrowRight aria-hidden /></a>}>Continue editing</SectionHeading>
      {errorBanner}
      {projects && projects.length > 0 && <ProjectTiles projects={sorted.slice(0, 4)} library={library} home />}
    </section>;
  }
  return <section aria-label="Video library" className="studio-videos-page" data-dragging={dragging || undefined}
    onDragOver={(event) => {
      if (!dragHasFiles(event)) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = "copy";
      setDragging(true);
    }}
    onDragLeave={(event) => {
      if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false);
    }}
    onDrop={(event) => {
      event.preventDefault();
      setDragging(false);
      void openFile.open(event.dataTransfer?.files?.[0]);
    }}>
    <div className="studio-videos-toolbar">
      <p className="studio-videos-count">{projects ? `${projects.length} ${projects.length === 1 ? "video" : "videos"}` : "Your library"}</p>
      <div className="studio-videos-tools">
        <OpenProjectButton busy={openFile.busy} onPick={(file: File) => void openFile.open(file)} />
        <div className="studio-video-sort"><label htmlFor="video-sort">Sort by</label><Select value={sort} onValueChange={setSort}><SelectTrigger id="video-sort" aria-label="Sort videos"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="edited">Last edited</SelectItem><SelectItem value="name">Name</SelectItem></SelectContent></Select></div>
      </div>
    </div>
    {openFile.error && <div role="alert" className="studio-inline-error"><span>{openFile.error}</span></div>}
    {errorBanner}
    {dragging && <div className="studio-drop-hint" role="status">Drop the file to open it</div>}
    {projects === null && !error ? <div role="status" aria-label="Loading your videos"><ul className="studio-template-grid">{[0, 1, 2, 3].map((key) => <CardSkeleton key={key} />)}</ul></div> : projects?.length === 0 && !error ? <div className="studio-empty" role="status">
      <div className="studio-empty-picture studio-empty-video"><Video aria-hidden /></div>
      <h2>No videos yet</h2>
      <p>Pick a template, change the words, and it saves here on its own. Or open a file someone sent you.</p>
      <div className="studio-empty-actions"><Button asChild size="md"><a href="#/templates">Browse templates <ArrowRight aria-hidden /></a></Button></div>
    </div> : <ProjectTiles projects={sorted} library={library} />}
  </section>;
}

/** Every typed word must appear in the video's title. */
function matchesVideo(project: ProjectSummary, query: string) {
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return false;
  const title = (project.title || "Untitled video").toLowerCase();
  return words.every((word) => title.includes(word));
}

function EmptyTemplates({ query, category }: { query: string; category?: string }) {
  const clearSearch = routeHash({ kind: "templates", ...(category ? { category } : {}) });
  return <div className="studio-empty" role="status">
    <div className="studio-empty-picture"><LayoutGrid aria-hidden /></div>
    <h2>{query ? `Nothing matches "${query}"` : "No templates here yet"}</h2>
    <p>{query ? "Try another word, or look through everything." : "Pick another category, or see everything we have."}</p>
    <div className="studio-empty-actions">
      {query && <Button asChild size="md"><a href={clearSearch}>Clear search</a></Button>}
      <a className="studio-empty-link" href="#/templates">See all templates</a>
    </div>
  </div>;
}

interface TemplatesProps {
  catalog: Catalog;
  category?: string;
  query: string;
  templates: Map<string, TemplateInfo>;
  library: Library;
  cards: Card[];
  videos: ProjectSummary[];
  favouriteSet: Set<string>;
  onFavourite: (card: Card) => void;
}

function TemplatesPage({ catalog, category, query, templates, library, cards, videos, favouriteSet, onFavourite }: TemplatesProps) {
  const summary = query
    ? `${[
      videos.length ? `${videos.length} ${videos.length === 1 ? "video" : "videos"}` : "",
      cards.length ? `${cards.length} ${cards.length === 1 ? "template" : "templates"}` : "",
    ].filter(Boolean).join(" and ")} matching “${query}”`
    : `${cards.length} ${cards.length === 1 ? "template" : "templates"}`;
  const categoryHref = (id?: string) => routeHash({ kind: "templates", ...(id ? { category: id } : {}), ...(query ? { query } : {}) });
  return <div className="studio-templates-page">
    <nav className="studio-template-categories" aria-label="Browse templates">
      <a href={categoryHref()} className="studio-category-pill" aria-label="All templates" aria-current={!category ? "page" : undefined}>All</a>
      {catalog.sections.map((section) => <a key={section.id} href={categoryHref(section.id)} className="studio-category-pill" aria-label={`${section.title}, ${section.cards.length} ${section.cards.length === 1 ? "template" : "templates"}`} aria-current={category === section.id ? "page" : undefined}>{section.title}</a>)}
    </nav>
    <p className="studio-results-count" role="status">{summary}</p>
    {videos.length > 0 && <section className="studio-gallery-section" aria-label="Your videos">
      <SectionHeading>Your videos</SectionHeading>
      <ProjectTiles projects={videos} library={library} />
    </section>}
    {cards.length > 0 ? <section className="studio-gallery-section" aria-label="Templates">
      {videos.length > 0 && <SectionHeading>Templates</SectionHeading>}
      <ul className="studio-template-grid">{cards.map((card) => <CardTile key={designKey(card)} card={card} template={templates.get(card.template)} favourite={favouriteSet.has(designKey(card))} onFavourite={onFavourite} />)}</ul>
    </section> : videos.length === 0 ? <EmptyTemplates query={query} category={category} /> : null}
  </div>;
}

export function Gallery({ catalog, route, library, exports }: { catalog: Catalog; route: Route; library: Library; exports: ReturnType<typeof useExports> }) {
  const templates = useMemo(() => new Map(catalog.templates.map((template) => [template.id, template])), [catalog.templates]);
  const [favourites, setFavourites] = useState<string[]>(readFavouriteDesigns);
  const favouriteSet = useMemo(() => new Set(favourites), [favourites]);
  const changeFavourite = (card: Card) => setFavourites(toggleFavouriteDesign(designKey(card)));
  if (route.kind === "videos") return <YourVideos library={library} />;
  if (route.kind === "exports") return <ExportsPage exports={exports} />;
  if (route.kind === "gallery") {
    return <Home catalog={catalog} library={library} exports={exports} favourites={favourites} favouriteSet={favouriteSet} onFavourite={changeFavourite} />;
  }
  const category = route.kind === "templates" ? route.category : undefined;
  const query = route.kind === "templates" ? route.query ?? "" : "";
  const cards = filterCards(catalog.sections.filter((section) => !category || section.id === category).flatMap((section) => section.cards), query, templates);
  const videos = query ? (library.projects ?? []).filter((project) => matchesVideo(project, query)) : [];
  return <TemplatesPage catalog={catalog} category={category} query={query} templates={templates} library={library} cards={cards} videos={videos} favouriteSet={favouriteSet} onFavourite={changeFavourite} />;
}

function CardSkeleton() {
  return <li aria-hidden><div className="studio-poster-well"><span className="studio-shimmer absolute inset-0" /></div><div className="studio-card-copy"><span className="studio-skeleton-line studio-shimmer" /><span className="studio-skeleton-line studio-shimmer" /></div></li>;
}

export function GalleryLoading() {
  return <div className="studio-gallery-section" role="status" aria-label="Loading designs…" aria-busy="true"><span className="studio-skeleton-line studio-shimmer" aria-hidden /><ul className="studio-template-grid">{[0, 1, 2, 3].map((key) => <CardSkeleton key={key} />)}</ul></div>;
}
