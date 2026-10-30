/** Settings: who you are, what new videos start with, AI apps, this computer, and about. */
import { useEffect, useId, useRef, useState, type CSSProperties, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import { ArrowUpRight, Check, RotateCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { requestJson } from "@/lib/api";

import type { Appearance } from "./appearance";
import { AiAppsList } from "./AiAppsList";
import { ColorControl } from "./ColorControl";
import { inputClass } from "./components";
import { useCatalog } from "./hooks";
import { ASPECTS } from "./options";
import {
  BRAND_NAME_MAX,
  flushPreferences,
  readBrandColor,
  readBrandName,
  readDefaultFormat,
  readDefaultTheme,
  setBrandColor,
  setBrandName,
  setDefaultFormat,
  setDefaultTheme,
} from "./preferences";
import { useSetupStatus } from "./setup";
import { SystemList } from "./SystemList";
import type { Catalog, Theme } from "./types";
import "./settings.css";

export interface SettingsPageProps {
  section?: string;
  /** The app-level theme, so the appearance control can live here. */
  appearance?: Appearance;
  onAppearance?: (value: Appearance) => void;
}

const SECTIONS = [
  { id: "profile", label: "You" },
  { id: "defaults", label: "New videos" },
  { id: "appearance", label: "Appearance" },
  { id: "ai", label: "AI assistants" },
  { id: "system", label: "This computer" },
  { id: "about", label: "About" },
] as const;

type SectionId = (typeof SECTIONS)[number]["id"];

const ASPECT_TITLES: Record<string, string> = {
  "16:9": "Landscape",
  "9:16": "Vertical",
  "1:1": "Square",
  "4:5": "Portrait",
};

interface AspectChoice {
  id: string;
  title: string;
  w: number;
  h: number;
}

/** The shapes the catalogue actually makes; the built-in four when it lists none. */
function aspectChoices(catalog: Catalog | null): AspectChoice[] {
  const listed: unknown[] = Array.isArray(catalog?.aspects) ? catalog.aspects : [];
  const choices: AspectChoice[] = [];
  for (const item of listed) {
    if (!item || typeof item !== "object") continue;
    const record = item as { id?: unknown; ratio?: unknown };
    if (typeof record.id !== "string") continue;
    if (choices.some((choice) => choice.id === record.id)) continue;
    const known = ASPECTS.find((aspect) => aspect.value === record.id);
    const ratio: unknown[] = Array.isArray(record.ratio) ? record.ratio : [];
    const w = typeof ratio[0] === "number" ? ratio[0] : known?.w;
    const h = typeof ratio[1] === "number" ? ratio[1] : known?.h;
    if (!w || !h) continue;
    choices.push({ id: record.id, title: ASPECT_TITLES[record.id] ?? known?.label ?? record.id, w, h });
  }
  if (choices.length > 0) return choices;
  return ASPECTS.map((aspect) => ({ id: aspect.value, title: ASPECT_TITLES[aspect.value] ?? aspect.label, w: aspect.w, h: aspect.h }));
}

interface TileOption {
  value: string | null;
  title: string;
  caption?: string;
  picture: ReactNode;
  wide?: boolean;
}

/** A radio group drawn as picture tiles, with arrow-key navigation (one tab stop). */
function TileGroup({ label, value, options, onChange, className }: {
  label: string;
  value: string | null;
  options: TileOption[];
  onChange: (value: string | null) => void;
  className?: string;
}) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const selected = options.findIndex((option) => option.value === value);
  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const delta = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 0;
    let next = index + delta;
    if (event.key === "Home") next = 0;
    else if (event.key === "End") next = options.length - 1;
    else if (!delta) return;
    event.preventDefault();
    next = (next + options.length) % options.length;
    onChange(options[next].value);
    refs.current[next]?.focus();
  };
  return <div role="radiogroup" aria-label={label} className={`studio-settings-tiles${className ? ` ${className}` : ""}`}>
    {options.map((option, index) => {
      const active = option.value === value;
      return <button
        key={option.title}
        ref={(node) => { refs.current[index] = node; }}
        type="button"
        role="radio"
        aria-checked={active}
        tabIndex={active || (selected === -1 && index === 0) ? 0 : -1}
        onClick={() => onChange(option.value)}
        onKeyDown={(event) => onKeyDown(event, index)}
        className={`studio-settings-tile${option.wide ? " studio-settings-tile-wide" : ""}`}
      >
        <span className="studio-settings-tile-picture" aria-hidden>{option.picture}</span>
        <span className="studio-settings-tile-copy">
          <span className="studio-settings-tile-title">{option.title}</span>
          {option.caption && <span className="studio-settings-tile-caption">{option.caption}</span>}
        </span>
      </button>;
    })}
  </div>;
}

function ShapePicture({ w, h }: { w: number; h: number }) {
  return <span className="studio-settings-shape" style={{ "--shape-ratio": `${w} / ${h}` } as CSSProperties}><span /></span>;
}

function ShapeAnyPicture() {
  return <span className="studio-settings-shape-any"><span /><span /><span /></span>;
}

