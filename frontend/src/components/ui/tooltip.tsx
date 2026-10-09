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
  align?: "start" | "center" | "end";
  /** Gap between the trigger and the hint, in px (default 6). */
  sideOffset?: number;
  /**
   * Wrap the trigger in a span. Needed when the child can be disabled: a
   * disabled button gets no pointer events, so the hint would never show.
   */
  wrap?: boolean;
  /** Extra classes for the `wrap` span (e.g. "flex w-full" for a full-width button). */
  wrapClassName?: string;
  children: React.ReactElement;
}

/** Hover / Tab-focus hint for icon buttons. Renders the child as the trigger. */
function Tooltip({ content, shortcut, side = "bottom", align = "center", sideOffset = 6, wrap = false, wrapClassName, children }: TooltipProps) {
  const [open, setOpen] = React.useState(false);
  // Typed as Radix wants; with `wrap` it is really the span.
  const triggerRef = React.useRef<HTMLButtonElement>(null);
  const hovered = React.useRef(false);
  // A click dismisses the hint until the pointer leaves; otherwise the next pointer
  // move reopens it (the "lingering Download tooltip" after a click).
  const clicked = React.useRef(false);
  const close = React.useCallback(() => setOpen(false), []);

  React.useEffect(() => {
    if (!open) return;
    if (closeOpenTooltip && closeOpenTooltip !== close) closeOpenTooltip();
    closeOpenTooltip = close;
    // A missed pointerleave (the trigger re-rendered, turned disabled, or moved under a resting
    // pointer) left the blocked-Render hint up after the pointer had gone: any pointer move or
    // press outside the trigger closes a hover-opened hint.
    const outside = (event: PointerEvent) => {
      const trigger = triggerRef.current;
      if (!hovered.current || !trigger) return;
      if (event.target instanceof Node && trigger.contains(event.target)) return;
      const box = trigger.getBoundingClientRect();
      if (event.clientX >= box.left && event.clientX <= box.right && event.clientY >= box.top && event.clientY <= box.bottom) return;
      hovered.current = false;
      close();
    };
    window.addEventListener("blur", close);
    window.addEventListener("scroll", close, true);
    document.addEventListener("pointermove", outside, true);
    document.addEventListener("pointerdown", outside, true);
    return () => {
      window.removeEventListener("blur", close);
      window.removeEventListener("scroll", close, true);
      document.removeEventListener("pointermove", outside, true);
      document.removeEventListener("pointerdown", outside, true);
      if (closeOpenTooltip === close) closeOpenTooltip = null;
    };
  }, [open, close]);

  const onOpenChange = (next: boolean) => {
    // Opening without the pointer over the trigger means focus did it; allow that only right after Tab.
    if (next && !hovered.current && !focusFromTab) return;
    if (next && clicked.current) return;
    setOpen(next);
  };

  const trigger = wrap ? (
    <span className={cn("inline-flex shrink-0 [&>button:disabled]:pointer-events-none", wrapClassName)}>{children}</span>
  ) : (
    children
  );

  return (
    // disableHoverableContent: the hint is pointer-events-none, so Radix's "pointer in transit to
    // the content" grace area only blocked the neighbouring button's tooltip (Rename -> Delete).
    <TooltipPrimitive.Root open={open} onOpenChange={onOpenChange} disableHoverableContent>
      <TooltipPrimitive.Trigger
        asChild
        ref={triggerRef}
        onPointerEnter={() => (hovered.current = true)}
        // A trigger mounted under a resting pointer (Render turning into Cancel) gets no
        // pointerenter until it leaves; the first move counts as hovering.
        onPointerMove={() => (hovered.current = true)}
        onPointerLeave={() => {
          hovered.current = false;
          clicked.current = false;
          close();
        }}
        onPointerDown={() => {
          clicked.current = true;
          close();
        }}
        onBlur={() => {
          clicked.current = false;
          close();
        }}
      >
        {trigger}
      </TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          side={side}
          align={align}
          sideOffset={sideOffset}
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
