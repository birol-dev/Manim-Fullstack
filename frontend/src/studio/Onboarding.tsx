/** The welcome tour: five real questions, saved as they are answered, over a live template preview. */
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { ArrowLeft, Check, Clapperboard, Play } from "lucide-react";

import { Button } from "@/components/ui/button";
import { apiUrl } from "@/lib/api";

import { AiAppsList } from "./AiAppsList";
import { ColorControl } from "./ColorControl";
import { Spinner } from "./components";
import { useCatalog, usePoster } from "./hooks";
import { ASPECTS, cardSettings } from "./options";
import {
  BRAND_NAME_MAX,
  readBrandColor,
  readBrandName,
  readDefaultFormat,
  flushPreferences,
  setBrandColor,
  setBrandName,
  setDefaultFormat,
  setOnboardingDone,
} from "./preferences";
import { navigate } from "./router";
import { useSetupStatus, type SetupStatus } from "./setup";
import { SystemList } from "./SystemList";
import type { Aspect, Card, Catalog, PreviewRequest, RenderSettings } from "./types";
import "./onboarding.css";

const STEP_COUNT = 5;
const READY_STEP = STEP_COUNT - 1;
const COLOR_DEBOUNCE_MS = 350;

const ASPECT_IDS: Aspect[] = ["16:9", "9:16", "1:1", "4:5"];

interface Shape {
  id: string;
  title: string;
  hint: string;
  w: number;
  h: number;
  accent: string;
}

/** The four shapes, in the words a person uses for them, each with one color block of its own. */
const SHAPES: Record<string, Omit<Shape, "id">> = {
  "16:9": { title: "Landscape", hint: "YouTube, screens", w: 16, h: 9, accent: "#E4572E" },
  "9:16": { title: "Vertical", hint: "Reels, TikTok, Stories", w: 9, h: 16, accent: "#2F6FED" },
  "1:1": { title: "Square", hint: "Feeds", w: 1, h: 1, accent: "#0F9F6E" },
  "4:5": { title: "Portrait", hint: "Instagram posts", w: 4, h: 5, accent: "#D6508C" },
};

const FALLBACK_SHAPES: Shape[] = ASPECTS.map((aspect) => ({ id: aspect.value, ...SHAPES[aspect.value] }));

function isAspect(value: string | null): value is Aspect {
  return value !== null && ASPECT_IDS.includes(value as Aspect);
}

/** The shapes this installation offers, with the ids the catalog uses. */
function shapeChoices(catalog: Catalog | null): Shape[] {
  const listed: unknown[] = Array.isArray(catalog?.aspects) ? catalog.aspects : [];
  const choices: Shape[] = [];
  for (const item of listed) {
    if (!item || typeof item !== "object") continue;
    const id = (item as { id?: unknown }).id;
    if (typeof id !== "string" || !SHAPES[id] || choices.some((choice) => choice.id === id)) continue;
    choices.push({ id, ...SHAPES[id] });
  }
  const ordered = ASPECT_IDS.map((id) => choices.find((choice) => choice.id === id)).filter((choice): choice is Shape => !!choice);
  return ordered.length > 0 ? ordered : FALLBACK_SHAPES;
}

/** A real card to preview: a sale or celebration card reads well in every shape. */
function pickCard(catalog: Catalog | null): Card | null {
  const cards = catalog?.sections.flatMap((section) => section.cards) ?? [];
  if (cards.length === 0) return null;
  const sale = cards.find((card) => card.tags.some((tag) => /sale|discount/i.test(tag)) || /sale/i.test(card.id));
  const celebration = cards.find((card) => card.template === "celebration");
  return sale ?? celebration ?? cards[0];
}

const QUESTIONS = [
  <><span className="studio-onboarding-fade">What should we</span> <em>call</em> <span className="studio-onboarding-fade">you?</span></>,
  <><span className="studio-onboarding-fade">What will you make</span> <em>most</em>?</>,
  <><span className="studio-onboarding-fade">Pick your</span> <em>color</em>.</>,
  <><span className="studio-onboarding-fade">Bring your</span> <em>AI</em> <span className="studio-onboarding-fade">along?</span></>,
  <><span className="studio-onboarding-fade">You're</span> <em>ready</em>.</>,
];

const HELP = [
  "We'll use it to greet you. You can change it later.",
  "Pick the shape you use most. You can change it for each video.",
  "Your videos start with this color. Pick one, or make your own.",
  "Optional. Your AI assistant can then make videos here for you.",
  "",
];

