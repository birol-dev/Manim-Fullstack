import { useEffect, useState } from "react";

import { requestJson } from "@/lib/api";

interface AuthorEvent {
  id: string;
  filename: string;
}

export type AuthorActivityItem = AuthorEvent & ({ kind: "script" } | {
  kind: "render";
  scene: string;
  status: "queued" | "rendering" | "done" | "error" | "cancelled";
  progress: number;
  output?: { url: string };
});

export interface AuthorActivity {
  enabled: boolean;
  items: AuthorActivityItem[];
}

export function useAuthorActivity(watching: boolean) {
  const [data, setData] = useState<AuthorActivity | null>(null);
  const [unreachable, setUnreachable] = useState(false);

  useEffect(() => {
    if (!watching) return;
    const controller = new AbortController();
    let timer: number | undefined;
    const poll = async () => {
      try {
        const activity = await requestJson<AuthorActivity>("/api/author/activity", { signal: controller.signal });
        if (controller.signal.aborted) return;
        setData(activity);
        setUnreachable(false);
      } catch {
        if (!controller.signal.aborted) setUnreachable(true);
      } finally {
        if (!controller.signal.aborted) timer = window.setTimeout(poll, 1800);
      }
    };
    void poll();
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [watching]);

  return { activity: watching ? data : null, unreachable: watching && unreachable };
}
