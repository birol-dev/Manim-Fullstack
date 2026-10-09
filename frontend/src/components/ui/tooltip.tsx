import * as React from "react";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";

import { cn } from "@/lib/utils";

const TooltipProvider = TooltipPrimitive.Provider;

// ---- Which input moved focus last ------------------------------------------
// Radix opens a tooltip whenever its trigger gains focus. Focus also moves for
// other reasons: it comes back after a click, when the window regains focus
// after "Open in new tab", when a dialog closes (Escape restores focus to its
// trigger), or when the editor hands focus on (Escape / Ctrl+M moves it to the
// next control). Those left "ghost" tooltips open with no pointer nearby. Only
// focus that follows a Tab key press opens one.
let focusFromTab = false;
if (typeof window !== "undefined") {
  window.addEventListener("keydown", (event) => (focusFromTab = event.key === "Tab"), true);
  window.addEventListener("pointerdown", () => (focusFromTab = false), true);
}

/** Closes whichever tooltip is open, so two can never be visible at once. */
let closeOpenTooltip: (() => void) | null = null;

interface TooltipProps {
  content: React.ReactNode;
  /** Keyboard shortcut shown after the label, e.g. "Ctrl+S". */
  shortcut?: string;
  side?: "top" | "right" | "bottom" | "left";
  /**
   * Wrap the trigger in a span. Needed when the child can be disabled: a
   * disabled button gets no pointer events, so the hint would never show.
   */
  wrap?: boolean;
  children: React.ReactElement;
}

/** Hover / Tab-focus hint for icon buttons. Renders the child as the trigger. */
function Tooltip({ content, shortcut, side = "bottom", wrap = false, children }: TooltipProps) {
  const [open, setOpen] = React.useState(false);
  const hovered = React.useRef(false);
  const close = React.useCallback(() => setOpen(false), []);

  React.useEffect(() => {
    if (!open) return;
    if (closeOpenTooltip && closeOpenTooltip !== close) closeOpenTooltip();
    closeOpenTooltip = close;
    window.addEventListener("blur", close);
    window.addEventListener("scroll", close, true);
    return () => {
      window.removeEventListener("blur", close);
      window.removeEventListener("scroll", close, true);
      if (closeOpenTooltip === close) closeOpenTooltip = null;
    };
  }, [open, close]);

  const onOpenChange = (next: boolean) => {
    // Opening without the pointer over the trigger means focus did it; allow that only right after Tab.
    if (next && !hovered.current && !focusFromTab) return;
    setOpen(next);
  };

  const trigger = wrap ? (
    <span className="inline-flex shrink-0 [&>button:disabled]:pointer-events-none">{children}</span>
  ) : (
    children
  );

  return (
    <TooltipPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <TooltipPrimitive.Trigger
        asChild
        onPointerEnter={() => (hovered.current = true)}
        onPointerLeave={() => {
          hovered.current = false;
          close();
        }}
        onPointerDown={close}
        onBlur={close}
      >
        {trigger}
      </TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          side={side}
          sideOffset={6}
          collisionPadding={8}
          className={cn(
            "pointer-events-none z-50 flex max-w-72 items-center gap-2 rounded-md border border-line-strong bg-overlay px-2 py-1 text-2xs font-medium text-fg shadow-popover",
            "data-[state=delayed-open]:animate-in data-[state=delayed-open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0",
          )}
        >
          {content}
          {shortcut && <kbd className="font-sans text-fg-subtle">{shortcut}</kbd>}
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}

export { Tooltip, TooltipProvider };