function LookPicture({ mode }: { mode: Appearance }) {
  return <span className="studio-settings-look-picture" data-mode={mode}><span /></span>;
}

function ThemePicture({ theme }: { theme: Theme }) {
  return <span className="studio-settings-theme-picture" style={{ background: theme.bg, color: theme.text }}>
    <span className="studio-settings-theme-aa">Aa</span>
    <span className="studio-settings-theme-dots">{theme.accent.slice(0, 4).map((color) => <span key={color} style={{ background: color }} />)}</span>
  </span>;
}

function ThemeAnyPicture() {
  return <span className="studio-settings-theme-picture studio-settings-theme-any">
    <span className="studio-settings-theme-aa">Aa</span>
  </span>;
}

function Panel({ id, title, description, children }: { id: string; title: string; description: string; children: ReactNode }) {
  return <section className="studio-settings-section" aria-labelledby={`settings-${id}-title`}>
    <h2 id={`settings-${id}-title`}>{title}</h2>
    <p className="studio-settings-description">{description}</p>
    {children}
  </section>;
}

function SaveRow({ dirty, justSaved }: { dirty: boolean; justSaved: boolean }) {
  return <div className="studio-settings-save-row">
    {justSaved && !dirty && <span role="status" className="studio-settings-saved"><Check aria-hidden /> Saved.</span>}
    {dirty && <Button type="submit" variant="primary" size="md">Save changes</Button>}
  </div>;
}

function ProfileSection({ catalog }: { catalog: Catalog | null }) {
  const id = useId();
  const [name, setName] = useState(readBrandName);
  const [color, setColor] = useState<string | null>(readBrandColor);
  const [saved, setSaved] = useState(() => ({ name: readBrandName(), color: readBrandColor() }));
  const [justSaved, setJustSaved] = useState(false);
  const dirty = name.trim() !== saved.name || color !== saved.color;
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!dirty) return;
    const trimmed = name.trim().slice(0, BRAND_NAME_MAX);
    setBrandName(trimmed);
    setBrandColor(color);
    await flushPreferences();
    setName(trimmed);
    setSaved({ name: trimmed, color });
    setJustSaved(true);
  };
  return <Panel id="profile" title="You" description="Your name and color make new videos feel like yours.">
    <form className="studio-settings-form" onSubmit={(event) => { void submit(event); }}>
      <div className="studio-settings-fields">
        <div className="studio-settings-field">
          <label className="studio-settings-label" htmlFor={`${id}-name`}>What should we call you?</label>
          <input
            id={`${id}-name`}
            className={inputClass}
            value={name}
            maxLength={BRAND_NAME_MAX}
            autoComplete="off"
            placeholder="Your name or studio"
            onChange={(event) => { setName(event.target.value); setJustSaved(false); }}
          />
          <p className="studio-settings-hint">You can change this any time.</p>
        </div>
        <div className="studio-settings-field">
          <div className="studio-settings-label-row">
            <span id={`${id}-color-label`} className="studio-settings-label">Brand color</span>
            <span className="studio-settings-brand-value">
              <span className="studio-settings-brand-swatch" data-empty={color ? undefined : "true"} style={color ? { background: color } : undefined} aria-hidden />
              {color ?? "Template color"}
            </span>
          </div>
          <ColorControl
            id={`${id}-color`}
            label="Brand color"
            value={color}
            theme={catalog?.themes?.[0]}
            describedBy={`${id}-color-hint`}
            onChange={(value) => { setColor(value); setJustSaved(false); }}
          />
          <p id={`${id}-color-hint`} className="studio-settings-hint">New videos start with this color. You can change it per video.</p>
        </div>
      </div>
      <SaveRow dirty={dirty} justSaved={justSaved} />
    </form>
  </Panel>;
}

function DefaultsSection({ catalog, catalogError, retryCatalog }: {
  catalog: Catalog | null;
  catalogError: unknown;
  retryCatalog: () => void;
}) {
  const [shape, setShape] = useState<string | null>(readDefaultFormat);
  const [look, setLook] = useState<string | null>(readDefaultTheme);
  const [saved, setSaved] = useState(() => ({ shape: readDefaultFormat(), look: readDefaultTheme() }));
  const [justSaved, setJustSaved] = useState(false);
  const dirty = shape !== saved.shape || look !== saved.look;
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!dirty) return;
    setDefaultFormat(shape);
    setDefaultTheme(look);
    await flushPreferences();
    setSaved({ shape, look });
    setJustSaved(true);
  };
  const themes = catalog?.themes ?? [];
  const shapeOptions: TileOption[] = [
    ...aspectChoices(catalog).map((aspect) => ({
      value: aspect.id,
      title: aspect.title,
      caption: aspect.id,
      picture: <ShapePicture w={aspect.w} h={aspect.h} />,
    })),
    { value: null, title: "Keep each template's own shape", picture: <ShapeAnyPicture />, wide: true },
  ];
  const lookOptions: TileOption[] = [
    { value: null, title: "Keep each template's own look", picture: <ThemeAnyPicture />, wide: true },
    ...themes.map((theme) => ({ value: theme.id, title: theme.name, picture: <ThemePicture theme={theme} /> })),
  ];
  return <Panel id="defaults" title="New videos" description="Choose what a new video starts with. You can always change it while you work.">
    {catalogError !== null && catalogError !== undefined && <div role="alert" className="studio-settings-load-error">
      <p>Couldn't load the shapes and looks.</p>
      <Button size="sm" variant="secondary" onClick={retryCatalog}><RotateCw /> Try again</Button>
    </div>}
    <form className="studio-settings-form" onSubmit={(event) => { void submit(event); }}>
      <div className="studio-settings-fields">
        <div className="studio-settings-field">
          <span className="studio-settings-label">Default shape</span>
          <TileGroup label="Default shape" value={shape} options={shapeOptions} onChange={(value) => { setShape(value); setJustSaved(false); }} />
          <p className="studio-settings-hint">New videos start in this shape when the template supports it.</p>
        </div>
        <div className="studio-settings-field">
          <span className="studio-settings-label">Default look</span>
          <TileGroup label="Default look" value={look} options={lookOptions} onChange={(value) => { setLook(value); setJustSaved(false); }} className="studio-settings-tiles-themes" />
          <p className="studio-settings-hint">Every template can still be changed.</p>
        </div>
      </div>
      <SaveRow dirty={dirty} justSaved={justSaved} />
    </form>
  </Panel>;
}

