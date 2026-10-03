import { Cpu, Files, ImagePlus, LayoutTemplate, Settings, Shapes, Sigma, type LucideIcon } from "lucide-react";

import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export type SidebarView = "files" | "templates" | "shapes" | "latex" | "assets" | "system" | "settings";

const PRIMARY: Array<{ id: SidebarView; label: string; icon: LucideIcon }> = [
  { id: "files", label: "Files", icon: Files },
  { id: "templates", label: "Templates", icon: LayoutTemplate },
  { id: "shapes", label: "Shape builder", icon: Shapes },
  { id: "latex", label: "LaTeX", icon: Sigma },
  { id: "assets", label: "Assets", icon: ImagePlus },
];

const SECONDARY: Array<{ id: SidebarView; label: string; icon: LucideIcon }> = [
  { id: "system", label: "System", icon: Cpu },
  { id: "settings", label: "Settings", icon: Settings },
];

interface ActivityBarProps {
  view: SidebarView;
  open: boolean;
  /** Views that should show an attention dot. */
  badges?: Partial<Record<SidebarView, boolean>>;
  onSelect: (view: SidebarView) => void;
}

export function ActivityBar({ view, open, badges = {}, onSelect }: ActivityBarProps) {
  const item = ({ id, label, icon: Icon }: (typeof PRIMARY)[number]) => {
    const active = open && view === id;
    return (
      <Tooltip key={id} content={label} side="right">
        <button
          type="button"
          aria-label={label}
          aria-pressed={active}
          onClick={() => onSelect(id)}
          className={cn(
            "relative flex size-10 items-center justify-center rounded-md transition-colors",
            active ? "text-fg" : "text-fg-subtle hover:bg-raised hover:text-fg-muted",
          )}
        >
          {active && <span className="absolute -left-1 top-2 bottom-2 w-0.5 rounded-full bg-accent" />}
          <Icon className="size-[18px]" strokeWidth={1.75} />
          {badges[id] && <span className="absolute right-2 top-2 size-1.5 rounded-full bg-warning" />}
        </button>
      </Tooltip>
    );
  };

  return (
    <nav
      aria-label="Sidebar views"
      className="flex w-12 shrink-0 flex-col items-center justify-between border-r border-line bg-surface py-1.5"
    >
      <div className="flex flex-col items-center gap-0.5">{PRIMARY.map(item)}</div>
      <div className="flex flex-col items-center gap-0.5">{SECONDARY.map(item)}</div>
    </nav>
  );
}
