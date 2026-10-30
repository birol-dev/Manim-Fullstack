/** The studio: gallery → editor → export. Author mode (#/author) is the code editor. */
import { lazy, Suspense, useEffect, useLayoutEffect, useState, type ReactNode } from "react";
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
import { needsOnboarding } from "./preferences";
import { useHashRoute } from "./router";
import { StudioShell } from "./StudioShell";

const AuthorApp = lazy(() => import("@/App"));
const SettingsPage = lazy(() => import("./Settings").then((module) => ({ default: module.SettingsPage })));
const OnboardingPage = lazy(() => import("./Onboarding").then((module) => ({ default: module.OnboardingPage })));

function Loading({ label }: { label: string }) {
  return (
    <div className="flex h-full items-center justify-center gap-2 text-sm text-fg-muted">
      <Spinner /> {label}
    </div>
  );
}

function Studio({ route, routeKey, replace, push, appearance, onAppearance }: ReturnType<typeof useHashRoute> & { appearance: Appearance; onAppearance: (value: Appearance) => void }) {
  const { catalog, error, loading, retry } = useCatalog();

  if (route.kind === "welcome") {
    return <Suspense fallback={<Loading label="Getting things ready…" />}><OnboardingPage /></Suspense>;
  }

  if (route.kind === "settings") {
    return <StudioShell route={route} catalog={catalog} push={push} replace={replace}>
      {() => <Suspense fallback={<Loading label="Opening settings…" />}><SettingsPage section={route.section} appearance={appearance} onAppearance={onAppearance} /></Suspense>}
    </StudioShell>;
  }

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
  } else if (editor) {
    page = <EditorPage key={routeKey} catalog={catalog} route={route} onProjectCreated={(id) => replace({ kind: "project", id })} />;
  }

  if (route.kind === "gallery" || route.kind === "templates" || route.kind === "videos" || route.kind === "exports") {
    return <StudioShell route={route} catalog={catalog} push={push} replace={replace}>
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
  const { route, replace } = hashRoute;
  const [appearance, setAppearance] = useState<Appearance>(readAppearance);
  const changeAppearance = (value: Appearance) => { setAppearance(value); storeAppearance(value); };
  const isStudio = route.kind !== "author";
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
  // A first launch lands on the welcome tour once the workspace has answered; an unanswered
  // request (or a test without a preferences mock) keeps the gallery.
  useLayoutEffect(() => {
    if (route.kind === "gallery" && needsOnboarding()) replace({ kind: "welcome" });
  }, [route.kind, replace]);
  useEffect(() => {
    if (route.kind === "welcome") document.title = "Welcome · Manim Studio";
  }, [route.kind]);
  if (route.kind === "author") {
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