/** A little frame drawn in the shape, with just enough inside to read as a video. */
function ShapePicture({ shape }: { shape: Shape }) {
  const scale = 54 / Math.max(shape.w, shape.h);
  const w = shape.w * scale;
  const h = shape.h * scale;
  const x = (64 - w) / 2;
  const y = (64 - h) / 2;
  const pad = 4;
  const block = Math.max(7, (h - pad * 2) * 0.42);
  return <span className="studio-onboarding-shape" aria-hidden>
    <svg viewBox="0 0 64 64">
      <rect x={x} y={y} width={w} height={h} rx="4" fill="var(--color-surface)" stroke="var(--color-line-strong)" />
      <rect x={x + pad} y={y + pad} width={(w - pad * 2) * 0.6} height="3" rx="1.5" fill="var(--color-line-strong)" />
      <rect x={x + pad} y={y + pad + 7} width={(w - pad * 2) * 0.35} height="3" rx="1.5" fill="var(--color-line)" />
      <rect x={x + pad} y={y + h - pad - block} width={w - pad * 2} height={block} rx="2" fill={shape.accent} />
    </svg>
  </span>;
}

function PreviewPlaceholder({ waiting, note }: { waiting: boolean; note: string }) {
  return <div className="studio-onboarding-preview-empty">
    <span className="studio-onboarding-preview-picture" data-waiting={waiting ? "true" : undefined} aria-hidden>
      {waiting ? <Spinner /> : <Clapperboard />}
    </span>
    <p role="status">{note}</p>
  </div>;
}

