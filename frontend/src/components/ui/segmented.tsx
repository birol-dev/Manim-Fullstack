import { cn } from "@/lib/utils";

interface SegmentedOption<T extends string> {
  value: T;
  label: React.ReactNode;
}

interface SegmentedProps<T extends string> {
  value: T;
  onChange: (value: T) => void;
  options: SegmentedOption<T>[];
  "aria-label": string;
  className?: string;
}

/** A compact radio group styled as a segmented control. */
function Segmented<T extends string>({ value, onChange, options, className, ...aria }: SegmentedProps<T>) {
  return (
    <div role="radiogroup" className={cn("@container flex min-w-0 rounded-md border border-line-strong bg-canvas p-0.5", className)} {...aria}>
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(option.value)}
            className={cn(
              "flex h-6 min-w-0 flex-1 items-center justify-center gap-1.5 overflow-hidden whitespace-nowrap rounded-[4px] px-2 text-xs font-medium transition-colors [&_svg]:size-3.5 [&_svg]:shrink-0",
              // Narrow sidebars: drop the icons before the labels would clip.
              "@max-[210px]:gap-0 @max-[210px]:px-1.5 @max-[210px]:[&_svg]:hidden",
              active ? "bg-overlay text-fg shadow-sm" : "text-fg-subtle hover:text-fg-muted",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

export { Segmented };
