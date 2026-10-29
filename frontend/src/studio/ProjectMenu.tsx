import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { Copy, MoreHorizontal, Pencil, Trash2 } from "lucide-react";

export interface MenuItem {
  label: string;
  icon: ReactNode;
  href?: string;
  download?: string | boolean;
  danger?: boolean;
  onSelect?: () => void;
}

/**
 * Small, keyboard-operated menu kept outside the card's navigation link. The menu itself is
 * placed with fixed coordinates so scroll containers cannot clip it.
 */
export function ActionMenu({ title, disabled = false, items, className = "studio-project-menu" }: { title: string; disabled?: boolean; items: MenuItem[]; className?: string }) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null);
  const container = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const entries = useRef<Array<HTMLElement | null>>([]);
  const openingIndex = useRef(0);
  const id = useId();

  const place = useCallback(() => {
    const anchor = trigger.current?.getBoundingClientRect();
    if (!anchor) return;
    const rect = content.current?.getBoundingClientRect();
    const width = rect?.width || 168;
    const height = rect?.height || 0;
    const left = Math.max(8, Math.min(anchor.right - width, window.innerWidth - width - 8));
    const below = anchor.bottom + 6;
    const top = height && below + height > window.innerHeight - 8 ? Math.max(8, anchor.top - height - 6) : below;
    setPosition({ top, left });
  }, []);

  useLayoutEffect(() => {
    if (open) place();
  }, [open, place]);

  useEffect(() => {
    if (!open) return;
    entries.current[openingIndex.current]?.focus();
    const outside = (event: PointerEvent) => { if (event.target instanceof Node && !container.current?.contains(event.target)) setOpen(false); };
    document.addEventListener("pointerdown", outside);
    window.addEventListener("resize", place);
    document.addEventListener("scroll", place, true);
    return () => {
      document.removeEventListener("pointerdown", outside);
      window.removeEventListener("resize", place);
      document.removeEventListener("scroll", place, true);
    };
  }, [open, place]);

  const count = items.length;
  const keydown = (event: KeyboardEvent) => {
    if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); setOpen(false); trigger.current?.focus(); return; }
    if (event.key === "Tab") { trigger.current?.focus(); setOpen(false); return; }
    // Links do not activate with Space the way buttons do.
    if (event.key === " " && document.activeElement instanceof HTMLAnchorElement) { event.preventDefault(); document.activeElement.click(); return; }
    const current = entries.current.indexOf(document.activeElement as HTMLElement);
    const next = event.key === "ArrowDown" ? (current + 1) % count : event.key === "ArrowUp" ? (current + count - 1) % count : event.key === "Home" ? 0 : event.key === "End" ? count - 1 : -1;
    if (next >= 0) { event.preventDefault(); entries.current[next]?.focus(); }
  };
  return <div ref={container} className={className} onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false); }}>
    <button ref={trigger} type="button" className="studio-shell-icon" aria-label={`Options for ${title}`} aria-haspopup="menu" aria-expanded={open} aria-controls={open ? id : undefined} disabled={disabled} onClick={() => { openingIndex.current = 0; setOpen((value) => !value); }} onKeyDown={(event) => {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); openingIndex.current = event.key === "ArrowUp" ? 2 : 0; setOpen(true); }
    }}><MoreHorizontal /></button>
    {open && <div ref={content} id={id} role="menu" aria-label={`Actions for ${title}`} className="studio-project-menu-content" style={{ top: position?.top ?? 0, left: position?.left ?? 0, visibility: position ? "visible" : "hidden" }} onKeyDown={keydown}>
      {items.map((item, index) => {
        const common = {
          ref: (node: HTMLElement | null) => { entries.current[index] = node; },
          role: "menuitem",
          tabIndex: -1,
          "data-danger": item.danger || undefined,
          onClick: () => { setOpen(false); trigger.current?.focus(); item.onSelect?.(); },
        };
        return item.href
          ? <a key={item.label} {...common} href={item.href} download={item.download}>{item.icon}{item.label}</a>
          : <button key={item.label} {...common} type="button">{item.icon}{item.label}</button>;
      })}
    </div>}
  </div>;
}

/** The saved video's actions. */
export function ProjectMenu({ title, disabled, onRename, onDuplicate, onDelete }: { title: string; disabled: boolean; onRename: () => void; onDuplicate: () => void; onDelete: () => void }) {
  return <ActionMenu title={title} disabled={disabled} items={[
    { label: "Rename", icon: <Pencil aria-hidden />, onSelect: onRename },
    { label: "Duplicate", icon: <Copy aria-hidden />, onSelect: onDuplicate },
    { label: "Delete", icon: <Trash2 aria-hidden />, danger: true, onSelect: onDelete },
  ]} />;
}
