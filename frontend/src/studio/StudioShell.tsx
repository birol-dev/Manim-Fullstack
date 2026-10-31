import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { BarChart3, ChevronRight, Code2, FolderDown, GraduationCap, Home, LayoutGrid, MapPin, Megaphone, Menu, PanelLeftClose, PanelLeftOpen, PartyPopper, Play, Plug, Repeat, Search, Settings, Timer, Trophy, Video, X } from "lucide-react";

import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Tooltip } from "@/components/ui/tooltip";

import { readCollapsed, setCollapsed as storeCollapsed } from "./appearance";
import { useExportActivity, useExports } from "./hooks";
import { timeAgo, toDate } from "./options";
import { routeHash, type Route, type useHashRoute } from "./router";
import { useUpdateStatus } from "./setup";
import type { Catalog, ProjectSummary } from "./types";
import { useLibrary, type Library } from "./useLibrary";
import "./shell.css";

type ShellRoute = Extract<Route, { kind: "gallery" | "templates" | "videos" | "exports" | "settings" }>;
type Exports = ReturnType<typeof useExports>;

interface ShellProps {
  route: ShellRoute;
  catalog: Catalog | null;
  push: ReturnType<typeof useHashRoute>["push"];
  replace: ReturnType<typeof useHashRoute>["replace"];
  children: (library: Library, exports: Exports) => ReactNode;
}

const CATEGORY_ICONS = { announce: Megaphone, celebrate: PartyPopper, timers: Timer, creator: Video, teach: GraduationCap, numbers: BarChart3, sports: Trophy, travel: MapPin, screens: Repeat };

interface Counts {
  projects: number | null;
  exports: number | null;
  activity: boolean;
  update: boolean;
}

interface PanelProps {
  route: ShellRoute;
  catalog: Catalog | null;
  query: string;
  onSearch: (value: string) => void;
  onNavigate: () => void;
  searchRef: RefObject<HTMLInputElement | null>;
  projects: ProjectSummary[] | null;
  onCollapse?: () => void;
}

/** Search, then the two things people reach for: what to make, and what they were making. */
function Panel({ route, catalog, query, onSearch, onNavigate, searchRef, projects, onCollapse }: PanelProps) {
  const [fade, setFade] = useState({ top: false, bottom: false });
  const bodyRef = useRef<HTMLElement>(null);
  const measure = useCallback(() => {
    const body = bodyRef.current;
    if (!body) return;
    const top = body.scrollTop > 2;
    const bottom = body.scrollTop + body.clientHeight < body.scrollHeight - 2;
    setFade((current) => (current.top === top && current.bottom === bottom ? current : { top, bottom }));
  }, []);
  useLayoutEffect(measure);
  useEffect(() => {
    const body = bodyRef.current;
    if (!body) return;
    const observer = new ResizeObserver(measure);
    observer.observe(body);
    return () => observer.disconnect();
  }, [measure]);
  const recents = projects === null
    ? null
    : [...projects].sort((a, b) => (toDate(b.updated)?.getTime() ?? 0) - (toDate(a.updated)?.getTime() ?? 0)).slice(0, 5);
  return <div className="studio-panel">
    <div className="studio-panel-head">
      <div className="studio-panel-search">
        <Search aria-hidden />
        <input
          ref={searchRef}
          type="search"
          value={query}
          onChange={(event) => onSearch(event.target.value)}
          placeholder="Search"
          title="Search videos and templates"
          aria-label="Search designs"
          aria-keyshortcuts="Control+k Meta+k /"
        />
        {query ? <button type="button" aria-label="Clear search" onClick={() => onSearch("")}><X /></button> : <kbd aria-hidden>Ctrl K</kbd>}
      </div>
      {onCollapse && <Tooltip content="Hide side panel" side="right">
        <button type="button" className="studio-panel-toggle" aria-label="Collapse sidebar" onClick={onCollapse}><PanelLeftClose /></button>
      </Tooltip>}
    </div>
    <nav ref={bodyRef} aria-label="Library" className="studio-panel-body" data-fade={fade.top && fade.bottom ? "both" : fade.top ? "top" : fade.bottom ? "bottom" : undefined} onScroll={measure}>
      <section className="studio-panel-section" aria-labelledby="studio-panel-create">
        <h2 id="studio-panel-create" className="studio-panel-title">Create</h2>
        {catalog ? <div className="studio-panel-list" role="group" aria-label="Template categories">
          {catalog.sections.map((section) => {
            const Icon = CATEGORY_ICONS[section.id as keyof typeof CATEGORY_ICONS] ?? LayoutGrid;
            const active = route.kind === "templates" && route.category === section.id;
            return <a key={section.id} href={routeHash({ kind: "templates", category: section.id })} className="studio-panel-link" aria-label={section.title} aria-current={active ? "page" : undefined} onClick={onNavigate}>
              <Icon aria-hidden /><span className="studio-panel-label">{section.title}</span><span className="studio-nav-count" aria-hidden>{section.cards.length}</span>
            </a>;
          })}
        </div> : <p className="studio-panel-hint" role="status">Loading designs…</p>}
      </section>
      <section className="studio-panel-section" aria-labelledby="studio-panel-recents">
        <h2 id="studio-panel-recents" className="studio-panel-title">Recents</h2>
        {recents === null ? <div className="studio-panel-skeleton" aria-hidden><span /><span /><span /></div> : recents.length === 0 ? <p className="studio-panel-hint">Your videos will appear here.</p> : <ul className="studio-panel-list">
          {recents.map((project) => <li key={project.id}><a href={routeHash({ kind: "project", id: project.id })} className="studio-panel-recent" onClick={onNavigate}>
            <span className="studio-panel-recent-title">{project.title || "Untitled video"}</span>
            {timeAgo(project.updated) && <span className="studio-panel-recent-meta">Edited {timeAgo(project.updated)}</span>}
          </a></li>)}
        </ul>}
      </section>
    </nav>
  </div>;
}

