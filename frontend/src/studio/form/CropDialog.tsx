import { useEffect, useRef, useState } from "react";
import { RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { assetUrl, friendlyError } from "../api";
import { Spinner } from "../components";
import { clamp } from "../color";
import { cropGeometry, cropPhoto, cropRatio, RESET_CROP } from "./crop";
import "../editor.css";

export function CropDialog({ name, shape, onClose, onConfirm }: { name: string; shape?: string; onClose: () => void; onConfirm: (file: File) => Promise<void> }) {
  const image = useRef<HTMLImageElement>(null);
  const [dimensions, setDimensions] = useState<{ width: number; height: number } | null>(null);
  const [position, setPosition] = useState(RESET_CROP);
  const [freeRatio, setFreeRatio] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [loadVersion, setLoadVersion] = useState(0);
  const live = useRef(true);
  useEffect(() => { live.current = true; return () => { live.current = false; }; }, []);
  const drag = useRef<{ x: number; y: number; startX: number; startY: number } | null>(null);
  const ratio = freeRatio ?? cropRatio(shape, dimensions ? dimensions.width / dimensions.height : 1);
  const rect = dimensions ? cropGeometry(dimensions.width, dimensions.height, ratio, position) : null;
  const reset = () => { setPosition(RESET_CROP); setFreeRatio(null); };
  return <Dialog open onOpenChange={(open) => { if (!open && !busy) { live.current = false; onClose(); } }}>
    <DialogContent className="studio-crop-dialog" onEscapeKeyDown={(event) => { if (busy) event.preventDefault(); }} onPointerDownOutside={(event) => { if (busy) event.preventDefault(); }}>
      <DialogHeader><DialogTitle>Adjust photo</DialogTitle><DialogDescription>Drag to position your photo. Use the arrow keys for small adjustments.</DialogDescription></DialogHeader>
      <div className="studio-crop-stage">
        <div className="studio-crop-mask" data-circle={shape === "circle" || undefined} style={{ aspectRatio: String(ratio), maxWidth: Math.min(340, 300 * ratio) }} role="group" tabIndex={0} aria-label="Photo position" aria-describedby="studio-crop-position-help" aria-disabled={busy}
          onPointerDown={(event) => { if (busy || !dimensions || event.button !== 0) return; event.currentTarget.focus(); event.currentTarget.setPointerCapture(event.pointerId); drag.current = { x: event.clientX, y: event.clientY, startX: position.x, startY: position.y }; }}
          onPointerMove={(event) => { if (!drag.current || !event.currentTarget.hasPointerCapture(event.pointerId) || !rect || !dimensions) return; const bounds = event.currentTarget.getBoundingClientRect(); const dx = (dimensions.width / rect.width - 1) * bounds.width / 2; const dy = (dimensions.height / rect.height - 1) * bounds.height / 2; setPosition((prev) => ({ ...prev, x: dx ? clamp(drag.current!.startX - (event.clientX - drag.current!.x) / dx, -1, 1) : 0, y: dy ? clamp(drag.current!.startY - (event.clientY - drag.current!.y) / dy, -1, 1) : 0 })); }}
          onPointerUp={(event) => { drag.current = null; if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }} onPointerCancel={() => { drag.current = null; }}
          onKeyDown={(event) => { if (busy || !event.key.startsWith("Arrow")) return; event.preventDefault(); const step = event.shiftKey ? .1 : .02; setPosition((p) => ({ ...p, x: clamp(p.x + (event.key === "ArrowLeft" ? step : event.key === "ArrowRight" ? -step : 0), -1, 1), y: clamp(p.y + (event.key === "ArrowUp" ? step : event.key === "ArrowDown" ? -step : 0), -1, 1) })); }}>
          <img key={loadVersion} ref={image} crossOrigin="anonymous" src={assetUrl(name)} alt="Photo to crop" draggable={false} onLoad={(event) => { const img = event.currentTarget; if (!img.naturalWidth || !img.naturalHeight) { setLoadFailed(true); return; } setDimensions({ width: img.naturalWidth, height: img.naturalHeight }); setLoadFailed(false); }} onError={() => { setLoadFailed(true); }} style={dimensions && rect ? { width: `${dimensions.width / rect.width * 100}%`, height: `${dimensions.height / rect.height * 100}%`, left: `${-rect.x / rect.width * 100}%`, top: `${-rect.y / rect.height * 100}%` } : { visibility: "hidden" }} />
          {!dimensions && !loadFailed && <span className="studio-crop-loading" role="status"><Spinner /> Loading photo?</span>}
        </div>
      </div>
      <p id="studio-crop-position-help" className="studio-crop-help">{shape === "circle" ? "The circle shows what will appear in your video." : "The frame shows what will appear in your video."} Shift + arrow moves farther.</p>
      {(!shape || shape === "free") && <label className="studio-crop-slider">Crop width <span>{ratio.toFixed(2)}:1</span><input type="range" min={.25} max={4} step={.01} value={clamp(ratio, .25, 4)} disabled={busy || !dimensions} onChange={(event) => { setFreeRatio(Number(event.target.value)); setPosition(RESET_CROP); }} /></label>}
      <label className="studio-crop-slider">Zoom <span>{position.zoom.toFixed(1)}?</span><input type="range" min={1} max={4} step={.05} value={position.zoom} disabled={busy || !dimensions} onChange={(event) => setPosition((p) => ({ ...p, zoom: Number(event.target.value) }))} /></label>
      {loadFailed && <p role="alert" className="text-xs text-danger">Couldn't open this picture. <button type="button" onClick={() => { setLoadFailed(false); setLoadVersion((v) => v + 1); }}>Try again</button></p>}
      {problem && <p role="alert" className="text-xs text-danger">{problem}</p>}
      <DialogFooter><Button variant="ghost" disabled={busy} onClick={reset} className="mr-auto"><RotateCcw /> Reset</Button><Button disabled={busy} onClick={() => { live.current = false; onClose(); }}>Cancel</Button><Button variant="primary" disabled={busy || !dimensions || loadFailed} onClick={async () => { if (!image.current || busy) return; setBusy(true); setProblem(null); try { const file = await cropPhoto(image.current, shape, ratio, position, name); if (!live.current) return; await onConfirm(file); } catch (error) { if (live.current) setProblem(friendlyError(error, "Couldn't save that photo. Try again.")); } finally { if (live.current) setBusy(false); } }}>{busy && <Spinner />}{busy ? "Saving photo?" : problem ? "Try again" : "Use photo"}</Button></DialogFooter>
    </DialogContent>
  </Dialog>;
}
