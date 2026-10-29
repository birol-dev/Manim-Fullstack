import { useEffect, useId, useLayoutEffect, useRef, useState, type ComponentProps, type Ref } from "react";
import { createPortal } from "react-dom";
import { Pipette, Plus, X } from "lucide-react";
import { clamp, hexToHsv, hsvToHex, parseHex, readRecentColors, rememberColor, type HSV } from "./color";
import "./editor.css";

type EyeDropperWindow = Window & { EyeDropper?: new () => { open: (options?: { signal: AbortSignal }) => Promise<{ sRGBHex: string }> } };

/** Shared, dependency-free popover, including the table's compact swatch. */
export function ColorPickerButton({ value, onChange, swatches = [], children, ref, ...props }: Omit<ComponentProps<"button">, "value" | "onChange"> & {
  value: string; onChange: (hex: string) => void; swatches?: string[]; ref?: Ref<HTMLButtonElement>;
}) {
  const [anchor, setAnchor] = useState<HTMLButtonElement | null>(null);
  const id = useId();
  return <>
    <button {...props} ref={ref} type="button" aria-haspopup="dialog" aria-expanded={!!anchor} aria-controls={anchor ? id : undefined} onClick={(event) => setAnchor(anchor ? null : event.currentTarget)}>
      {children ?? <Plus aria-hidden className="size-4" />}
    </button>
    {anchor && <Picker id={id} anchor={anchor} value={value} onChange={onChange} swatches={swatches} onClose={() => setAnchor(null)} />}
  </>;
}