export function OnboardingPage() {
  const uid = useId();
  const questionId = `${uid}question`;
  const helperId = `${uid}help`;
  const nameId = `${uid}name`;
  const colorLabelId = `${uid}color-label`;
  const colorControlId = `${uid}color`;

  const [step, setStep] = useState(0);
  const [name, setName] = useState(readBrandName);
  const [format, setFormat] = useState<string | null>(readDefaultFormat);
  const [color, setColor] = useState<string | null>(readBrandColor);
  const [previewColor, setPreviewColor] = useState<string | null>(color);
  const [brokenUrl, setBrokenUrl] = useState<string | null>(null);
  const questionRef = useRef<HTMLHeadingElement>(null);
  const tileRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const catalog = useCatalog();
  const setup = useSetupStatus();
  const shapes = useMemo(() => shapeChoices(catalog.catalog), [catalog.catalog]);
  const card = useMemo(() => pickCard(catalog.catalog), [catalog.catalog]);
  const template = useMemo(
    () => (card ? catalog.catalog?.templates.find((item) => item.id === card.template) : undefined),
    [card, catalog.catalog],
  );

  // A new color waits a moment, so dragging the picker asks for one poster, not twenty.
  useEffect(() => {
    const timer = window.setTimeout(() => setPreviewColor(color), COLOR_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [color]);

  useEffect(() => {
    questionRef.current?.focus({ preventScroll: true });
  }, [step]);

  const previewAspect = useMemo<Aspect | undefined>(() => {
    const wanted = isAspect(format) ? format : undefined;
    if (wanted && (!template || template.aspects.includes(wanted))) return wanted;
    if (card) {
      const own = cardSettings(card, template).aspect;
      if (own) return own;
    }
    return template?.default_aspect;
  }, [format, card, template]);

  const posterRequest = useMemo<PreviewRequest | null>(() => {
    if (!card) return null;
    const base = cardSettings(card, template);
    const settings: Partial<RenderSettings> = { ...base };
    if (previewAspect) settings.aspect = previewAspect;
    if (previewColor) settings.brand = { ...(base.brand ?? {}), accent: previewColor };
    return { template: card.template, params: card.params, settings, mode: "poster" };
  }, [card, template, previewAspect, previewColor]);

  const poster = usePoster(posterRequest);
  // The last finished picture stays on screen while the next one is drawn.
  const [lastUrl, setLastUrl] = useState<string | null>(null);
  const responseUrl = poster.response?.url ?? null;
  if (responseUrl && responseUrl !== lastUrl) setLastUrl(responseUrl);
  const shownUrl = responseUrl ?? lastUrl;

  const colorPending = color !== previewColor;
  const previewFailed = !!poster.error || (!!shownUrl && brokenUrl === shownUrl);
  const healthyUrl = shownUrl && brokenUrl !== shownUrl ? shownUrl : null;
  const showPoster = !!healthyUrl && !previewFailed;
  const previewWaiting = !showPoster && !previewFailed && (catalog.loading || poster.loading || colorPending);
  const previewNote = previewFailed
    ? "The preview can't be drawn right now. You can keep going."
    : catalog.error
      ? "Previews aren't available right now. You can still make your choices."
      : posterRequest === null && !catalog.loading
        ? "Your preview will show here."
        : "Getting your preview ready…";

  const setupSummary = useMemo<SetupStatus | null>(() => {
    if (!setup.status) return null;
    return {
      ...setup.status,
      components: setup.status.components
        .filter((component) => component.required)
        .map((component) => ({ ...component, can_install: false })),
    };
  }, [setup.status]);
  const requiredReady = setupSummary ? setupSummary.components.every((component) => component.status === "ready") : true;

  const chosenShape = shapes.find((shape) => shape.id === format) ?? shapes.find((shape) => shape.id === previewAspect);
  const hasShape = shapes.some((shape) => shape.id === format);

  const advance = () => {
    if (step === 0) setBrandName(name);
    else if (step === 1) setDefaultFormat(format);
    else if (step === 2) {
      setBrandColor(color);
      setPreviewColor(color);
    }
    if (step < 3) void flushPreferences();
    if (step === READY_STEP) {
      setOnboardingDone(true);
      void flushPreferences();
      navigate({ kind: "gallery" });
      return;
    }
    setStep(step + 1);
  };

  const back = () => setStep((value) => Math.max(0, value - 1));
  const skip = () => {
    if (step < READY_STEP) setStep(READY_STEP);
  };

  const chooseShape = (shape: Shape, index: number) => {
    setFormat(shape.id);
    tileRefs.current[index]?.focus();
  };
  const onTileKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const delta = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 0;
    let next = index + delta;
    if (event.key === "Home") next = 0;
    else if (event.key === "End") next = shapes.length - 1;
    else if (!delta) return;
    event.preventDefault();
    next = (next + shapes.length) % shapes.length;
    chooseShape(shapes[next], next);
  };

  const posterFigure = showPoster && healthyUrl ? <figure className="studio-onboarding-figure">
    <img
      src={apiUrl(healthyUrl)}
      alt={card ? `${card.title} preview` : "Template preview"}
      onError={() => setBrokenUrl(healthyUrl)}
    />
  </figure> : <PreviewPlaceholder waiting={previewWaiting} note={previewNote} />;

  return <main className="studio-onboarding" aria-labelledby={questionId}>
    <h2 className="sr-only">Welcome to Manim Studio</h2>
    <div className="studio-onboarding-logo">
      <span className="studio-brand-mark" aria-hidden><Play fill="currentColor" /></span>
      <span className="studio-onboarding-wordmark">Manim Studio</span>
    </div>

    <div className="studio-onboarding-stage">
      <form
        className="studio-onboarding-form"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          advance();
        }}
        onKeyDown={(event) => {
          if (event.key !== "Enter") return;
          const target = event.target as HTMLElement;
          // Controls keep their own Enter behavior (a tile selects, a swatch picks);
          // everywhere else, including the name field, Enter continues.
          if (target.closest("button, a, textarea, select, [role='slider'], [role='combobox']")) return;
          event.preventDefault();
          advance();
        }}
      >
        <div className="studio-onboarding-top">
          {step > 0
            ? <button type="button" className="studio-onboarding-back" aria-label="Back" onClick={back}><ArrowLeft aria-hidden /></button>
            : <span className="studio-onboarding-back-spacer" aria-hidden />}
          <div
            className="studio-onboarding-progress"
            role="progressbar"
            aria-label="Your progress"
            aria-valuemin={1}
            aria-valuemax={STEP_COUNT}
            aria-valuenow={step + 1}
            aria-valuetext={`Step ${step + 1} of ${STEP_COUNT}`}
          >
            <span style={{ width: `${((step + 1) / STEP_COUNT) * 100}%` }} />
          </div>
        </div>

        <p className="sr-only" aria-live="polite" aria-atomic="true">{`Step ${step + 1} of ${STEP_COUNT}`}</p>

        <h1 id={questionId} ref={questionRef} className="studio-onboarding-question" tabIndex={-1}>
          {QUESTIONS[step]}
        </h1>
        {HELP[step] && <p id={helperId} className="studio-onboarding-help">{HELP[step]}</p>}

        {step === 0 && <div className="studio-onboarding-block">
          <label className="studio-onboarding-label" htmlFor={nameId}>Your name or business</label>
          <input
            id={nameId}
            className="studio-onboarding-input"
            value={name}
            maxLength={BRAND_NAME_MAX}
            autoComplete="off"
            placeholder="Your name or studio"
            aria-describedby={helperId}
            onChange={(event) => setName(event.target.value)}
          />
        </div>}

        {step === 1 && <div
          className="studio-onboarding-tiles"
          role="radiogroup"
          aria-labelledby={questionId}
          aria-describedby={helperId}
        >
          {shapes.map((shape, index) => {
            const selected = format === shape.id;
            return <button
              key={shape.id}
              ref={(node) => { tileRefs.current[index] = node; }}
              type="button"
              role="radio"
              aria-checked={selected}
              tabIndex={selected || (!hasShape && index === 0) ? 0 : -1}
              className="studio-onboarding-tile"
              onClick={() => chooseShape(shape, index)}
              onKeyDown={(event) => onTileKeyDown(event, index)}
            >
              <ShapePicture shape={shape} />
              {selected && <span className="studio-onboarding-tile-check" aria-hidden><Check /></span>}
              <span className="studio-onboarding-tile-copy">
                <span className="studio-onboarding-tile-title">{shape.title}</span>
                <span className="studio-onboarding-tile-hint">{shape.hint}</span>
              </span>
            </button>;
          })}
        </div>}

        {step === 2 && <div className="studio-onboarding-block">
          <span id={colorLabelId} className="studio-onboarding-label">Brand color</span>
          <ColorControl
            id={colorControlId}
            label="Brand color"
            value={color}
            theme={catalog.catalog?.themes?.[0]}
            describedBy={helperId}
            onChange={setColor}
          />
        </div>}

        {step === 3 && <div className="studio-onboarding-block studio-onboarding-ai">
          <AiAppsList status={setup.status} error={setup.error} refresh={setup.refresh} />
        </div>}

        {step === 4 && <div className="studio-onboarding-block studio-onboarding-ready">
          <p className="studio-onboarding-line">That's everything. Make your first video whenever you're ready.</p>
          <SystemList status={setupSummary} error={setup.error} refresh={setup.refresh} />
          {setupSummary && !requiredReady && <div className="studio-onboarding-check">
            <Button size="sm" variant="secondary" onClick={() => void setup.refresh()}>Try again</Button>
          </div>}
        </div>}

        <div className="studio-onboarding-actions">
          <Button type="submit" variant="primary" size="md">
            {step === READY_STEP ? "Start making videos" : "Continue"}
          </Button>
          {step < READY_STEP && <button type="button" className="studio-onboarding-skip" onClick={skip}>Skip</button>}
        </div>
      </form>

      <div className="studio-onboarding-preview">
        <div className="studio-onboarding-window">
          <div className="studio-onboarding-window-bar">
            <span className="studio-onboarding-window-dot" aria-hidden />
            <span className="studio-onboarding-window-dot" aria-hidden />
            <span className="studio-onboarding-window-dot" aria-hidden />
            {showPoster && (poster.loading || colorPending) && <span className="studio-onboarding-window-busy" role="status">
              <Spinner />
              <span className="sr-only">Updating the preview…</span>
            </span>}
          </div>
          <div className="studio-onboarding-window-body">
            {step === 0 ? <div className="studio-onboarding-hello">
              <p className="studio-onboarding-hello-greeting">{name.trim() ? `Welcome, ${name.trim()}` : "Welcome"}</p>
              {posterFigure}
            </div> : step === 3 ? <div className="studio-onboarding-chat">
              <span className="studio-onboarding-chat-label">Example</span>
              <div className="studio-onboarding-chat-bubble">
                <small>Your AI assistant</small>
                <p>I made your sale video</p>
              </div>
              <div className="studio-onboarding-chat-thumb" data-empty={showPoster ? undefined : "true"}>
                {showPoster && healthyUrl
                  ? <img src={apiUrl(healthyUrl)} alt="" />
                  : <Clapperboard aria-hidden />}
              </div>
              <p className="studio-onboarding-chat-note">Just an example. Nothing is connected until you choose Connect.</p>
            </div> : <>
              {posterFigure}
              {step === 1 && hasShape && chosenShape && <p className="studio-onboarding-preview-caption">{chosenShape.title} · {chosenShape.id}</p>}
              {step === 2 && <p className="studio-onboarding-preview-caption">
                {color
                  ? <><span className="studio-onboarding-preview-dot" style={{ background: color }} aria-hidden />Your color</>
                  : "Template color"}
              </p>}
            </>}
          </div>
        </div>
      </div>
    </div>
  </main>;
}
