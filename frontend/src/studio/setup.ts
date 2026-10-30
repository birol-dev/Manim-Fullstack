/** Zero-setup client: what the app needs, and which AI apps can be connected for the person. */
import { useCallback, useEffect, useState } from "react";

import { postJson, requestJson } from "@/lib/api";

export type ComponentStatus = "ready" | "missing" | "optional" | "installing" | "failed";

export interface SetupComponent {
  id: string;
  label: string;
  purpose: string;
  status: ComponentStatus;
  required: boolean;
  can_install: boolean;
  detail: string | null;
  progress: number | null;
}

export interface AIApp {
  id: string;
  label: string;
  detected: boolean;
  connected: boolean;
  needs_repair: boolean;
  restart_hint: string | null;
  error: string | null;
}

export interface SetupStatus {
  platform: "windows" | "macos" | "linux";
  mode: "desktop" | "source";
  components: SetupComponent[];
  ai_apps: AIApp[];
  data_folder: string;
}

export const getSetupStatus = () => requestJson<SetupStatus>("/api/studio/setup/status");
export const connectAIApp = (id: string) => postJson<AIApp>(`/api/studio/setup/ai-apps/${encodeURIComponent(id)}/connect`, {});
export const disconnectAIApp = (id: string) => requestJson<AIApp>(`/api/studio/setup/ai-apps/${encodeURIComponent(id)}/connect`, { method: "DELETE" });
export const installComponent = (id: string) => postJson<SetupComponent>(`/api/studio/setup/components/${encodeURIComponent(id)}/install`, {});
export const revealDataFolder = () => requestJson<void>("/api/studio/setup/reveal-data-folder", { method: "POST" });

/** Polls while something is installing, so progress moves without any refresh button. */
export function useSetupStatus() {
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [error, setError] = useState<unknown>(null);
  const refresh = useCallback(() => getSetupStatus().then(
    (next) => { setStatus(next); setError(null); return next; },
    (failure) => { setError(failure); return null; },
  ), []);
  useEffect(() => { void refresh(); }, [refresh]);
  const installing = status?.components.some((component) => component.status === "installing") ?? false;
  useEffect(() => {
    if (!installing) return;
    const timer = window.setInterval(() => { void refresh(); }, 1000);
    return () => window.clearInterval(timer);
  }, [installing, refresh]);
  return { status, error, refresh };
}
