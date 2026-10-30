import { useCallback, useEffect, useState } from "react";

/** Hash routes: the library, its pages, an editor, settings, the welcome tour and the code IDE. */
export type Route =
  | { kind: "gallery" }
  | { kind: "templates"; category?: string; query?: string }
  | { kind: "videos" }
  | { kind: "exports" }
  | { kind: "settings"; section?: string }
  | { kind: "welcome" }
  | { kind: "new"; template: string; preset: string }
  | { kind: "project"; id: string }
  | { kind: "author" };

function decode(part: string | undefined): string {
  if (!part) return "";
  try {
    return decodeURIComponent(part);
  } catch {
    return part;
  }
}

export function parseRoute(hash: string): Route {
  const [pathname, search = ""] = hash.replace(/^#/, "").split("?");
  const path = pathname.replace(/^\/+/, "").replace(/\/+$/, "");
  const [head, ...rest] = path.split("/");
  if (head === "templates") {
    const query = new URLSearchParams(search).get("q");
    return { kind: "templates", ...(rest[0] ? { category: decode(rest[0]) } : {}), ...(query ? { query } : {}) };
  }
  if (head === "videos") return { kind: "videos" };
  if (head === "exports") return { kind: "exports" };
  if (head === "settings") return { kind: "settings", ...(rest[0] ? { section: decode(rest[0]) } : {}) };
  if (head === "welcome") return { kind: "welcome" };
  if (head === "author") return { kind: "author" };
  if (head === "new" && rest[0]) return { kind: "new", template: decode(rest[0]), preset: decode(rest[1]) };
  if (head === "project" && rest[0]) return { kind: "project", id: decode(rest[0]) };
  return { kind: "gallery" };
}

export function routeHash(route: Route): string {
  switch (route.kind) {
    case "templates": {
      const query = route.query ? `?${new URLSearchParams({ q: route.query })}` : "";
      return `#/templates${route.category ? `/${encodeURIComponent(route.category)}` : ""}${query}`;
    }
    case "videos":
      return "#/videos";
    case "exports":
      return "#/exports";
    case "settings":
      return `#/settings${route.section ? `/${encodeURIComponent(route.section)}` : ""}`;
    case "welcome":
      return "#/welcome";
    case "author":
      return "#/author";
    case "new":
      return `#/new/${encodeURIComponent(route.template)}/${encodeURIComponent(route.preset)}`;
    case "project":
      return `#/project/${encodeURIComponent(route.id)}`;
    default:
      return "#/";
  }
}

interface RouteState {
  route: Route;
  /** Changes on every real navigation; stays the same when the editor renames its own URL. */
  key: number;
}

/**
 * The current hash route. `replace` swaps the URL without a navigation (an editor that just
 * saved its new project moves from #/new/... to #/project/<id> and keeps its state).
 */
export function useHashRoute() {
  const [state, setState] = useState<RouteState>(() => ({ route: parseRoute(window.location.hash), key: 0 }));

  useEffect(() => {
    const onHashChange = () => setState((prev) => ({ route: parseRoute(window.location.hash), key: prev.key + 1 }));
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const replace = useCallback((route: Route) => {
    window.history.replaceState(window.history.state, "", routeHash(route));
    setState((prev) => ({ route, key: prev.key }));
  }, []);

  const push = useCallback((route: Route) => {
    window.history.pushState(window.history.state, "", routeHash(route));
    setState((prev) => ({ route, key: prev.key + 1 }));
  }, []);

  return { route: state.route, routeKey: state.key, replace, push };
}

export function navigate(route: Route) {
  window.location.hash = routeHash(route);
}
