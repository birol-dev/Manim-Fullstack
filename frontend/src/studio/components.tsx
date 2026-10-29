/** Small building blocks shared by the studio's pages. */
import { useRef, type CSSProperties, type KeyboardEvent, type ReactNode } from "react";
import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

import { iconUrl } from "./api";

export const inputClass =
  "studio-input w-full rounded-lg border border-line-strong bg-surface px-3 text-sm text-fg placeholder:text-fg-subtle transition-colors hover:border-fg-subtle focus-visible:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 disabled:cursor-not-allowed disabled:opacity-50 aria-[invalid=true]:border-danger aria-[invalid=true]:ring-danger/20";

interface SegmentsProps<T extends string> {
  value: T | null;
  options: Array<{ value: T; label: ReactNode; title?: string }>;
  onChange: (value: T) => void;
  "aria-label"?: string;
  "aria-labelledby"?: string;
  "aria-describedby"?: string;
  invalid?: boolean;
  className?: string;
  size?: "sm" | "md";
}

/** A radio group drawn as a segmented control, with arrow-key navigation (one tab stop). */
export function Segments<T extends string>({ value, options, onChange, invalid, className, size = "md", ...aria }: SegmentsProps<T>) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const activeIndex = options.findIndex((option) => option.value === value);
  const onKeyDown = (event: KeyboardEvent, index: number) => {
    const delta = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 0;
    let next = index + delta;
    if (event.key === "Home") next = 0;
    else if (event.key === "End") next = options.length - 1;
    else if (!delta) return;
    event.preventDefault();
    next = (next + options.length) % options.length;
    onChange(options[next].value);
    refs.current[next]?.focus();
  };
  return (
    <div
      role="radiogroup"
      aria-invalid={invalid || undefined}
      className={cn(
        "studio-segments flex min-w-0 gap-0.5 rounded-lg border border-line-strong bg-canvas p-0.5",
        invalid && "border-danger",
        className,
      )}
      {...aria}
    >
      {options.map((option, index) => {
        const active = index === activeIndex;
        return (
          <button
            key={option.value}
            ref={(element) => {
              refs.current[index] = element;
            }}
            type="button"
            role="radio"
            aria-checked={active}
            title={option.title}
            tabIndex={active || (activeIndex === -1 && index === 0) ? 0 : -1}
            onClick={() => onChange(option.value)}
            onKeyDown={(event) => onKeyDown(event, index)}
            className={cn(
              "flex min-w-0 flex-1 items-center justify-center gap-1.5 overflow-hidden whitespace-nowrap rounded-md px-2.5 font-medium transition-colors focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent",
              size === "md" ? "h-8 text-[13px]" : "h-7 text-xs",
              active ? "bg-overlay text-fg shadow-sm ring-1 ring-line-strong" : "text-fg-subtle hover:text-fg-muted",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

/** A bundled icon, drawn in the current text color. */
export function StudioIcon({ name, className, style }: { name: string; className?: string; style?: CSSProperties }) {
  return (
    <span
      aria-hidden
      className={cn("studio-icon size-6", className)}
      style={{ ...style, ["--icon" as string]: `url("${iconUrl(name)}")` }}
    />
  );
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 aria-hidden className={cn("size-4 animate-spin", className)} />;
}

/** A little frame in the shape of an aspect ratio (the format picker's icons). */
export function FrameIcon({ w, h, className }: { w: number; h: number; className?: string }) {
  const scale = 14 / Math.max(w, h);
  return (
    <span aria-hidden className={cn("inline-flex size-4 items-center justify-center", className)}>
      <span
        className="block rounded-[2px] border-[1.5px] border-current"
        style={{ width: Math.max(6, w * scale), height: Math.max(6, h * scale) }}
      />
    </span>
  );
}

export function SectionHeading({ children, action, id }: { children: ReactNode; action?: ReactNode; id?: string }) {
  return (
    <div className="flex items-end justify-between gap-3">
      <h2 id={id} className="studio-section-title text-base font-semibold tracking-tight text-fg">
        {children}
      </h2>
      {action}
    </div>
  );
}
