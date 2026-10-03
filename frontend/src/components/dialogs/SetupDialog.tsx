import { useState } from "react";
import { Check, CheckCircle2, CircleDashed, Copy, Download, Loader2, RefreshCw, XCircle } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Callout } from "@/components/ui/panel";
import { isInstalled } from "@/hooks/useDiagnostics";
import { errorMessage } from "@/lib/api";
import type { Dependency, Diagnostics } from "@/lib/types";
import { cn } from "@/lib/utils";

type Platform = "Windows" | "Darwin" | "Linux";

interface DependencyInfo {
  id: Dependency;
  name: string;
  description: string;
  required: boolean;
  /** Install commands per platform (shown for copy/paste). */
  commands: Record<Platform, string>;
  /** Whether the server can run the installer itself on this platform. */
  canAutoInstall: (platform: Platform) => boolean;
  installLabel: string;
}

const DEPENDENCIES: DependencyInfo[] = [
  {
    id: "manim",
    name: "Manim Community Edition",
    description: "The animation engine that renders your scenes.",
    required: true,
    commands: {
      Windows: "pip install manim",
      Darwin: "brew install cairo pkg-config && pip install manim",
      Linux: "sudo apt install build-essential pkg-config libcairo2-dev libpango1.0-dev && pip install manim",
    },
    canAutoInstall: (platform) => platform === "Windows",
    installLabel: "Install with pip",
  },
  {
    id: "latex",
    name: "LaTeX",
    description: "Needed for MathTex, Tex, and numbered axes. Text() works without it.",
    required: false,
    commands: {
      Windows: "winget install MiKTeX.MiKTeX",
      Darwin: "brew install --cask mactex-no-gui",
      Linux: "sudo apt install texlive texlive-latex-extra",
    },
    canAutoInstall: (platform) => platform === "Windows",
    installLabel: "Install MiKTeX",
  },
  {
    id: "ffmpeg",
    name: "FFmpeg",
    description: "Only needed for scenes with sound (add_sound). Manim encodes video on its own.",
    required: false,
    commands: {
      Windows: "winget install Gyan.FFmpeg",
      Darwin: "brew install ffmpeg",
      Linux: "sudo apt install ffmpeg",
    },
    canAutoInstall: (platform) => platform === "Windows",
    installLabel: "Install FFmpeg",
  },
];

function normalizePlatform(value: string | undefined): Platform {
  if (value === "Windows" || value === "Darwin") return value;
  if (value === "Linux") return "Linux";
  const agent = typeof navigator === "undefined" ? "" : navigator.userAgent;
  if (/Windows/i.test(agent)) return "Windows";
  if (/Mac/i.test(agent)) return "Darwin";
  return "Linux";
}

function CommandLine({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Couldn't copy to the clipboard.");
    }
  };
  return (
    <div className="flex items-center gap-1 rounded-md border border-line bg-canvas py-1 pl-2.5 pr-1">
      <code className="min-w-0 flex-1 truncate font-mono text-2xs text-fg-muted" title={command}>
        <span className="select-none text-fg-subtle">$ </span>
        {command}
      </code>
      <Button variant="ghost" size="icon-xs" aria-label="Copy command" onClick={() => void copy()}>
        {copied ? <Check className="text-success" /> : <Copy />}
      </Button>
    </div>
  );
}

interface SetupDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  diagnostics: Diagnostics | null;
  offline: boolean;
  isInstalling: (dependency: Dependency) => boolean;
  onInstall: (dependency: Dependency) => Promise<string>;
  onRefresh: () => Promise<unknown>;
}

export function SetupDialog({ open, onOpenChange, diagnostics, offline, isInstalling, onInstall, onRefresh }: SetupDialogProps) {
  const [checking, setChecking] = useState(false);
  const platform = normalizePlatform(diagnostics?.platform);

  const install = async (dependency: Dependency) => {
    try {
      toast.success(await onInstall(dependency));
    } catch (err) {
      toast.error(errorMessage(err, "The installer couldn't be started."));
    }
  };

  const recheck = async () => {
    setChecking(true);
    try {
      await onRefresh();
    } finally {
      setChecking(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl gap-5">
        <DialogHeader>
          <DialogTitle>Set up your machine</DialogTitle>
          <DialogDescription>
            Manim Composer drives the Manim installed next to the server. Here's what it found
            {diagnostics?.platform ? ` on ${platform === "Darwin" ? "macOS" : platform}` : ""}.
          </DialogDescription>
        </DialogHeader>

        {offline ? (
          <Callout tone="danger" icon={<XCircle />}>
            The server isn't responding. Start it from the project folder with <code className="font-mono">python run.py</code>.
          </Callout>
        ) : (
          <ul className="flex flex-col divide-y divide-line overflow-y-auto rounded-lg border border-line">
            {DEPENDENCIES.map((dependency) => {
              const installed = isInstalled(diagnostics, dependency.id);
              const installing = !installed && isInstalling(dependency.id);
              const StatusIcon = installed ? CheckCircle2 : installing ? Loader2 : dependency.required ? XCircle : CircleDashed;
              return (
                <li key={dependency.id} className="flex flex-col gap-2.5 p-3.5">
                  <div className="flex items-start gap-3">
                    <StatusIcon
                      className={cn(
                        "mt-0.5 size-4 shrink-0",
                        installed ? "text-success" : installing ? "animate-spin text-accent" : dependency.required ? "text-danger" : "text-fg-subtle",
                      )}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="flex items-center gap-2 text-[13px] font-medium text-fg">
                        {dependency.name}
                        <span className="rounded bg-overlay px-1.5 py-px text-2xs font-normal text-fg-muted">
                          {dependency.required ? "Required" : "Optional"}
                        </span>
                      </p>
                      <p className="mt-0.5 text-xs leading-relaxed text-fg-muted">{dependency.description}</p>
                    </div>
                    <div className="shrink-0">
                      {installed ? (
                        <span className="text-xs font-medium text-success">Installed</span>
                      ) : installing ? (
                        <span className="text-xs text-fg-muted">Installing…</span>
                      ) : (
                        dependency.canAutoInstall(platform) && (
                          <Button size="xs" onClick={() => void install(dependency.id)}>
                            <Download />
                            {dependency.installLabel}
                          </Button>
                        )
                      )}
                    </div>
                  </div>
                  {!installed && (
                    <div className="pl-7">
                      <CommandLine command={dependency.commands[platform]} />
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}

        <DialogFooter className="flex-nowrap">
          <p className="mr-2 min-w-0 flex-1 text-2xs leading-relaxed text-fg-subtle">
            Installed something by hand? Restart the server so it picks up the new PATH.
          </p>
          <Button variant="ghost" onClick={() => void recheck()} disabled={checking}>
            <RefreshCw className={cn(checking && "animate-spin")} />
            Re-check
          </Button>
          <Button variant="primary" onClick={() => onOpenChange(false)}>
            Done
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
