import type { ReactNode } from "react";

import { PaneHeader, PaneTitle } from "@/components/ui/panel";

interface SidebarPanelProps {
  title: string;
  actions?: ReactNode;
  children: ReactNode;
}

export function SidebarPanel({ title, actions, children }: SidebarPanelProps) {
  return (
    <div className="flex h-full min-h-0 flex-col bg-surface">
      <PaneHeader className="h-10 justify-between pr-1.5">
        <PaneTitle>{title}</PaneTitle>
        {actions && <div className="flex items-center gap-0.5">{actions}</div>}
      </PaneHeader>
      <div className="min-h-0 min-w-0 flex-1 overflow-y-auto overflow-x-hidden p-2">{children}</div>
    </div>
  );
}

export function RowActions({ children }: { children: ReactNode }) {
  return (
    <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
      {children}
    </div>
  );
}
