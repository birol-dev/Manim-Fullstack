import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { Copy, MoreHorizontal, Pencil, Trash2 } from "lucide-react";

/** Small, keyboard-operated menu kept outside the card's navigation link. */
export function ProjectMenu({ title, disabled, onRename, onDuplicate, onDelete }: { title: string; disabled: boolean; onRename: () => void; onDuplicate: () => void; onDelete: () => void }) {
  const [open, setOpen] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const items = useRef<Array<HTMLButtonElement | null>>([]);
  const openingIndex = useRef(0);
  const id = useId();
  useEffect(() => {
    if (!open) return;
    items.current[openingIndex.current]?.focus();
    const outside = (event: PointerEvent) => { if (event.target instanceof Node && !container.current?.contains(event.target)) setOpen(false); };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);
  const keydown = (event: KeyboardEvent) => {
    if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); setOpen(false); trigger.current?.focus(); return; }
    if (event.key === "Tab") { trigger.current?.focus(); setOpen(false); return; }
    const current = items.current.indexOf(document.activeElement as HTMLButtonElement);
    const next = event.key === "ArrowDown" ? (current + 1) % 3 : event.key === "ArrowUp" ? (current + 2) % 3 : event.key === "Home" ? 0 : event.key === "End" ? 2 : -1;
    if (next >= 0) { event.preventDefault(); items.current[next]?.focus(); }
  };
  return <div ref={container} className="studio-project-menu" onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false); }}>
    <button ref={trigger} type="button" className="studio-shell-icon" aria-label={`Options for ${title}`} aria-haspopup="menu" aria-expanded={open} aria-controls={open ? id : undefined} disabled={disabled} onClick={() => { openingIndex.current = 0; setOpen((value) => !value); }} onKeyDown={(event) => {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); openingIndex.current = event.key === "ArrowUp" ? 2 : 0; setOpen(true); }
    }}><MoreHorizontal /></button>
    {open && <div id={id} role="menu" aria-label={`Actions for ${title}`} className="studio-project-menu-content" onKeyDown={keydown}>
      {[
        { label: "Rename", Icon: Pencil, action: onRename },
        { label: "Duplicate", Icon: Copy, action: onDuplicate },
        { label: "Delete", Icon: Trash2, action: onDelete },
      ].map(({ label, Icon, action }, index) => <button key={label} ref={(node) => { items.current[index] = node; }} type="button" role="menuitem" tabIndex={-1} data-danger={label === "Delete" || undefined} onClick={() => { setOpen(false); trigger.current?.focus(); action(); }}><Icon aria-hidden />{label}</button>)}
    </div>}
  </div>;
}
