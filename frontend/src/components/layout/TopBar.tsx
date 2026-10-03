import { BookOpen, Wrench } from "lucide-react";

import { Logo } from "@/components/brand/Logo";
import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";

interface TopBarProps {
  needsSetup: boolean;
  onOpenSetup: () => void;
}

const DOCS_URL = "https://docs.manim.community/en/stable/reference.html";

export function TopBar({ needsSetup, onOpenSetup }: TopBarProps) {
  return (
    <header className="flex h-11 shrink-0 items-center justify-between border-b border-line bg-surface pl-3 pr-2">
      <div className="flex items-center gap-2.5">
        <Logo className="h-5 w-6" />
        <h1 className="text-[13px] font-semibold tracking-tight text-fg">Manim Composer</h1>
      </div>

      <div className="flex items-center gap-1">
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