interface NavProps extends Counts {
  route: ShellRoute;
  onNavigate: () => void;
}

interface RailProps extends NavProps {
  collapsed: boolean;
  onExpand: () => void;
}

/** The permanent destinations: everything a person might want, always in the same place. */
function Rail({ route, collapsed, onNavigate, onExpand, projects, exports, activity, update }: RailProps) {
  const link = (target: Route, label: string, icon: ReactNode, active: boolean, count?: number | null, dot = false, updateDot = false) => {
    const description = [dot ? "An export is running or ready to open." : "", updateDot ? "An update is ready to install." : ""]
      .filter(Boolean).join(" ") || undefined;
    return <Tooltip key={label} content={label} side="right">
      <a href={routeHash(target)} className="studio-rail-link" aria-label={label} aria-current={active ? "page" : undefined} aria-description={description} onClick={onNavigate}>
        <span className="studio-rail-icon">
          {icon}
          {count != null && <span className="studio-nav-count" aria-hidden>{count}</span>}
          {dot && <span className="studio-export-activity" aria-hidden />}
          {updateDot && <span className="studio-update-dot" aria-hidden />}
        </span>
        <span className="studio-rail-label">{label}</span>
        {dot && <span className="sr-only">An export is running or ready to open.</span>}
        {updateDot && <span className="sr-only">An update is ready to install.</span>}
      </a>
    </Tooltip>;
  };
  return <nav className="studio-rail-nav" aria-label="Studio">
    <a href="#/" className="studio-rail-logo" aria-label="Manim Studio home" onClick={onNavigate}>
      <span className="studio-brand-mark"><Play aria-hidden fill="currentColor" /></span>
    </a>
    {collapsed && <Tooltip content="Show side panel" side="right">
      <button type="button" className="studio-rail-tool" aria-label="Expand sidebar" onClick={onExpand}><PanelLeftOpen /></button>
    </Tooltip>}
    {link({ kind: "gallery" }, "Home", <Home />, route.kind === "gallery")}
    {link({ kind: "templates" }, "Templates", <LayoutGrid />, route.kind === "templates")}
    {link({ kind: "videos" }, "Your videos", <Video />, route.kind === "videos", projects)}
    {link({ kind: "exports" }, "Exports", <FolderDown />, route.kind === "exports", exports, activity)}
    <div className="studio-rail-spacer" />
    {link({ kind: "settings", section: "ai" }, "Connect to AI", <Plug />, route.kind === "settings" && route.section === "ai")}
    {link({ kind: "settings" }, "Settings", <Settings />, route.kind === "settings" && route.section !== "ai", undefined, false, update)}
    <a href="#/author" className="studio-rail-link" aria-label="Author mode" onClick={onNavigate}><span className="studio-rail-icon"><Code2 aria-hidden /></span><span className="studio-rail-label">Author mode</span></a>
  </nav>;
}

