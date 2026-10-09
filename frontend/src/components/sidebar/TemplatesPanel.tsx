import { FilePlus2, Replace } from "lucide-react";

import { Button } from "@/components/ui/button";
import { SCENE_TEMPLATES, type SceneTemplate } from "@/lib/templates";
import { cn } from "@/lib/utils";
import { SidebarPanel } from "./SidebarPanel";

interface TemplatesPanelProps {
  latexAvailable: boolean;
  canReplace: boolean;
  onCreateFrom: (template: SceneTemplate) => void;
  onReplaceWith: (template: SceneTemplate) => void;
}

export function TemplatesPanel({ latexAvailable, canReplace, onCreateFrom, onReplaceWith }: TemplatesPanelProps) {
  return (
    <SidebarPanel title="Templates">
      <p className="mb-2 px-1 text-xs leading-relaxed text-fg-subtle">
        Complete, ready-to-render scenes. Start a new file from one, or swap it into the open editor.
      </p>
      <ul className="flex flex-col gap-2">
        {SCENE_TEMPLATES.map((template) => (
          <li key={template.id} className="min-w-0 overflow-hidden rounded-lg border border-line bg-raised/40 p-3 transition-colors hover:border-line-strong">
            <div className="mb-1 flex items-center justify-between gap-2">
              <h3 className="truncate text-[13px] font-medium text-fg">{template.title}</h3>
              <span
                className={cn(
                  "shrink-0 rounded px-1.5 py-px text-2xs font-medium",
                  template.needsLatex && !latexAvailable ? "bg-warning-soft text-warning" : "bg-overlay text-fg-muted",
                )}
                title={template.needsLatex && !latexAvailable ? "Needs a LaTeX install to render" : undefined}
              >
                {template.needsLatex && !latexAvailable ? "Needs LaTeX" : template.category}
              </span>
            </div>
            <p className="mb-3 break-words text-xs leading-relaxed text-fg-muted">{template.description}</p>
            <div className="flex gap-1.5">
              <Button size="xs" onClick={() => onCreateFrom(template)}>
                <FilePlus2 />
                New file
              </Button>
              <Button size="xs" variant="ghost" disabled={!canReplace} onClick={() => onReplaceWith(template)}>
                <Replace />
                Replace current
              </Button>
            </div>
          </li>
        ))}
      </ul>
    </SidebarPanel>
  );
}
