/** The start page: "What are you making?" with a card per ready-made design. */
import { useEffect, useMemo, useRef, useState } from "react";
import { Clapperboard, Code2, FolderDown, Plug, RotateCw, Search, Trash2, X } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { apiUrl } from "@/lib/api";
import { cn } from "@/lib/utils";

import { deleteProject, friendlyError, listProjects } from "./api";
import { inputClass, SectionHeading } from "./components";
import { ConnectionDialog } from "./ConnectionDialog";
import { ExportRow, ExportsPanel } from "./exports";
import { useExports, useNearViewport, usePoster } from "./hooks";
import { cardSettings, filterCards, timeAgo } from "./options";
import { routeHash } from "./router";
import type { Card, Catalog, ProjectSummary, TemplateInfo } from "./types";

function Poster({ card, template }: { card: Card; template: TemplateInfo | undefined }) {
  const ref = useRef<HTMLDivElement>(null);
  const near = useNearViewport(ref);
  const request = near ? { template: card.template, params: card.params, settings: cardSettings(card, template), mode: "poster" as const } : null;
  const { response, error } = usePoster(request);
  return (
    <div ref={ref} className="relative aspect-video overflow-hidden bg-raised">
      {response ? (
        <img src={apiUrl(response.url)} alt="" className="absolute inset-0 size-full object-contain transition-transform duration-300 group-hover:scale-[1.03]" />
      ) : error ? (
        <div className="absolute inset-0 flex items-center justify-center text-fg-subtle">
          <Clapperboard aria-hidden className="size-8" />
        </div>
      ) : (
        <div className="studio-shimmer absolute inset-0" aria-hidden />
      )}
    </div>
  );
}

function CardTile({ card, template }: { card: Card; template: TemplateInfo | undefined }) {
  return (
    <li>
      <a
        href={routeHash({ kind: "new", template: card.template, preset: card.id })}
        className="group flex h-full flex-col overflow-hidden rounded-xl border border-line bg-surface transition-colors hover:border-line-strong hover:bg-raised/40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        <Poster card={card} template={template} />
        <span className="flex flex-col gap-0.5 px-3 pb-3 pt-2.5">
          <span className="text-sm font-semibold text-fg">{card.title}</span>
          <span className="text-xs leading-relaxed text-fg-muted">{card.summary}</span>
        </span>
      </a>
    </li>
  );
}

function ProjectTile({ project, onDelete }: { project: ProjectSummary; onDelete: (project: ProjectSummary) => void }) {
  return (
    <li className="group relative w-56 shrink-0">
      <a
        href={routeHash({ kind: "project", id: project.id })}
        className="flex flex-col overflow-hidden rounded-xl border border-line bg-surface transition-colors hover:border-line-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        <span className="relative block aspect-video bg-raised">
          {project.poster_url ? (
            <img src={apiUrl(project.poster_url)} alt="" className="absolute inset-0 size-full object-contain" />
          ) : (
            <span className="absolute inset-0 flex items-center justify-center text-fg-subtle">
              <Clapperboard aria-hidden className="size-7" />
            </span>
          )}
        </span>
        <span className="flex flex-col px-3 py-2">
          <span className="truncate text-[13px] font-medium text-fg">{project.title || "Untitled video"}</span>
          <span className="text-xs text-fg-subtle">Edited {timeAgo(project.updated)}</span>
        </span>
      </a>
      <button
        type="button"
        onClick={() => onDelete(project)}
        aria-label={`Delete ${project.title || "untitled video"}`}
        className="absolute right-1.5 top-1.5 flex size-7 items-center justify-center rounded-md bg-canvas/80 text-fg-muted opacity-0 transition-opacity hover:text-danger focus-visible:opacity-100 group-hover:opacity-100"
      >
        <Trash2 className="size-3.5" />
      </button>
    </li>
  );
}

