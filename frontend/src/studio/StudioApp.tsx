/** The studio: gallery → editor → export. Author mode (#/author) is the code editor. */
import { lazy, Suspense } from "react";
import { Toaster } from "sonner";
import { RotateCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { TooltipProvider } from "@/components/ui/tooltip";

import "./studio.css";
import { friendlyError } from "./api";
import { Spinner } from "./components";
import { EditorPage } from "./Editor";
import { Gallery } from "./Gallery";
import { useCatalog } from "./hooks";
import { useHashRoute } from "./router";

const AuthorApp = lazy(() => import("@/App"));

function Loading({ label }: { label: string }) {
  return (
    <div className="flex h-full items-center justify-center gap-2 text-sm text-fg-muted">
      <Spinner /> {label}
    </div>
  );
}

function Studio({ route, routeKey, replace }: ReturnType<typeof useHashRoute>) {
  const { catalog, error, loading, retry } = useCatalog();

  let page;
  if (loading || (!catalog && !error)) page = <Loading label="Loading designs…" />;
  else if (!catalog) {
    page = (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
        <h1 className="text-lg font-semibold text-fg">Couldn't load the designs.</h1>
        <p className="max-w-sm text-sm text-fg-muted">{friendlyError(error)}</p>
        <Button variant="secondary" size="md" onClick={retry}>
          <RotateCw /> Try again
        </Button>
      </div>
    );
  } else if (route.kind === "new" || route.kind === "project") {
    page = <EditorPage key={routeKey} catalog={catalog} route={route} onProjectCreated={(id) => replace({ kind: "project", id })} />;
  } else {
    page = <Gallery key={routeKey} catalog={catalog} />;
  }

  return (
    <div className={route.kind === "gallery" ? "h-full overflow-y-auto text-sm" : "h-full overflow-hidden text-sm"}>
      {page}
    </div>
  );
}

export default function StudioApp() {
  const hashRoute = useHashRoute();
  if (hashRoute.route.kind === "author") {
    return (
      <Suspense fallback={<Loading label="Opening author mode…" />}>
        <AuthorApp />
      </Suspense>
    );
  }
  return (
    <TooltipProvider delayDuration={400} skipDelayDuration={200}>
      <Studio {...hashRoute} />
      <Toaster theme="dark" position="bottom-right" richColors closeButton />
    </TooltipProvider>
  );
}
