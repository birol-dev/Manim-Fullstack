import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { BarChart3, ChevronDown, ChevronRight, Code2, FolderDown, GraduationCap, Home, LayoutGrid, MapPin, Menu, Monitor, Moon, PanelLeftClose, PanelLeftOpen, PartyPopper, Play, Plug, Repeat, Search, Sun, Timer, Trophy, Video, X, Megaphone } from "lucide-react";

import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Tooltip } from "@/components/ui/tooltip";

import { readCategoriesOpen, readCollapsed, setCategoriesOpen, setCollapsed as storeCollapsed, type Appearance } from "./appearance";
import { Segments } from "./components";
import { ConnectionDialog } from "./ConnectionDialog";
import { useExportActivity, useExports } from "./hooks";
import { routeHash, type Route, type useHashRoute } from "./router";
import type { Catalog } from "./types";
import { useLibrary, type Library } from "./useLibrary";
import "./shell.css";

type LibraryRoute = Extract<Route, { kind: "gallery" | "templates" | "videos" | "exports" }>;
type Exports = ReturnType<typeof useExports>;
interface ShellProps {
  route: LibraryRoute;
  catalog: Catalog | null;
  appearance: Appearance;
  onAppearance: (value: Appearance) => void;
  push: ReturnType<typeof useHashRoute>["push"];
  replace: ReturnType<typeof useHashRoute>["replace"];
  children: (library: Library, exports: Exports) => ReactNode;
}

const CATEGORY_ICONS = { announce: Megaphone, celebrate: PartyPopper, timers: Timer, creator: Video, teach: GraduationCap, numbers: BarChart3, sports: Trophy, travel: MapPin, screens: Repeat };

/** Keep in step with the compact-height rules in shell.css. */
const SHORT_HEIGHT = "(max-height: 760px)";

/** Whether the window is too short for the full-height sidebar (the category list starts closed). */
function useShortViewport() {
  const [short, setShort] = useState(() => window.matchMedia(SHORT_HEIGHT).matches);
  useEffect(() => {
    const media = window.matchMedia(SHORT_HEIGHT);
    const changed = () => setShort(media.matches);
    media.addEventListener("change", changed);
    return () => media.removeEventListener("change", changed);
  }, []);
  return short;
}

interface SidebarProps extends Omit<ShellProps, "children" | "push" | "replace"> {
  collapsed: boolean;
  collapsible: boolean;
  onToggle: () => void;
  onNavigate: () => void;
  onConnect: () => void;
  onSearch: (value: string) => void;
  onFocusSearch: () => void;
  searchRef: RefObject<HTMLInputElement | null>;
  projectsCount: number | null;
  exportsCount: number | null;
  activity: boolean;
}

