import { BookOpen, CircleHelp, LayoutGrid, Wrench } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import { StudioMark } from "@/studio/StudioMark";

interface TopBarProps {
  design?: boolean;
  needsSetup: boolean;
  onOpenSetup: () => void;
  onOpenGuide: () => void;
}

const DOCS_URL = "https://docs.manim.community/en/stable/reference.html";

export function TopBar({ design, needsSetup, onOpenSetup, onOpenGuide }: TopBarProps) {
  return (
    <header className="author-topbar flex h-11 shrink-0 items-center justify-between gap-3 border-b border-line bg-surface pl-3 pr-2">
      <div className="flex min-w-0 items-center gap-2.5">
        <span className="author-mark"><StudioMark /></span>
        <h1 className="author-title truncate">{design ? "Design Studio" : "Author mode"}</h1>
        <span className="author-brand-label hidden sm:inline">Manim Studio</span>
      </div>

      <div className="flex shrink-0 items-center gap-1">
        <Button variant="secondary" size="sm" onClick={onOpenGuide}>
          <CircleHelp />
          Quick guide
        </Button>
        {/* A full page load (not a hash change), so the unsaved-changes guard still asks first. */}
        <Button asChild variant="ghost" size="sm">
          <a href={import.meta.env.BASE_URL}>
            <LayoutGrid />
            Back to Studio
          </a>
        </Button>
        <Tooltip content="Manim reference docs">
          <Button asChild variant="ghost" size="icon-sm" aria-label="Manim reference docs">
            <a href={DOCS_URL} target="_blank" rel="noreferrer">
              <BookOpen />
            </a>
          </Button>
        </Tooltip>
        <Button variant="ghost" size="sm" onClick={onOpenSetup} className="relative">
          <Wrench />
          Setup
          {needsSetup && (
            <span className="absolute right-1 top-1 size-1.5 rounded-full bg-warning" aria-label="Setup needs attention" />
          )}
        </Button>
      </div>
    </header>
  );
}
