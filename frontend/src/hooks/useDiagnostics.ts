import { useCallback, useEffect, useState } from "react";

import { postJson, requestJson } from "@/lib/api";
import type { Dependency, Diagnostics } from "@/lib/types";

export type BackendStatus = "loading" | "online" | "offline";

const OFFLINE_RETRY_MS = 4000;
const INSTALL_POLL_MS = 3000;
const INSTALL_TIMEOUT_MS = 15 * 60 * 1000;

export function isInstalled(diagnostics: Diagnostics | null, dependency: Dependency): boolean {
  if (!diagnostics) return false;
  const deps = diagnostics.dependencies;
  if (dependency === "latex") return Boolean(deps.latex_available);
  const path = deps[dependency];
  return Boolean(path) && path !== "Not Found";
}

/** Server reachability, hardware profile, and dependency installs. */
export function useDiagnostics() {
  const [data, setData] = useState<Diagnostics | null>(null);
  const [status, setStatus] = useState<BackendStatus>("loading");
  // Dependency -> time the install was started.
  const [installing, setInstalling] = useState<Partial<Record<Dependency, number>>>({});

  const refresh = useCallback(async () => {
    try {
      const next = await requestJson<Diagnostics>("/api/diagnostics");
      setData(next);
      setStatus("online");
      setInstalling((previous) => {
        const now = Date.now();
        const entries = Object.entries(previous).filter(
          ([dependency, startedAt]) =>
            !isInstalled(next, dependency as Dependency) && now - (startedAt ?? 0) < INSTALL_TIMEOUT_MS,
        );
        return entries.length === Object.keys(previous).length ? previous : Object.fromEntries(entries);
      });
      return next;
    } catch {
      setStatus("offline");
      return null;
    }
  }, []);

  useEffect(() => {
    // Initial load; the state updates happen after the request resolves.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (status !== "offline") return;
    const timer = setInterval(() => void refresh(), OFFLINE_RETRY_MS);
    return () => clearInterval(timer);
  }, [status, refresh]);

  const installCount = Object.keys(installing).length;
  useEffect(() => {
    if (installCount === 0) return;
    const timer = setInterval(() => void refresh(), INSTALL_POLL_MS);
    return () => clearInterval(timer);
  }, [installCount, refresh]);

  /** Start an installer on the server. Resolves with its message; throws ApiError. */
  const install = useCallback(async (dependency: Dependency) => {
    const result = await postJson<{ message: string }>(`/api/install-${dependency}`);
    setInstalling((previous) => ({ ...previous, [dependency]: Date.now() }));
    return result.message;
  }, []);

  const isInstalling = useCallback((dependency: Dependency) => dependency in installing, [installing]);

  return { data, status, refresh, install, isInstalling };
}