function Sidebar({ route, catalog, appearance, onAppearance, collapsed, collapsible, onToggle, onNavigate, onConnect, onSearch, onFocusSearch, searchRef, projectsCount, exportsCount, activity }: SidebarProps) {
  const short = useShortViewport();
  // Short windows start with the category list closed; an explicit choice always wins.
  const [categoriesChoice, setCategoriesChoice] = useState(readCategoriesOpen);
  const categoriesOpen = categoriesChoice ?? !short;
  const [navFade, setNavFade] = useState({ top: false, bottom: false });
  const navRef = useRef<HTMLElement>(null);
  const measureNav = useCallback(() => {
    const nav = navRef.current;
    if (!nav) return;
    const top = nav.scrollTop > 2;
    const bottom = nav.scrollTop + nav.clientHeight < nav.scrollHeight - 2;
    setNavFade((current) => (current.top === top && current.bottom === bottom ? current : { top, bottom }));
  }, []);
  useLayoutEffect(measureNav);
  useEffect(() => {
    const nav = navRef.current;
    if (!nav) return;
    const observer = new ResizeObserver(measureNav);
    observer.observe(nav);
    return () => observer.disconnect();
  }, [measureNav]);
  const toggleCategories = () => {
    const next = !categoriesOpen;
    setCategoriesChoice(next);
    setCategoriesOpen(next);
  };
  const fade = navFade.top && navFade.bottom ? "both" : navFade.top ? "top" : navFade.bottom ? "bottom" : undefined;
  const query = route.kind === "templates" ? route.query ?? "" : "";
  const navLink = (target: Route, label: string, icon: ReactNode, active: boolean, count?: number | null, dot = false) => (
    <Tooltip content={label} side="right">
      <a href={routeHash(target)} className="studio-nav-item" aria-label={label} aria-current={active ? "page" : undefined} aria-description={dot ? "An export is running or ready to open." : undefined} onClick={onNavigate}>
        <span className="studio-nav-icon">{icon}{dot && <span className="studio-export-activity" aria-hidden />}</span>
        <span className="studio-sidebar-label">{label}</span>
        {count != null && <span className="studio-nav-count" aria-hidden>{count}</span>}
        {dot && <span className="sr-only">An export is running or ready to open.</span>}
      </a>
    </Tooltip>
  );
  return <div className="studio-sidebar-inner" data-collapsed={collapsed}>
    <div className="studio-sidebar-brand">
      <a href="#/" className="studio-wordmark" aria-label="Manim Studio home" onClick={onNavigate}>
        <span className="studio-brand-mark"><Play aria-hidden fill="currentColor" /></span>
        <span className="studio-sidebar-label">Manim Studio</span>
      </a>
      {collapsible && !collapsed && <button type="button" className="studio-shell-icon studio-sidebar-collapse" aria-label="Collapse sidebar" onClick={onToggle}><PanelLeftClose /></button>}
    </div>
    <div className="studio-sidebar-search">
      {collapsed ? <Tooltip content="Search videos and templates" shortcut="Ctrl+K" side="right"><button type="button" className="studio-shell-icon" aria-label="Search videos and templates" onClick={onFocusSearch}><Search /></button></Tooltip> : <>
        <Search aria-hidden />
        <input ref={searchRef} type="search" value={query} onChange={(event) => onSearch(event.target.value)} placeholder="Search" title="Search videos and templates" aria-label="Search designs" aria-keyshortcuts="Control+k Meta+k /" />
        {query ? <button type="button" aria-label="Clear search" onClick={() => onSearch("")}><X /></button> : <kbd aria-hidden>Ctrl K</kbd>}
      </>}
    </div>
    <nav ref={navRef} aria-label="Studio" className="studio-sidebar-nav" data-fade={fade} onScroll={measureNav}>
      {navLink({ kind: "gallery" }, "Home", <Home />, route.kind === "gallery")}
      <div className="studio-nav-templates">
        {navLink({ kind: "templates" }, "Templates", <LayoutGrid />, route.kind === "templates" && (!route.category || collapsed || !categoriesOpen), catalog?.sections.reduce((count, section) => count + section.cards.length, 0))}
        {!collapsed && <button type="button" className="studio-category-toggle" aria-label={categoriesOpen ? "Collapse template categories" : "Expand template categories"} aria-expanded={categoriesOpen} aria-controls="studio-template-categories" onClick={toggleCategories}>{categoriesOpen ? <ChevronDown /> : <ChevronRight />}</button>}
      </div>
      {!collapsed && categoriesOpen && <div id="studio-template-categories" className="studio-nav-categories" role="group" aria-label="Template categories">
        {catalog?.sections.map((section) => {
          const Icon = CATEGORY_ICONS[section.id as keyof typeof CATEGORY_ICONS] ?? LayoutGrid;
          return <a key={section.id} href={routeHash({ kind: "templates", category: section.id })} className="studio-nav-item" aria-label={section.title} aria-current={route.kind === "templates" && route.category === section.id ? "page" : undefined} onClick={onNavigate}>
            <Icon aria-hidden /><span>{section.title}</span><span className="studio-nav-count" aria-hidden>{section.cards.length}</span>
          </a>;
        })}
      </div>}
      <div className="studio-nav-divider" />
      {navLink({ kind: "videos" }, "Your videos", <Video />, route.kind === "videos", projectsCount)}
      {navLink({ kind: "exports" }, "Exports", <FolderDown />, route.kind === "exports", exportsCount, activity)}
    </nav>
    <div className="studio-sidebar-footer">
      <Tooltip content="Connect to AI" side="right"><button type="button" className="studio-nav-item" aria-label="Connect to AI" onClick={onConnect}><Plug aria-hidden /><span className="studio-sidebar-label">Connect to AI</span></button></Tooltip>
      <div className="studio-appearance">
        <span className="studio-sidebar-label studio-appearance-label">Appearance</span>
        <Segments<Appearance> aria-label="Appearance" value={appearance} onChange={onAppearance} options={[
          { value: "light", label: <><Sun aria-hidden /><span className="studio-sidebar-label">Light</span></>, title: "Light" },
          { value: "dark", label: <><Moon aria-hidden /><span className="studio-sidebar-label">Dark</span></>, title: "Dark" },
          { value: "system", label: <><Monitor aria-hidden /><span className="studio-sidebar-label">System</span></>, title: "System" },
        ]} />
      </div>
      <a href="#/author" className="studio-author-link" aria-label="Author mode" onClick={onNavigate}><Code2 aria-hidden /><span className="studio-sidebar-label">Author mode</span></a>
    </div>
  </div>;
}

