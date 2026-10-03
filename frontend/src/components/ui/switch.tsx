import { cn } from "@/lib/utils";

interface SwitchProps {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
  id?: string;
  "aria-label"?: string;
  "aria-labelledby"?: string;
  "aria-describedby"?: string;
  className?: string;
}

function Switch({ checked, onCheckedChange, disabled, className, ...aria }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        "relative inline-flex h-[18px] w-8 shrink-0 cursor-pointer items-center rounded-full border transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-45",
        checked ? "border-accent bg-accent" : "border-line-strong bg-raised hover:border-[#3d3d47]",
        className,
      )}
      {...aria}
    >
      <span
        aria-hidden
        className={cn(
          "pointer-events-none block size-3 rounded-full shadow-sm transition-transform duration-150",
          checked ? "translate-x-[15px] bg-accent-fg" : "translate-x-[2px] bg-fg-muted",
        )}
      />
    </button>
  );
}

export { Switch };