/** The same destinations as the rail, laid out in rows for the phone drawer. */
function DrawerNav({ route, onNavigate, projects, exports, activity, update }: NavProps) {
  const link = (target: Route, label: string, icon: ReactNode, active: boolean, count?: number | null, dot = false, updateDot = false) => {
    const description = [dot ? "An export is running or ready to open." : "", updateDot ? "An update is ready to install." : ""]
      .filter(Boolean).join(" ") || undefined;
    return <a key={label} href={routeHash(target)} className="studio-drawer-link" aria-label={label} aria-current={active ? "page" : undefined} aria-description={description} onClick={onNavigate}>
      <span className="studio-rail-icon">{icon}{dot && <span className="studio-export-activity" aria-hidden />}{updateDot && <span className="studio-update-dot" aria-hidden />}</span>
      <span>{label}</span>
      {count != null && <span className="studio-nav-count" aria-hidden>{count}</span>}
      {dot && <span className="sr-only">An export is running or ready to open.</span>}
      {updateDot && <span className="sr-only">An update is ready to install.</span>}
    </a>;
  };
  return <nav className="studio-drawer-nav" aria-label="Studio">
    {link({ kind: "gallery" }, "Home", <Home />, route.kind === "gallery")}
    {link({ kind: "templates" }, "Templates", <LayoutGrid />, route.kind === "templates")}
    {link({ kind: "videos" }, "Your videos", <Video />, route.kind === "videos", projects)}
    {link({ kind: "exports" }, "Exports", <FolderDown />, route.kind === "exports", exports, activity)}
    <div className="studio-nav-divider" />
    {link({ kind: "settings", section: "ai" }, "Connect to AI", <Plug />, route.kind === "settings" && route.section === "ai")}
    {link({ kind: "settings" }, "Settings", <Settings />, route.kind === "settings" && route.section !== "ai", undefined, false, update)}
    {link({ kind: "author" }, "Author mode", <Code2 />, false)}
  </nav>;
}