function AppearanceSection({ appearance, onAppearance }: { appearance?: Appearance; onAppearance?: (value: Appearance) => void }) {
  const current: Appearance = appearance ?? "system";
  return <Panel id="appearance" title="Appearance" description="Make the app easier on your eyes. The change happens straight away.">
    <div className="studio-settings-fields">
      <div className="studio-settings-field">
        <span className="studio-settings-label">Theme</span>
        <TileGroup
          label="Theme"
          value={current}
          options={[
            { value: "light", title: "Light", picture: <LookPicture mode="light" /> },
            { value: "dark", title: "Dark", picture: <LookPicture mode="dark" /> },
            { value: "system", title: "System", picture: <LookPicture mode="system" /> },
          ]}
          onChange={(value) => {
            if (value === "light" || value === "dark" || value === "system") onAppearance?.(value);
          }}
        />
        <p className="studio-settings-hint">System follows your computer's light or dark setting.</p>
      </div>
    </div>
  </Panel>;
}

function AiSection() {
  const setup = useSetupStatus();
  return <Panel id="ai" title="AI assistants" description="Let an AI app make and edit videos here for you. Connecting adds Manim Studio to that app's settings. Nothing else in them changes, and a backup is kept.">
    <AiAppsList {...setup} />
  </Panel>;
}

function SystemSection() {
  const setup = useSetupStatus();
  return <Panel id="system" title="This computer" description="What Manim Studio needs to draw and save your videos on this computer.">
    <SystemList {...setup} />
  </Panel>;
}

function AboutSection() {
  const [version, setVersion] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    requestJson<{ version?: unknown }>("/api/health").then(
      (data) => { if (live && data && typeof data.version === "string") setVersion(data.version); },
      () => { /* The version is a nicety; it simply stays out when unknown. */ },
    );
    return () => { live = false; };
  }, []);
  return <Panel id="about" title="About" description="A video maker for people who don't write code.">
    <dl className="studio-settings-about">
      <div><dt>App</dt><dd>Manim Studio</dd></div>
      {version && <div><dt>Version</dt><dd>{version}</dd></div>}
    </dl>
    <nav className="studio-settings-links" aria-label="More">
      <a className="studio-settings-link-row" href="#/author">
        <span className="studio-settings-link-copy">
          <span>Author mode</span>
          <small>For people who write Manim code</small>
        </span>
        <ArrowUpRight aria-hidden />
      </a>
      <a className="studio-settings-link-row" href="#/welcome">
        <span className="studio-settings-link-copy"><span>Run the welcome tour again</span></span>
        <ArrowUpRight aria-hidden />
      </a>
    </nav>
  </Panel>;
}

export function SettingsPage({ section, appearance, onAppearance }: SettingsPageProps) {
  const active: SectionId = SECTIONS.some((item) => item.id === section) ? section as SectionId : "profile";
  const { catalog, error: catalogError, retry: retryCatalog } = useCatalog();
  return <div className="studio-settings">
    <h1 className="studio-settings-title">Settings</h1>
    <div className="studio-settings-layout">
      <nav className="studio-settings-menu" aria-label="Settings">
        {SECTIONS.map((item) => <a key={item.id} href={`#/settings/${item.id}`} aria-current={active === item.id ? "page" : undefined}>
          {item.label}
        </a>)}
      </nav>
      <div className="studio-settings-body">
        {active === "profile" && <ProfileSection catalog={catalog} />}
        {active === "defaults" && <DefaultsSection catalog={catalog} catalogError={catalogError} retryCatalog={retryCatalog} />}
        {active === "appearance" && <AppearanceSection appearance={appearance} onAppearance={onAppearance} />}
        {active === "ai" && <AiSection />}
        {active === "system" && <SystemSection />}
        {active === "about" && <AboutSection />}
      </div>
    </div>
  </div>;
}
