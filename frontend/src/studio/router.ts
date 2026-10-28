import { useCallback, useEffect, useState } from "react";

/** Hash routes: the gallery, an editor (new from a card, or a saved project), and the code IDE. */
export type Route =
  | { kind: "gallery" }
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
  const path = hash.replace(/^#/, "").replace(/^\/+/, "").replace(/\/+$/, "");
  const [head, ...rest] = path.split("/");
  if (head === "author") return { kind: "author" };
  if (head === "new" && rest[0]) return { kind: "new", template: decode(rest[0]), preset: decode(rest[1]) };
  if (head === "project" && rest[0]) return { kind: "project", id: decode(rest[0]) };
  return { kind: "gallery" };
}

export function routeHash(route: Route): string {
  switch (route.kind) {
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

  return { route: state.route, routeKey: state.key, replace };
}

export function navigate(route: Route) {
  window.location.hash = routeHash(route);
}