export function StudioShell({ route, catalog, push, replace, children }: ShellProps) {
  const library = useLibrary();
  const exports = useExports(true, library.revision);
  const { activity, markSeen } = useExportActivity(route.kind === "exports", library.revision);
  const { status: updateStatus } = useUpdateStatus();
  const updateAvailable = !!updateStatus && ["available", "downloading", "ready"].includes(updateStatus.state);
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [mobile, setMobile] = useState(() => window.matchMedia("(max-width: 899px)").matches);
  const [drawer, setDrawer] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const focusOnOpen = useRef(false);
  const mainRef = useRef<HTMLElement>(null);
  const focusFrame = useRef(0);
  const categoryId = route.kind === "templates" ? route.category : undefined;

  useEffect(() => {
    if (route.kind === "exports" && exports.jobs) markSeen();
  }, [route.kind, exports.jobs, markSeen]);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 899px)");
    const changed = () => { setMobile(media.matches); setDrawer(false); };
    media.addEventListener("change", changed);
    return () => media.removeEventListener("change", changed);
  }, []);
  const focusSearch = useCallback(() => {
    if (mobile) {
      if (drawer) { searchRef.current?.focus(); searchRef.current?.select(); }
      else { focusOnOpen.current = true; setDrawer(true); }
    } else {
      setCollapsed(false);
      storeCollapsed(false);
      cancelAnimationFrame(focusFrame.current);
      focusFrame.current = requestAnimationFrame(() => { searchRef.current?.focus(); searchRef.current?.select(); });
    }
  }, [mobile, drawer]);
  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      const target = event.target;
      const editable = target instanceof HTMLElement && (target.isContentEditable || !!target.closest("input, textarea, select, [role=\"textbox\"]"));
      const shortcut = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k";
      const slash = event.key === "/" && !event.ctrlKey && !event.metaKey && !event.altKey && !editable;
      if (!shortcut && !slash || event.isComposing) return;
      if (document.querySelector('[role="dialog"]:not(.studio-navigation-drawer), [role="alertdialog"]')) return;
      event.preventDefault();
      focusSearch();
    };
    window.addEventListener("keydown", keydown);
    return () => window.removeEventListener("keydown", keydown);
  }, [focusSearch]);
  useEffect(() => () => cancelAnimationFrame(focusFrame.current), []);
  useEffect(() => {
    // Announce page changes without interrupting typing in the persistent search field.
    if (document.activeElement !== searchRef.current) mainRef.current?.focus({ preventScroll: true });
    mainRef.current?.scrollTo?.(0, 0);
  }, [route.kind, categoryId]);

  const category = route.kind === "templates" && route.category ? catalog?.sections.find((section) => section.id === route.category) : undefined;
  const pageTitle = route.kind === "templates" && !route.category ? "Templates" : route.kind === "videos" ? "Your videos" : route.kind === "exports" ? "Exports" : null;
  const title = route.kind === "gallery"
    ? "Home"
    : route.kind === "videos"
      ? "Your videos"
      : route.kind === "exports"
        ? "Exports"
        : route.kind === "settings"
          ? route.section === "ai" ? "Connect to AI" : "Settings"
          : category?.title ?? "Templates";
  useEffect(() => { document.title = `${title} · Manim Studio`; }, [title]);
  const collapse = () => { setCollapsed(true); storeCollapsed(true); };
  const expand = () => { setCollapsed(false); storeCollapsed(false); };
  const onSearch = (query: string) => {
    const next: Route = { kind: "templates", ...(route.kind === "templates" && route.category ? { category: route.category } : {}), ...(query ? { query } : {}) };
    if (route.kind === "templates") replace(next); else push(next);
  };
  const counts: Counts = { projects: library.projects?.length ?? null, exports: exports.jobs?.length ?? null, activity, update: updateAvailable };

  return <div className="studio-shell">
    <a href="#studio-main" className="studio-skip-link" onClick={(event) => { event.preventDefault(); mainRef.current?.focus(); }}>Skip to content</a>
    {!mobile && <aside className="studio-sidebar" aria-label="Main navigation">
      <Rail route={route} collapsed={collapsed} onNavigate={() => setDrawer(false)} onExpand={expand} {...counts} />
      {!collapsed && <Panel route={route} catalog={catalog} query={route.kind === "templates" ? route.query ?? "" : ""} onSearch={onSearch} onNavigate={() => setDrawer(false)} searchRef={searchRef} projects={library.projects} onCollapse={collapse} />}
    </aside>}
    <div className="studio-shell-main">
      {mobile && <header className="studio-shell-topbar">
        <a href="#/" className="studio-wordmark" aria-label="Manim Studio home">
          <span className="studio-brand-mark"><Play aria-hidden fill="currentColor" /></span>
          <span>Manim Studio</span>
        </a>
        <button type="button" className="studio-shell-icon" aria-label="Open navigation" aria-haspopup="dialog" aria-expanded={drawer} onClick={() => setDrawer(true)}><Menu /></button>
      </header>}
      <main ref={mainRef} id="studio-main" aria-label={title} tabIndex={-1} className="studio-shell-content studio-scroll">
        <div className="studio-shell-container">
          {category && <nav aria-label="Breadcrumb" className="studio-breadcrumb"><a href="#/templates">Templates</a><ChevronRight aria-hidden /><h1>{title}</h1></nav>}
          {pageTitle && <header className="studio-page-head"><h1>{pageTitle}</h1></header>}
          {children(library, exports)}
        </div>
      </main>
    </div>
    {mobile && <Dialog open={drawer} onOpenChange={setDrawer}>
      <DialogContent variant="sheet" className="studio-navigation-drawer" hideClose onOpenAutoFocus={(event) => {
        if (focusOnOpen.current) { event.preventDefault(); searchRef.current?.focus(); focusOnOpen.current = false; }
      }}>
        <DialogTitle className="sr-only">Navigation</DialogTitle>
        <DialogDescription className="sr-only">Browse templates, your videos and exports, and open settings.</DialogDescription>
        <div className="studio-drawer-head">
          <a href="#/" className="studio-wordmark" aria-label="Manim Studio home" onClick={() => setDrawer(false)}>
            <span className="studio-brand-mark"><Play aria-hidden fill="currentColor" /></span>
            <span>Manim Studio</span>
          </a>
          <button type="button" className="studio-shell-icon" aria-label="Close navigation" onClick={() => setDrawer(false)}><X /></button>
        </div>
        <div className="studio-drawer-body">
          <Panel route={route} catalog={catalog} query={route.kind === "templates" ? route.query ?? "" : ""} onSearch={onSearch} onNavigate={() => setDrawer(false)} searchRef={searchRef} projects={library.projects} />
          <div className="studio-nav-divider" />
          <DrawerNav route={route} onNavigate={() => setDrawer(false)} {...counts} />
        </div>
      </DialogContent>
    </Dialog>}
  </div>;
}
