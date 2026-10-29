import { useEffect, useId, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { assetUrl, friendlyError } from "../api";
import { Spinner } from "../components";
import { clamp } from "../color";
import { cropGeometry, cropPhoto, cropPositionLabel, cropRatio, RESET_CROP } from "./crop";
import type { ImageCropRecipe } from "../types";
import "../editor.css";

interface CropDialogProps {
  name: string;
  shape?: string;
  initialCrop?: ImageCropRecipe;
  onClose: () => void;
  onConfirm: (file: File, crop: ImageCropRecipe) => Promise<void>;
  /** Keep the original picture untouched: no crop, no new file. */
  onUseAsIs?: () => void;
}

export function CropDialog({ name, shape, initialCrop, onClose, onConfirm, onUseAsIs }: CropDialogProps) {
  const image = useRef<HTMLImageElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const initialFocus = useRef(false);
  const helpId = useId();
  const [dimensions, setDimensions] = useState<{ width: number; height: number } | null>(null);
  const [position, setPosition] = useState(() => initialCrop?.position ?? RESET_CROP);
  const [freeRatio, setFreeRatio] = useState<number | null>(() => !shape || shape === "free" ? initialCrop?.ratio ?? null : null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [loadVersion, setLoadVersion] = useState(0);
  const live = useRef(true);
  const drag = useRef<{ x: number; y: number; startX: number; startY: number } | null>(null);
  useEffect(() => {
    live.current = true;
    return () => { live.current = false; };
  }, []);

  const ratio = freeRatio ?? cropRatio(shape, dimensions ? dimensions.width / dimensions.height : 1);
  const rect = dimensions ? cropGeometry(dimensions.width, dimensions.height, ratio, position) : null;
  const ready = !!dimensions && !loadFailed;
  // The stage always fits the whole photo; the mask is the crop window over it.
  const frameRatio = dimensions ? dimensions.width / dimensions.height : ratio;
  const frameWidth = Math.round(300 * frameRatio * 100) / 100;
  const reset = () => { setPosition(RESET_CROP); setFreeRatio(null); };
  const close = () => { if (!busy) { live.current = false; onClose(); } };
  // Nothing is cropped or saved: the field keeps the picture it already has.
  const useAsIs = () => {
    if (busy) return;
    live.current = false;
    onUseAsIs?.();
    onClose();
  };

  const startDrag = (event: PointerEvent<HTMLDivElement>) => {
    if (busy || !ready || event.button !== 0) return;
    event.currentTarget.focus();
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { x: event.clientX, y: event.clientY, startX: position.x, startY: position.y };
  };
  const moveDrag = (event: PointerEvent<HTMLDivElement>) => {
    const start = drag.current;
    if (busy || !start || !event.currentTarget.hasPointerCapture(event.pointerId) || !rect || !dimensions) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    // Half the window's on-screen travel: one position unit is 2 × travel pixels.
    const travelX = (dimensions.width / rect.width - 1) * bounds.width / 2;
    const travelY = (dimensions.height / rect.height - 1) * bounds.height / 2;
    // Capture coordinates before React runs the updater: pointerup may clear drag meanwhile.
    const x = travelX ? clamp(start.startX + (event.clientX - start.x) / travelX, -1, 1) : start.startX;
    const y = travelY ? clamp(start.startY + (event.clientY - start.y) / travelY, -1, 1) : start.startY;
    setPosition((previous) => ({ ...previous, x, y }));
  };
  const stopDrag = (event: PointerEvent<HTMLDivElement>) => {
    drag.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };
  const moveWithKeys = (event: KeyboardEvent<HTMLDivElement>) => {
    if (busy || !ready || !event.key.startsWith("Arrow")) return;
    event.preventDefault();
    const step = event.shiftKey ? .1 : .02;
    const dx = event.key === "ArrowLeft" ? -step : event.key === "ArrowRight" ? step : 0;
    const dy = event.key === "ArrowUp" ? -step : event.key === "ArrowDown" ? step : 0;
    setPosition((previous) => ({ ...previous, x: clamp(previous.x + dx, -1, 1), y: clamp(previous.y + dy, -1, 1) }));
  };
  const confirm = async () => {
    if (!image.current || busy || !ready) return;
    setBusy(true);
    setProblem(null);
    try {
      const file = await cropPhoto(image.current, shape, ratio, position, name);
      if (live.current) await onConfirm(file, { source: name, position: { ...position }, ratio, shape: shape ?? "free" });
    } catch (error) {
      if (live.current) setProblem(error instanceof DOMException && error.name === "SecurityError"
        ? "This picture couldn't be cropped. Try downloading and uploading it again."
        : friendlyError(error, "Couldn't save that photo. Try again."));
    } finally {
      if (live.current) setBusy(false);
    }
  };

  return <Dialog open onOpenChange={(open) => { if (!open) close(); }}>
    <DialogContent className="studio-crop-dialog" hideClose={busy}
      onOpenAutoFocus={(event) => {
        event.preventDefault();
        stage.current?.focus();
      }}
      onEscapeKeyDown={(event) => { if (busy) event.preventDefault(); }}
      onPointerDownOutside={(event) => { if (busy) event.preventDefault(); }}>
      <DialogHeader>
        <DialogTitle>Adjust photo</DialogTitle>
        <DialogDescription>
          Drag the {shape === "circle" ? "circle" : "frame"} to choose what shows in your video. Arrow keys move it too.
        </DialogDescription>
      </DialogHeader>
      <div className="studio-crop-stage">
        <div className="studio-crop-frame" style={{ width: `min(100%, ${frameWidth}px)`, aspectRatio: String(frameRatio) }}>
          <img key={loadVersion} ref={image} crossOrigin="anonymous" src={assetUrl(name)} alt="Photo to crop" draggable={false}
            className="studio-crop-photo"
            onLoad={(event) => {
              const img = event.currentTarget;
              if (!img.naturalWidth || !img.naturalHeight) { setLoadFailed(true); return; }
              setDimensions({ width: img.naturalWidth, height: img.naturalHeight });
              setLoadFailed(false);
            }} onError={() => setLoadFailed(true)}
            style={dimensions ? undefined : { visibility: "hidden" }} />
          {dimensions && rect && (
            <div ref={(node) => {
              stage.current = node;
              if (node && !initialFocus.current) { initialFocus.current = true; node.focus(); }
            }} className="studio-crop-mask" data-circle={shape === "circle" || undefined}
              style={{
                left: `${rect.x / dimensions.width * 100}%`, top: `${rect.y / dimensions.height * 100}%`,
                width: `${rect.width / dimensions.width * 100}%`, height: `${rect.height / dimensions.height * 100}%`,
                aspectRatio: String(ratio),
              }}
              role="group" tabIndex={0} aria-label="Photo position" aria-valuetext={cropPositionLabel(position)}
              aria-describedby={helpId} aria-disabled={busy || !ready}
              onPointerDown={startDrag} onPointerMove={moveDrag} onPointerUp={stopDrag} onPointerCancel={stopDrag}
              onLostPointerCapture={() => { drag.current = null; }} onKeyDown={moveWithKeys} />
          )}
        </div>
        {!dimensions && !loadFailed && <span className="studio-crop-loading" role="status"><Spinner /> Loading photo…</span>}
      </div>
      <p id={helpId} className="studio-crop-help">Shift + arrow moves farther.</p>
      {(!shape || shape === "free") && <label className="studio-crop-slider">
        Crop width <span>{ratio.toFixed(2)}:1</span>
        <input type="range" aria-label="Crop width" aria-valuetext={`${ratio.toFixed(2)} to 1`} min={.25} max={4} step={.01} value={clamp(ratio, .25, 4)} disabled={busy || !ready}
          onChange={(event) => { setFreeRatio(Number(event.target.value)); setPosition(RESET_CROP); }} />
      </label>}
      <label className="studio-crop-slider">
        Zoom <span>{position.zoom.toFixed(1)}×</span>
        <input type="range" aria-label="Zoom" aria-valuetext={`${position.zoom.toFixed(1)} times`} min={1} max={4} step={.05} value={position.zoom} disabled={busy || !ready}
          onChange={(event) => setPosition((previous) => ({ ...previous, zoom: Number(event.target.value) }))} />
      </label>
      {loadFailed && <p role="alert" className="studio-crop-error">Couldn't open this picture. <button type="button" onClick={() => {
        initialFocus.current = false; setDimensions(null); setLoadFailed(false); setLoadVersion((version) => version + 1);
      }}>Try again</button></p>}
      {problem && <p role="alert" className="studio-crop-error">{problem}</p>}
      <DialogFooter>
        <Button variant="ghost" disabled={busy || !ready} onClick={reset} className="mr-auto"><RotateCcw /> Reset</Button>
        <Button variant="secondary" disabled={busy} onClick={useAsIs}>Use as is</Button>
        <Button disabled={busy} onClick={close}>Cancel</Button>
        <Button variant="primary" disabled={busy || !ready} onClick={() => void confirm()}>
          {busy && <Spinner />}{busy ? "Saving photo…" : problem ? "Try again" : "Use photo"}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>;
}
