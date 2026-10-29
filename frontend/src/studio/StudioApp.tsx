/** The studio: gallery → editor → export. Author mode (#/author) is the code editor. */
import { lazy, Suspense, useLayoutEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Toaster } from "sonner";
import { RotateCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { TooltipProvider } from "@/components/ui/tooltip";

import "./studio.css";
import { friendlyError } from "./api";
import { readAppearance, setAppearance as storeAppearance, type Appearance } from "./appearance";
import { Spinner } from "./components";
import { EditorPage } from "./Editor";
import { Gallery, GalleryLoading } from "./Gallery";
import { useCatalog } from "./hooks";
import { useHashRoute } from "./router";
import { StudioShell } from "./StudioShell";

const AuthorApp = lazy(() => import("@/App"));

function Loading({ label }: { label: string }) {
  return (
    <div className="flex h-full items-center justify-center gap-2 text-sm text-fg-muted">
      <Spinner /> {label}
    </div>
  );
}

function Studio({ route, routeKey, replace, push, appearance, onAppearance }: ReturnType<typeof useHashRoute> & { appearance: Appearance; onAppearance: (value: Appearance) => void }) {
  const { catalog, error, loading, retry } = useCatalog();

  let page: ReactNode;
  const editor = route.kind === "new" || route.kind === "project";
  if (loading || (!catalog && !error)) page = editor ? <Loading label="Loading designs…" /> : <GalleryLoading />;
  else if (!catalog) {
    page = (
      <div role="alert" className="studio-page-state">
        <h1 className="text-lg font-semibold text-fg">Couldn't load the designs.</h1>
        <p className="max-w-sm text-sm text-fg-muted">{friendlyError(error)}</p>
        <Button variant="secondary" size="md" onClick={retry}>
          <RotateCw /> Try again
        </Button>
      </div>
    );
  } else if (route.kind === "new" || route.kind === "project") {
    page = <EditorPage key={routeKey} catalog={catalog} route={route} onProjectCreated={(id) => replace({ kind: "project", id })} />;
  }

  if (route.kind === "gallery" || route.kind === "templates" || route.kind === "videos" || route.kind === "exports") {
    return <StudioShell route={route} catalog={catalog} appearance={appearance} onAppearance={onAppearance} push={push} replace={replace}>
      {(library, exports) => catalog && !loading ? <Gallery catalog={catalog} route={route} library={library} exports={exports} /> : page}
    </StudioShell>;
  }
  return (
    <div className="h-full overflow-hidden">
      {page}
    </div>
  );
}

export default function StudioApp() {
  const hashRoute = useHashRoute();
  const [appearance, setAppearance] = useState<Appearance>(readAppearance);
  const isStudio = hashRoute.route.kind !== "author";
  useLayoutEffect(() => {
    if (isStudio) {
      document.documentElement.dataset.surface = "studio";
      if (appearance === "system") delete document.documentElement.dataset.theme;
      else document.documentElement.dataset.theme = appearance;
    } else {
      delete document.documentElement.dataset.surface;
      delete document.documentElement.dataset.theme;
    }
    return () => { delete document.documentElement.dataset.surface; delete document.documentElement.dataset.theme; };
  }, [isStudio, appearance]);
  const changeAppearance = (value: Appearance) => { setAppearance(value); storeAppearance(value); };
  if (hashRoute.route.kind === "author") {
    return (
      <Suspense fallback={<Loading label="Opening author mode…" />}>
        <AuthorApp />
      </Suspense>
    );
  }
  return (
    <TooltipProvider delayDuration={400} skipDelayDuration={200}>
      <Studio {...hashRoute} appearance={appearance} onAppearance={changeAppearance} />
      {createPortal(<Toaster theme={appearance} position="bottom-right" richColors closeButton />, document.body)}
    </TooltipProvider>
  );
}
