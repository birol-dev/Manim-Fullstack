import { Component, createElement, Suspense, useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import type { PaperShaderElement } from "@paper-design/shaders";
import { Spinner } from "../components";
import type { ShaderDefinition } from "./catalog";
import { ASPECTS, heatmapShape, type ShaderDraft } from "./files";

class PreviewBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed ? <div className="shader-preview-message" role="alert">Couldn't prepare that picture. Try a different PNG, JPG, or SVG.</div> : this.props.children;
  }
}

function supportsWebGL() {
  try {
    const canvas = document.createElement("canvas");
    const gl = canvas.getContext("webgl2");
    if (!gl) return false;
    gl.getExtension("WEBGL_lose_context")?.loseContext();
    return true;
  } catch { return false; }
}

export function ShaderPreview({ shader, draft, playing, elementRef, onReady }: {
  shader: ShaderDefinition; draft: ShaderDraft; playing: boolean;
  elementRef: RefObject<PaperShaderElement | null>; onReady: () => void;
}) {
  const [supported] = useState(supportsWebGL);
  const [width, setWidth] = useState(0);
  const [failed, setFailed] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const [targetWidth, targetHeight] = ASPECTS[draft.aspect];
  const image = shader.category === "Image filters" ? draft.image : shader.category === "Logo animations" ? draft.logo || (shader.id === "heatmap" ? heatmapShape(draft.logoShape) : "") : undefined;
  useEffect(() => {
    if (!box.current) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(box.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!supported) return;
    let ticks = 0;
    let canvas: HTMLCanvasElement | undefined;
    const lost = (event: Event) => { event.preventDefault(); setFailed(true); };
    const timer = window.setInterval(() => {
      canvas = elementRef.current?.paperShaderMount?.canvasElement;
      if (canvas?.width && canvas.height) {
        canvas.addEventListener("webglcontextlost", lost);
        onReady();
        clearInterval(timer);
      } else if (++ticks > 300) { setFailed(true); clearInterval(timer); }
    }, 50);
    return () => { clearInterval(timer); canvas?.removeEventListener("webglcontextlost", lost); };
  }, [supported, elementRef, onReady]);
  return <div className="shader-artwork" ref={box} style={{ aspectRatio: `${targetWidth} / ${targetHeight}` }} aria-label={`${shader.name} preview`}>
    {!supported ? <div className="shader-preview-message" role="alert"><strong>Your browser can't display these effects.</strong><span>Enable hardware acceleration or open the app in a browser with WebGL 2 support.</span></div>
      : failed ? <div className="shader-preview-message" role="alert">The preview stopped. Select another shader, then try this one again.</div>
        : <PreviewBoundary><Suspense fallback={<div className="shader-preview-message" role="status"><Spinner /> Preparing your shape…</div>}>
          {createElement(shader.component, {
            ...draft.params,
            image: image ?? "",
            ...(shader.category === "Logo animations" ? { suspendWhenProcessingImage: true } : {}),
            ref: elementRef, speed: playing ? Number(draft.params.speed ?? 0) : 0,
            minPixelRatio: 1, maxPixelCount: targetWidth * targetHeight,
            webGlContextAttributes: { preserveDrawingBuffer: true, alpha: true },
            style: { width: targetWidth, height: targetHeight, transformOrigin: "top left", transform: `scale(${width / targetWidth})`, visibility: width > 0 ? "visible" : "hidden" },
          })}
        </Suspense></PreviewBoundary>}
  </div>;
}