function Picker({ id, anchor, value, onChange, swatches, onClose }: { id: string; anchor: HTMLButtonElement; value: string; onChange: (hex: string) => void; swatches: string[]; onClose: () => void }) {
  const panel = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ left: 8, top: 8 });
  const [hsv, setHsv] = useState(() => hexToHsv(parseHex(value) ?? "#2563EB"));
  const [draft, setDraft] = useState(() => parseHex(value) ?? "#2563EB");
  const [recent] = useState(readRecentColors);
  const [error, setError] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);
  const chosen = useRef<string | null>(null);
  const eyedropperAbort = useRef<AbortController | null>(null);
  const closeRef = useRef(onClose);
  useEffect(() => { closeRef.current = onClose; });
  useLayoutEffect(() => {
    const place = () => {
      const a = anchor.getBoundingClientRect(), p = panel.current?.getBoundingClientRect();
      const width = p?.width || 272, height = p?.height || 370;
      setPosition({ left: Math.max(8, Math.min(a.left, window.innerWidth - width - 8)), top: a.bottom + height + 8 < window.innerHeight ? a.bottom + 8 : Math.max(8, a.top - height - 8) });
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => { window.removeEventListener("resize", place); window.removeEventListener("scroll", place, true); };
  }, [anchor, error]);
  useEffect(() => {
    panel.current?.querySelector<HTMLElement>('[role="slider"]')?.focus();
    const close = (event: PointerEvent) => { if (!panel.current?.contains(event.target as Node) && !anchor.contains(event.target as Node)) closeRef.current(); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); closeRef.current(); } };
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", escape, true);
    return () => {
      document.removeEventListener("pointerdown", close);
      document.removeEventListener("keydown", escape, true);
      eyedropperAbort.current?.abort();
      if (chosen.current) rememberColor(chosen.current);
      if (anchor.isConnected) anchor.focus();
    };
  }, [anchor]);
  const update = (next: HSV) => {
    const hex = hsvToHex(next);
    setHsv(next); setDraft(hex); setError(null); chosen.current = swatches.includes(hex) ? null : hex; onChange(hex);
  };
  const choose = (hex: string) => { update(hexToHsv(hex)); };
  const commitHex = () => {
    const hex = parseHex(draft);
    if (hex) choose(hex);
    else setError("Enter a 3 or 6 digit hex color, like #2563EB.");
  };
  const EyeDropper = (window as EyeDropperWindow).EyeDropper;
  return createPortal(<div id={id} ref={panel} role="dialog" aria-label="Color picker" className="studio-picker" style={position} onKeyDown={(event) => {
    event.stopPropagation();
    if (event.key === "Tab") {
      const stops = Array.from(panel.current!.querySelectorAll<HTMLElement>('button:not(:disabled), input, [tabindex="0"]'));
      const first = stops[0], last = stops[stops.length - 1];
      if (event.shiftKey && event.target === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && event.target === last) { event.preventDefault(); first?.focus(); }
    }
  }}>
    <div className="studio-picker-heading"><span>Custom color</span><button type="button" aria-label="Close color picker" onClick={onClose}><X aria-hidden /></button></div>
    <div role="slider" tabIndex={0} aria-label="Saturation and brightness" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(hsv.s * 100)} aria-valuetext={`Saturation ${Math.round(hsv.s * 100)}%, brightness ${Math.round(hsv.v * 100)}%. Left/right changes saturation; up/down changes brightness.`} className="studio-picker-square" style={{ backgroundColor: `hsl(${hsv.h} 100% 50%)` }}
      onPointerDown={(event) => { if (event.button !== 0) return; event.currentTarget.focus(); event.currentTarget.setPointerCapture(event.pointerId); const r = event.currentTarget.getBoundingClientRect(); update({ ...hsv, s: clamp((event.clientX - r.left) / r.width), v: clamp(1 - (event.clientY - r.top) / r.height) }); }}
      onPointerMove={(event) => { if (!event.currentTarget.hasPointerCapture(event.pointerId)) return; const r = event.currentTarget.getBoundingClientRect(); update({ ...hsv, s: clamp((event.clientX - r.left) / r.width), v: clamp(1 - (event.clientY - r.top) / r.height) }); }}
      onPointerUp={(event) => { if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }}
      onKeyDown={(event) => { const step = event.shiftKey ? .1 : .01; if (!event.key.startsWith("Arrow")) return; event.preventDefault(); update({ ...hsv, s: clamp(hsv.s + (event.key === "ArrowRight" ? step : event.key === "ArrowLeft" ? -step : 0)), v: clamp(hsv.v + (event.key === "ArrowUp" ? step : event.key === "ArrowDown" ? -step : 0)) }); }}>
      <span className="studio-picker-cursor" style={{ left: `${hsv.s * 100}%`, top: `${(1 - hsv.v) * 100}%` }} />
    </div>
    <input type="range" min={0} max={359} value={Math.round(hsv.h)} aria-label="Hue" className="studio-picker-hue" onChange={(event) => update({ ...hsv, h: Number(event.target.value) })} onKeyDown={(event) => { if (!event.key.startsWith("Arrow")) return; event.preventDefault(); update({ ...hsv, h: clamp(hsv.h + ((event.key === "ArrowLeft" || event.key === "ArrowDown") ? -1 : 1) * (event.shiftKey ? 10 : 1), 0, 359) }); }} />
    <div className="studio-picker-code-row"><label htmlFor={`${id}-hex`}>Hex</label><input id={`${id}-hex`} value={draft} maxLength={7} spellCheck={false} aria-invalid={!!error} aria-describedby={error ? `${id}-error` : undefined} onChange={(event) => {
        const text = event.target.value;
        setDraft(text);
        const hex = parseHex(text);
        if (hex) { setHsv(hexToHsv(hex)); setError(null); chosen.current = swatches.includes(hex) ? null : hex; onChange(hex); }
      }} onBlur={commitHex} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); commitHex(); } }} />
      {EyeDropper && <button type="button" disabled={picking} aria-label="Pick color from screen" onClick={async () => { const controller = new AbortController(); eyedropperAbort.current = controller; setPicking(true); try { const result = await new EyeDropper().open({ signal: controller.signal }); const hex = parseHex(result.sRGBHex); if (!controller.signal.aborted && hex) choose(hex); } catch (err) { if (!controller.signal.aborted && (err as Error).name !== "AbortError") setError("Couldn't pick that color. Try again."); } finally { if (!controller.signal.aborted) setPicking(false); } }}><Pipette aria-hidden /></button>}
    </div>
    {error && <p id={`${id}-error`} role="alert" className="studio-picker-error">{error}</p>}
    {swatches.length > 0 && <div className="studio-picker-palette"><span>Theme colors</span><div>{swatches.map((hex) => <button key={hex} type="button" style={{ background: hex }} aria-label={`Theme ${hex}`} onClick={() => choose(hex)} />)}</div></div>}
    <div className="studio-picker-palette"><span>Recent</span><div>{recent.length ? recent.map((hex) => <button key={hex} type="button" style={{ background: hex }} aria-label={`Recent ${hex}`} onClick={() => choose(hex)} />) : <p>Your custom colors will appear here.</p>}</div></div>
  </div>, document.body);
}
