import { RefreshCw, Wrench } from "lucide-react";

import { Button } from "@/components/ui/button";
import { PathText } from "@/components/ui/code-text";
import { EmptyState, Section } from "@/components/ui/panel";
import { Tooltip } from "@/components/ui/tooltip";
import { isInstalled } from "@/hooks/useDiagnostics";
import type { Dependency, Diagnostics } from "@/lib/types";
import { cn } from "@/lib/utils";
import { SidebarPanel } from "./SidebarPanel";

interface SystemPanelProps {
  diagnostics: Diagnostics | null;
  offline: boolean;
  onRefresh: () => void;
  onOpenSetup: () => void;
}

const PROFILE_LABELS: Record<string, string> = { eco: "Eco", balanced: "Balanced", workstation: "Workstation" };

/** Label + value. Long values (CPU / GPU model, platform) truncate; the full text is in a tooltip and title. */
function Row({ label, value, full }: { label: string; value: string; full?: boolean }) {
  const text = (
    <span className="min-w-0 truncate text-right text-fg" title={full ? value : undefined}>
      {value}
    </span>
  );
  return (
    <div className="flex items-baseline justify-between gap-3 px-1 py-1 text-xs">
      <span className="shrink-0 text-fg-subtle">{label}</span>
      {full ? (
        <Tooltip content={value} side="right">
          {text}
        </Tooltip>
      ) : (
        text
      )}
    </div>
  );
}

const DEPENDENCIES: Array<{ id: Dependency | "dvisvgm"; label: string; optional: boolean }> = [
  { id: "manim", label: "Manim CE", optional: false },
  { id: "latex", label: "LaTeX", optional: true },
  { id: "dvisvgm", label: "dvisvgm", optional: true },
  { id: "ffmpeg", label: "FFmpeg", optional: true },
];

export function SystemPanel({ diagnostics, offline, onRefresh, onOpenSetup }: SystemPanelProps) {
  const actions = (
    <Button variant="ghost" size="icon-xs" aria-label="Re-check system" onClick={onRefresh}>
      <RefreshCw />
    </Button>
  );

  if (!diagnostics) {
    return (
      <SidebarPanel title="System" actions={actions}>
        <EmptyState
          title={offline ? "Server offline" : "Checking your system…"}
          description={offline ? "Start the backend with python run.py. This panel fills in once it responds." : undefined}
        />
      </SidebarPanel>
    );
  }

  const { hardware, dependencies } = diagnostics;
  return (
    <SidebarPanel title="System" actions={actions}>
      <div className="flex flex-col gap-4">
        <div className="rounded-lg border border-line bg-raised/40 p-3">
          <div className="mb-1 flex items-center gap-2">
            <span className="text-[13px] font-medium text-fg">{PROFILE_LABELS[diagnostics.profile] ?? diagnostics.profile} profile</span>
            <span className="rounded bg-accent-soft px-1.5 py-px text-2xs font-medium text-accent">{diagnostics.preview_quality}</span>
          </div>
          <p className="text-xs leading-relaxed text-fg-muted">{diagnostics.description}</p>
        </div>

        <Section title="Dependencies">
          <ul className="flex flex-col">
            {DEPENDENCIES.map((dependency) => {
              const path = dependencies[dependency.id === "latex" ? "latex" : dependency.id];
              const ok = dependency.id === "dvisvgm" ? path !== "Not Found" : isInstalled(diagnostics, dependency.id);
              return (
                <li key={dependency.id} className="flex flex-wrap items-center gap-x-2 px-1 py-1 text-xs">
                  <span
                    className={cn("size-1.5 shrink-0 rounded-full", ok ? "bg-success" : dependency.optional ? "bg-warning" : "bg-danger")}
                  />
                  <span className="shrink-0 text-fg">{dependency.label}</span>
                  {ok ? (
                    // Paths get their own line and wrap only after "/" (no "…/bin/ffm…" truncation at 1024).
                    <span className="code-wrap basis-full pl-3.5 font-mono text-2xs leading-4 text-fg-subtle" title={path}>
                      <PathText path={path} />
                    </span>
                  ) : (
                    <span className="ml-auto text-2xs text-fg-subtle">{dependency.optional ? "optional · not found" : "not found"}</span>
                  )}
                </li>
              );
            })}
          </ul>
          <Button size="sm" onClick={onOpenSetup} className="mt-1">
            <Wrench />
            Open setup guide
          </Button>
        </Section>

        <Section title="Hardware">
          <div className="flex flex-col">
            <Row label="CPU" value={hardware.cpu.model} full />
            <Row label="Cores" value={`${hardware.cpu.physical_cores} cores · ${hardware.cpu.logical_threads} threads`} />
            <Row label="Memory" value={`${hardware.ram_gb.toFixed(1)} GB`} />
            <Row label="GPU" value={hardware.gpu.devices[0]?.name ?? "—"} full={Boolean(hardware.gpu.devices[0]?.name)} />
            {diagnostics.platform && (
              <Row label="Platform" value={`${diagnostics.platform}${diagnostics.python_version ? ` · Python ${diagnostics.python_version}` : ""}`} full />
            )}
          </div>
        </Section>
      </div>
    </SidebarPanel>
  );
}
