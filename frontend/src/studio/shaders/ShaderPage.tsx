import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowDownToLine, Check, FileUp, ImagePlus, Pause, Play, RotateCcw, Search, SlidersHorizontal, Sparkles, X } from "lucide-react";
import type { PaperShaderElement } from "@paper-design/shaders";
import { toast } from "sonner";
import { friendlyError, uploadImage, validateImage } from "../api";
import { Spinner } from "../components";
import { CATEGORIES, cloneParams, DEFAULT_IMAGE, getShader, SHADERS, type Category, type ShaderValue } from "./catalog";
import { ShaderControls } from "./Controls";
import { ASPECTS, canvasPng, download, newDraft, parseDraft, portableDraft, readDraft, SHADER_DRAFT_KEY, type Aspect, type ShaderDraft } from "./files";
import { ShaderPreview } from "./Preview";
import { recordCanvas, recordingType } from "./recording";
import "./shaders.css";

export function ShaderPage() {
  const [draft, setDraft] = useState(readDraft);
  const [category, setCategory] = useState<Category | "All">("All");
  const [query, setQuery] = useState("");
  const [playing, setPlaying] = useState(() => !window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const [ready, setReady] = useState(false);
  const [previewVersion, setPreviewVersion] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [storageError, setStorageError] = useState(false);
  const [seconds, setSeconds] = useState(5);
  const [progress, setProgress] = useState(0);
  const [videoType] = useState(recordingType);
  const element = useRef<PaperShaderElement>(null);
  const uploadRef = useRef<HTMLInputElement>(null);
  const importRef = useRef<HTMLInputElement>(null);
  const controller = useRef<AbortController | null>(null);
  const drafts = useRef<Record<string, ShaderDraft>>({});
  const latestDraft = useRef(draft);
  const shader = getShader(draft.shader)!;
  const mounted = useRef(true);
  const onReady = useCallback(() => setReady(true), []);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; controller.current?.abort(); };
  }, []);
  useEffect(() => {
    latestDraft.current = draft;
    const timer = window.setTimeout(() => {
      try { localStorage.setItem(SHADER_DRAFT_KEY, JSON.stringify(draft)); setStorageError(false); }
      catch { setStorageError(true); }
    }, 250);
    return () => clearTimeout(timer);
  }, [draft]);
  useEffect(() => {
    // Leaving the tab or closing the window must keep edits made within the debounce window.
    const flush = () => { try { localStorage.setItem(SHADER_DRAFT_KEY, JSON.stringify(latestDraft.current)); } catch { /* The visible storage warning offers a portable file. */ } };
    window.addEventListener("pagehide", flush);
    return () => { window.removeEventListener("pagehide", flush); flush(); };
  }, []);

  const filtered = SHADERS.filter((item) => (category === "All" || item.category === category) && `${item.name} ${item.description}`.toLowerCase().includes(query.toLowerCase()));
  const change = (key: string, value: ShaderValue) => setDraft((current) => ({ ...current, preset: "Custom", params: { ...current.params, [key]: value } }));
  const refreshPreview = () => { setReady(false); setPreviewVersion((value) => value + 1); };
  const select = (id: string) => {
    if (id === draft.shader || busy) return;
    drafts.current[draft.shader] = draft;
    const saved = drafts.current[id];
    setDraft(saved ? { ...saved, image: draft.image, logo: draft.logo, aspect: draft.aspect } : { ...newDraft(getShader(id)!), image: draft.image, logo: draft.logo, aspect: draft.aspect });
    setError(null); refreshPreview();
  };
  const run = async (label: string, action: () => Promise<void>) => {
    setBusy(label); setError(null);
    try { await action(); }
    catch (problem) { if (mounted.current) setError(friendlyError(problem, "Couldn't finish that. Please try again.")); }
    finally { if (mounted.current) setBusy(null); }
  };
  const picture = async (file: File | undefined) => {
    if (!file) return;
    await run("Uploading picture…", async () => {
      const problem = validateImage(file);
      if (problem) throw new Error(problem);
      const source = URL.createObjectURL(file);
      try { const image = new Image(); image.src = source; await image.decode(); }
      catch { throw new Error("That picture couldn't be opened. Choose a PNG, JPG, WebP, GIF, or SVG."); }
      finally { URL.revokeObjectURL(source); }
      const name = await uploadImage(file);
      if (!mounted.current) return;
      setDraft((current) => ({ ...current, [shader.category === "Logo animations" ? "logo" : "image"]: `/assets/${encodeURIComponent(name)}` }));
      refreshPreview();
    });
  };
  const canvas = () => {
    const result = element.current?.paperShaderMount?.canvasElement;
    if (!ready || !result?.width) throw new Error("Wait for the preview to finish loading.");
    return result;
  };
  const exportPng = (add: boolean) => run(add ? "Adding to images…" : "Saving PNG…", async () => {
    const blob = await canvasPng(canvas());
    const name = `${shader.id}.png`;
    if (add) {
      const stored = await uploadImage(new File([blob], name, { type: "image/png" }));
      toast.success("Added to your images", { description: `Choose ${stored} from the image picker in any template.` });
    } else download(blob, name);
  });
  const exportVideo = () => run("Recording video…", async () => {
    const mount = element.current?.paperShaderMount;
    const target = canvas();
    if (!mount) return;
    const restorePlaying = playing;
    const previousFrame = mount.getCurrentFrame();
    controller.current = new AbortController();
    setProgress(0);
    mount.setSpeed(0); mount.setFrame(0);
    try {
      const recording = recordCanvas(target, seconds, controller.current.signal, setProgress);
      mount.setSpeed(Number(draft.params.speed ?? 1));
      download(await recording, `${shader.id}-${seconds}s.webm`);
    } finally {
      mount.setSpeed(restorePlaying ? Number(draft.params.speed ?? 0) : 0);
      if (!restorePlaying) mount.setFrame(previousFrame);
      controller.current = null;
    }
  });
  const openSettings = async (file: File | undefined) => {
    if (!file) return;
    await run("Opening settings…", async () => {
      if (file.size > 70 * 1024 * 1024) throw new Error("That settings file is too large. Choose a file under 70 MB.");
      const raw = JSON.parse(await file.text());
      if (raw.format !== "manim-shader" || raw.version !== 1) throw new Error("Choose a shader settings file saved by this app.");
      const next = parseDraft(raw);
      if (!mounted.current) return;
      setDraft(next); refreshPreview();
    });
  };
  const source = shader.category === "Image filters" ? draft.image : draft.logo;
  return <div className="shader-page" aria-busy={!!busy}>
    <header className="shader-page-header">
      <div><div className="shader-eyebrow"><Sparkles aria-hidden /> A playground for light & texture</div><h1>Shaders<span className="shader-total" aria-hidden>30</span></h1><p>A picture, a shape, or just a little color. Make it something new.</p></div>
      <div className="shader-file-actions">
        <span className="shader-autosave">{storageError ? "Save a settings file to keep this" : <><Check aria-hidden /> Draft kept on this device</>}</span>
        <button type="button" className="shader-button" disabled={!!busy} onClick={() => importRef.current?.click()}><FileUp aria-hidden /> Open settings</button>
        <button type="button" className="shader-button" disabled={!!busy} onClick={() => run("Saving settings…", async () => download(await portableDraft(draft), `${shader.id}.shader.json`))}><ArrowDownToLine aria-hidden /> Save settings</button>
      </div>
    </header>
    <input ref={importRef} type="file" accept=".json,application/json" aria-label="Open shader settings file" className="sr-only" tabIndex={-1} onChange={(event) => { void openSettings(event.target.files?.[0]); event.target.value = ""; }} />
    {error && <div className="shader-error" role="alert"><span>{error}</span><button type="button" aria-label="Dismiss error" onClick={() => setError(null)}><X /></button></div>}
    <div className="shader-workspace">
      <aside className="shader-browser" aria-label="Shader library">
        <label className="shader-search"><Search aria-hidden /><input type="search" aria-label="Search shaders" placeholder="Find a shader…" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
        <div className="shader-categories" role="group" aria-label="Shader categories">{(["All", ...CATEGORIES] as const).map((item) => <button type="button" key={item} aria-label={item} aria-pressed={category === item} onClick={() => setCategory(item)}>{item === "Logo animations" ? "Logos" : item}<span aria-hidden>{item === "All" ? SHADERS.length : SHADERS.filter((effect) => effect.category === item).length}</span></button>)}</div>
        <div className="shader-card-list" role="group" aria-label="Choose a shader">{filtered.map((item) => <button key={item.id} type="button" className="shader-card" aria-label={item.name} aria-pressed={shader.id === item.id} disabled={!!busy} onClick={() => select(item.id)}>
          <div><img loading="lazy" src={`/shaders/previews/${item.id}.webp`} alt="" />{shader.id === item.id && <span className="shader-card-selected"><Check aria-hidden /></span>}</div><span>{item.name}</span>
        </button>)}{filtered.length === 0 && <p className="shader-no-results">No shaders found.<button type="button" onClick={() => { setQuery(""); setCategory("All"); }}>Show all shaders</button></p>}</div>
        <a className="shader-credit" href="https://github.com/paper-design/shaders" target="_blank" rel="noreferrer">Powered by Paper Shaders ↗</a>
      </aside>
      <section className="shader-center" aria-label="Shader canvas">
        <div className="shader-canvas-toolbar"><span className="shader-canvas-label">{shader.category}</span><label><span className="sr-only">Canvas format</span><select aria-label="Canvas format" value={draft.aspect} disabled={!!busy} onChange={(event) => { setDraft((current) => ({ ...current, aspect: event.target.value as Aspect })); refreshPreview(); }}>{Object.keys(ASPECTS).map((aspect) => <option key={aspect}>{aspect}</option>)}</select></label></div>
        <div className="shader-stage"><div className={`shader-artwork-wrap shader-aspect-${draft.aspect.toLowerCase()}`}><ShaderPreview key={previewVersion} shader={shader} draft={draft} playing={playing} elementRef={element} onReady={onReady} /></div></div>
        <div className="shader-playback"><div><button type="button" className="shader-round-button" disabled={!!busy || !shader.animated || !ready} aria-label={playing ? "Pause animation" : "Play animation"} onClick={() => setPlaying((value) => !value)}>{playing && shader.animated ? <Pause aria-hidden fill="currentColor" /> : <Play aria-hidden fill="currentColor" />}</button><span>{shader.animated ? playing ? "Live preview" : "Paused" : "Still texture"}</span></div><span>{ASPECTS[draft.aspect].join(" × ")}</span><button type="button" className="shader-text-button" disabled={!!busy || !ready} onClick={() => element.current?.paperShaderMount?.setFrame(0)}><RotateCcw aria-hidden /> Restart</button></div>
        <div className="shader-effect-caption"><div><span className="shader-eyebrow">{String(SHADERS.indexOf(shader) + 1).padStart(2, "0")} / 30</span><h2>{shader.name}</h2></div><p>{shader.description}</p></div>
        <div className="shader-export-bar">
          <button type="button" className="shader-button shader-primary" disabled={!!busy || !ready} onClick={() => void exportPng(false)}><ArrowDownToLine aria-hidden /> Export PNG</button>
          <button type="button" className="shader-button" disabled={!!busy || !ready} onClick={() => void exportPng(true)}><ImagePlus aria-hidden /> Add to images</button>
          {shader.animated && <div className="shader-video-export"><label><span className="sr-only">Video duration</span><select aria-label="Video duration" disabled={!!busy} value={seconds} onChange={(event) => setSeconds(Number(event.target.value))}>{[3, 5, 10].map((duration) => <option key={duration} value={duration}>{duration} seconds</option>)}</select></label><button type="button" className="shader-button" title={videoType ? "Export an animated WebM video" : "Video export is unavailable in this browser"} disabled={!!busy || !ready || !videoType || Number(draft.params.speed) === 0} onClick={() => void exportVideo()}><Play aria-hidden /> Export video</button></div>}
        </div>
        {busy && <div className="shader-busy" role="status"><Spinner /><span>{busy === "Recording video…" ? `Recording video… ${Math.round(progress * 100)}%` : busy}</span>{busy === "Recording video…" && <><progress aria-label="Video export progress" value={progress} max={1} /><button type="button" onClick={() => controller.current?.abort()}>Cancel</button></>}</div>}
        <p className="shader-export-hint">{shader.animated ? "Export a still frame or a WebM video. " : "Export a PNG at the canvas size. "}Added images are available in every template’s image picker.</p>
      </section>
      <aside className="shader-inspector" aria-label="Shader controls">
        <header><span><SlidersHorizontal aria-hidden /> Make it yours</span><button type="button" className="shader-text-button" disabled={!!busy} onClick={() => { setDraft((current) => ({ ...current, preset: "Default", params: cloneParams(shader.presets[0].params) })); refreshPreview(); }}><RotateCcw aria-hidden /> Reset</button></header>
        <fieldset disabled={!!busy}>
          <div className="shader-presets"><span className="shader-section-label">Presets{draft.preset === "Custom" && <small>Customized</small>}</span><div role="group" aria-label="Shader presets">{shader.presets.map((preset) => <button type="button" key={preset.name} aria-pressed={draft.preset === preset.name} onClick={() => { setDraft((current) => ({ ...current, preset: preset.name, params: cloneParams(preset.params) })); }} >{preset.name}</button>)}</div></div>
          {shader.category !== "Effects" && <div className="shader-source"><span className="shader-section-label">{shader.category === "Image filters" ? "Source image" : "Shape"}</span>
            <input ref={uploadRef} type="file" accept="image/png,image/jpeg,image/webp,image/gif,image/svg+xml" aria-label={shader.category === "Image filters" ? "Upload source image" : "Upload logo"} className="sr-only" tabIndex={-1} onChange={(event) => { void picture(event.target.files?.[0]); event.target.value = ""; }} />
            <button type="button" className="shader-upload" onClick={() => uploadRef.current?.click()}>{source ? <img src={source} alt="Current source" /> : <ImagePlus aria-hidden />}<span>{shader.category === "Image filters" ? "Change image" : source ? "Change logo" : "Upload your logo"}<small>PNG, JPG, WebP, GIF, SVG</small></span><FileUp aria-hidden /></button>
            {(shader.category === "Image filters" ? draft.image !== DEFAULT_IMAGE : !!draft.logo) && <button type="button" className="shader-text-button" onClick={() => { setDraft((current) => ({ ...current, ...(shader.category === "Image filters" ? { image: DEFAULT_IMAGE } : { logo: "" }) })); refreshPreview(); }}>{shader.category === "Image filters" ? "Use example image" : "Use built-in shape"}</button>}
            {shader.id === "heatmap" && !draft.logo && <label className="shader-select-field"><span>Shape</span><select aria-label="Shape" value={draft.logoShape} onChange={(event) => { setDraft((current) => ({ ...current, logoShape: event.target.value })); refreshPreview(); }}>{["diamond", "circle", "daisy", "metaballs", "none"].map((shape) => <option key={shape} value={shape}>{shape.replace(/^./, (c) => c.toUpperCase())}</option>)}</select></label>}
            {shader.category === "Logo animations" && <p>For a clear silhouette, choose a logo with a transparent background.</p>}
          </div>}
          <ShaderControls shader={shader} params={draft.params} onChange={change} />
        </fieldset>
      </aside>
    </div>
  </div>;
}