function YourVideos() {
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [confirm, setConfirm] = useState<ProjectSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    listProjects().then(
      (list) => {
        if (!live) return;
        setProjects(list);
        setError(null);
      },
      (error) => live && setError(error),
    );
    return () => {
      live = false;
    };
  }, [attempt]);
  if (!projects?.length && !error) return null;
  const remove = async () => {
    if (!confirm) return;
    setBusy(true);
    try {
      await deleteProject(confirm.id);
      setProjects((list) => (list ?? []).filter((item) => item.id !== confirm.id));
      setConfirm(null);
    } catch (error) {
      toast.error(friendlyError(error, "Couldn't delete that video."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section aria-labelledby="your-videos" className="flex flex-col gap-3">
      <SectionHeading id="your-videos">Your videos</SectionHeading>
      {!!error && <div role="alert" className="flex flex-wrap items-center gap-3 text-sm text-danger">
        <span>Couldn't load your videos. {friendlyError(error)}</span>
        <Button size="sm" variant="secondary" onClick={() => setAttempt((value) => value + 1)}><RotateCw /> Try again</Button>
      </div>}
      <ul className="-mx-1 flex gap-3 overflow-x-auto px-1 pb-2">
        {projects?.map((project) => (
          <ProjectTile key={project.id} project={project} onDelete={setConfirm} />
        ))}
      </ul>
      <Dialog open={!!confirm} onOpenChange={(open) => !open && setConfirm(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete "{confirm?.title || "Untitled video"}"?</DialogTitle>
            <DialogDescription>This removes the video from Your videos. Files you've already downloaded are kept.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" size="md" onClick={() => setConfirm(null)}>
              Keep it
            </Button>
            <Button variant="danger" size="md" onClick={remove} disabled={busy}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}

function RecentExports() {
  const [panel, setPanel] = useState(false);
  const { jobs, error, cancel, retry } = useExports(true);
  if (!jobs?.length && !error) return null;
  return (
    <section aria-labelledby="recent-exports" className="flex flex-col gap-3">
      <SectionHeading
        id="recent-exports"
        action={
          <Button variant="ghost" size="sm" onClick={() => setPanel(true)}>
            <FolderDown /> See all
          </Button>
        }
      >
        Recent exports
      </SectionHeading>
      {!!error && <div role="alert" className="flex flex-wrap items-center gap-3 text-sm text-danger">
        <span>Couldn't refresh exports. {friendlyError(error)}</span>
        <Button size="sm" variant="secondary" onClick={retry}><RotateCw /> Try again</Button>
      </div>}
      <ul className="grid gap-2 md:grid-cols-2">
        {jobs?.slice(0, 4).map((job) => (
          <ExportRow key={job.id} job={job} onCancel={cancel} />
        ))}
      </ul>
      <ExportsPanel open={panel} onOpenChange={setPanel} />
    </section>
  );
}

export function Gallery({ catalog }: { catalog: Catalog }) {
  const [query, setQuery] = useState("");
  const [connectionOpen, setConnectionOpen] = useState(false);
  const templates = useMemo(() => new Map(catalog.templates.map((template) => [template.id, template])), [catalog.templates]);
  const sections = useMemo(
    () => catalog.sections.map((section) => ({ ...section, cards: filterCards(section.cards, query, templates) })).filter((section) => section.cards.length),
    [catalog.sections, query, templates],
  );
  useEffect(() => {
    document.title = "Studio";
  }, []);

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-10 px-4 pb-16 pt-8 sm:px-6 lg:px-8 lg:pt-12">
      <header className="flex flex-col gap-5">
        <div className="flex items-start justify-between gap-4">
          <div className="flex flex-col gap-2">
            <h1 className="text-2xl font-semibold tracking-tight text-fg sm:text-3xl">What are you making?</h1>
            <p className="max-w-xl text-sm leading-relaxed text-fg-muted">
              Pick a starting point. You can change every word, color and format, then export a video.
            </p>
          </div>
          <div className="flex shrink-0 flex-col items-end gap-2 sm:flex-row sm:items-center">
            <Button variant="secondary" size="sm" onClick={() => setConnectionOpen(true)}><Plug /> Connect to AI</Button>
            <a
            href={routeHash({ kind: "author" })}
            className="flex shrink-0 items-center gap-1.5 rounded-md px-2 py-1 text-xs text-fg-subtle hover:bg-raised hover:text-fg-muted"
          >
            <Code2 className="size-3.5" /> Author mode
            </a>
          </div>
        </div>
        <div className="relative max-w-md">
          <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-fg-subtle" />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search: sale, timer, birthday…"
            aria-label="Search designs"
            className={cn(inputClass, "h-10 pl-9 pr-9")}
          />
          {query && (
            <button
              type="button"
              onClick={() => setQuery("")}
              aria-label="Clear search"
              className="absolute right-2 top-1/2 flex size-6 -translate-y-1/2 items-center justify-center rounded text-fg-subtle hover:text-fg"
            >
              <X className="size-3.5" />
            </button>
          )}
        </div>
      </header>

      {!query && <YourVideos />}
      {!query && <RecentExports />}
      {connectionOpen && <ConnectionDialog onClose={() => setConnectionOpen(false)} />}

      {sections.length === 0 ? (
        <p className="py-10 text-center text-sm text-fg-muted">Nothing matches "{query}". Try another word.</p>
      ) : (
        sections.map((section) => (
          <section key={section.id} aria-labelledby={`section-${section.id}`} className="flex flex-col gap-3">
            <SectionHeading id={`section-${section.id}`}>{section.title}</SectionHeading>
            <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {section.cards.map((card) => (
                <CardTile key={`${card.template}/${card.id}`} card={card} template={templates.get(card.template)} />
              ))}
            </ul>
          </section>
        ))
      )}
    </div>
  );
}
