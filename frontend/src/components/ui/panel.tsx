import * as React from "react";

import { cn } from "@/lib/utils";

/** Fixed-height header strip at the top of a pane. */
function PaneHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("flex h-9 shrink-0 items-center gap-2 border-b border-line bg-surface px-3", className)}
      {...props}
    />
  );
}

/** Small uppercase title used for panes and sidebar sections. */
function PaneTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h2
      className={cn("truncate text-2xs font-semibold uppercase tracking-[0.08em] text-fg-muted", className)}
      {...props}
    />
  );
}

interface SectionProps {
  title: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}

function Section({ title, actions, className, children }: SectionProps) {
  return (
    <section className={cn("flex flex-col gap-1.5", className)}>
      <div className="flex h-6 items-center justify-between gap-2 px-1">
        <h3 className="text-2xs font-semibold uppercase tracking-[0.08em] text-fg-subtle">{title}</h3>
        {actions && <div className="flex items-center gap-0.5">{actions}</div>}
      </div>
      {children}
    </section>
  );
}

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}

function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-2 px-6 py-8 text-center", className)}>
      {icon && <div className="mb-1 text-fg-subtle [&_svg]:size-6">{icon}</div>}
      <p className="text-[13px] font-medium text-fg-muted">{title}</p>
      {description && <p className="max-w-72 text-xs leading-relaxed text-fg-subtle">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

type CalloutTone = "info" | "warning" | "danger";

const calloutTones: Record<CalloutTone, string> = {
  info: "border-accent/25 bg-accent-soft text-fg-muted [&_svg]:text-accent",
  warning: "border-warning/25 bg-warning-soft text-fg-muted [&_svg]:text-warning",
  danger: "border-danger/25 bg-danger-soft text-fg-muted [&_svg]:text-danger",
};

interface CalloutProps {
  tone?: CalloutTone;
  icon?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}

function Callout({ tone = "info", icon, className, children }: CalloutProps) {
  return (
    <div className={cn("flex gap-2 rounded-lg border px-2.5 py-2 text-xs leading-relaxed", calloutTones[tone], className)}>
      {icon && <span className="mt-px shrink-0 [&_svg]:size-3.5">{icon}</span>}
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

function Kbd({ className, ...props }: React.HTMLAttributes<HTMLElement>) {
  return (
    <kbd
      className={cn(
        "inline-flex h-[18px] min-w-[18px] items-center justify-center rounded border border-line-strong bg-raised px-1 font-sans text-2xs font-medium text-fg-muted",
        className,
      )}
      {...props}
    />
  );
}

export { PaneHeader, PaneTitle, Section, EmptyState, Callout, Kbd };