export function StudioShell({ route, catalog, appearance, onAppearance, push, replace, children }: ShellProps) {
  const library = useLibrary();
  const exports = useExports(true, library.revision);
  const { activity, markSeen } = useExportActivity(route.kind === "exports", library.revision);
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [mobile, setMobile] = useState(() => window.matchMedia("(max-width: 899px)").matches);
  const [drawer, setDrawer] = useState(false);
  const [connection, setConnection] = useState(false);
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
    }
    else {
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
  const title = route.kind === "gallery" ? "Home" : route.kind === "videos" ? "Your videos" : route.kind === "exports" ? "Exports" : category?.title ?? "Templates";
  useEffect(() => { document.title = `${title} · Manim Studio`; }, [title]);
  const toggleSidebar = () => { setCollapsed((value) => !value); storeCollapsed(!collapsed); };
  const sidebarProps = {
    route, catalog, appearance, onAppearance,
    collapsed: !mobile && collapsed,
    collapsible: !mobile,
    onToggle: toggleSidebar,
    onNavigate: () => setDrawer(false),
    onConnect: () => { setDrawer(false); setConnection(true); },
    onSearch: (query: string) => {
      const next: Route = { kind: "templates", ...(route.kind === "templates" && route.category ? { category: route.category } : {}), ...(query ? { query } : {}) };
      if (route.kind === "templates") replace(next); else push(next);
    },
    onFocusSearch: focusSearch,
    projectsCount: library.projects?.length ?? null, exportsCount: exports.jobs?.length ?? null, activity,
  };
  return <div className="studio-shell" data-collapsed={collapsed}>
    <a href="#studio-main" className="studio-skip-link" onClick={(event) => { event.preventDefault(); mainRef.current?.focus(); }}>Skip to content</a>
    {!mobile && <aside className="studio-sidebar" aria-label="Main navigation"><Sidebar searchRef={searchRef} {...sidebarProps} /></aside>}
    <div className="studio-shell-main">
      <header className="studio-shell-topbar">
        {mobile ? <button type="button" className="studio-shell-icon" aria-label="Open navigation" aria-haspopup="dialog" aria-expanded={drawer} onClick={() => setDrawer(true)}><Menu /></button> : collapsed && <button type="button" className="studio-shell-icon" aria-label="Expand sidebar" onClick={toggleSidebar}><PanelLeftOpen /></button>}
        {category ? <nav aria-label="Breadcrumb" className="studio-breadcrumb"><a href="#/templates">Templates</a><ChevronRight aria-hidden /><h1>{title}</h1></nav> : route.kind === "gallery" ? <span>{title}</span> : <h1>{title}</h1>}
      </header>
      <main ref={mainRef} id="studio-main" aria-label={title} tabIndex={-1} className="studio-shell-content studio-scroll"><div className="studio-shell-container">{children(library, exports)}</div></main>
    </div>
    {mobile && <Dialog open={drawer} onOpenChange={setDrawer}>
      <DialogContent variant="sheet" className="studio-navigation-drawer" hideClose onOpenAutoFocus={(event) => {
        if (focusOnOpen.current) { event.preventDefault(); searchRef.current?.focus(); focusOnOpen.current = false; }
      }} onCloseAutoFocus={(event) => { if (connection) event.preventDefault(); }}>
        <DialogTitle className="sr-only">Navigation</DialogTitle><DialogDescription className="sr-only">Browse templates, your videos and exports.</DialogDescription>
        <button type="button" className="studio-shell-icon studio-drawer-close" aria-label="Close navigation" onClick={() => setDrawer(false)}><X /></button>
        <Sidebar searchRef={searchRef} {...sidebarProps} />
      </DialogContent>
    </Dialog>}
    {connection && <ConnectionDialog onClose={() => setConnection(false)} />}
  </div>;
}
