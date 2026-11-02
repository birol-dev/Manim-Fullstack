/** The "Look" controls: theme, energy, ending, background, length, safe zone, number style, brand. */
import { useId, useRef, type ReactNode } from "react";
import { Check } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

import { inputClass, Segments } from "./components";
import { ColorControl } from "./ColorControl";
import { changeBackgroundKind, visibleBackgroundSlots, type BackgroundSlot } from "./background";
import { ImageWidget } from "./form/media";
import { BACKGROUNDS, ENDINGS, ENERGIES, formatSeconds, isPortrait, LOCALES } from "./options";
import { BRAND_FONTS, readBrandKit } from "./preferences";
import type { FieldSpec } from "./schemaForm";
import type { Background, Brand, RenderSettings, TemplateInfo, Theme } from "./types";

const TEMPLATE_FONT = "__template__";
const LOGO_FIELD: FieldSpec = {
  key: "logo",
  widget: "image",
  title: "Logo",
  description: "Shown small in a corner of this video.",
  required: false,
  nullable: true,
  shape: "logo",
};

/** Try each bundled family in the dropdown; the renderer always uses the real bundled file. */
function fontStack(value: string): string {
  return value === "JetBrains Mono"
    ? '"JetBrains Mono Studio", "JetBrains Mono", ui-monospace, monospace'
    : '"Inter Studio", Inter, system-ui, sans-serif';
}

interface LookPanelProps {
  settings: RenderSettings;
  onChange: (patch: Partial<RenderSettings>) => void;
  template: TemplateInfo;
  themes: Theme[];
  errors: Record<string, string[]>;
}

function Row({ label, labelId, htmlFor, hint, errors, children }: { label: string; labelId?: string; htmlFor?: string; hint?: ReactNode; errors?: string[]; children: ReactNode }) {
  return (
    <div className="studio-look-field">
      {htmlFor ? (
        <label id={labelId} htmlFor={htmlFor} className="text-[13px] font-medium text-fg">
          {label}
        </label>
      ) : (
        <span id={labelId} className="text-[13px] font-medium text-fg">
          {label}
        </span>
      )}
      {children}
      {errors && errors.length > 0 && (
        <p role="alert" className="text-xs text-danger">
          {errors.join(" ")}
        </p>
      )}
      {hint && <p className="text-xs leading-relaxed text-fg-subtle">{hint}</p>}
    </div>
  );
}

function ThemeSwatches({ themes, value, onChange, labelId }: { themes: Theme[]; value: string; onChange: (id: string) => void; labelId: string }) {
  return (
    <div role="radiogroup" aria-labelledby={labelId} className="studio-theme-grid">
      {themes.map((theme) => {
        const active = theme.id === value;
        return (
          <button
            key={theme.id}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(theme.id)}
            className={cn(
              "studio-theme-card",
              active && "studio-theme-selected",
            )}
          >
            <span
              aria-hidden
              className="studio-theme-sample"
              style={{ background: theme.bg, color: theme.text }}
            >
              <span className="text-base font-bold leading-none">Aa</span>
              <span className="flex gap-0.5">
                {theme.accent.slice(0, 5).map((color) => (
                  <span key={color} className="size-1.5 rounded-full" style={{ background: color }} />
                ))}
              </span>
              {active && (
                <span className="absolute right-1 top-1 flex size-4 items-center justify-center rounded-full bg-accent text-accent-fg">
                  <Check className="size-3" />
                </span>
              )}
            </span>
            <span className="truncate px-0.5 text-xs font-medium text-fg-muted">{theme.name}</span>
          </button>
        );
      })}
    </div>
  );
}

function ColorInput({ label, value, fallback, onChange, theme }: { label: string; value: string | null | undefined; fallback: string; onChange: (value: string | null) => void; theme?: Theme }) {
  const id = useId();
  return (
    <div className="studio-look-field">
      <label id={`${id}-label`} htmlFor={id} className="text-[13px] font-medium text-fg">{label}</label>
      <ColorControl id={id} label={label} value={value} fallback={fallback} theme={theme} onChange={onChange} pickerLabel={label} />
    </div>
  );
}

export function LookPanel({ settings, onChange, template, themes, errors }: LookPanelProps) {
  const ids = {
    theme: useId(), energy: useId(), ending: useId(), background: useId(), length: useId(), locale: useId(),
    safe: useId(), brandLogo: useId(), brandFont: useId(), brandMain: useId(), brandSecond: useId(),
  };
  const theme = themes.find((item) => item.id === settings.theme);
  const background = settings.background ?? { kind: "theme" };
  const chosenBackgroundSlots = useRef(new Set<BackgroundSlot>(visibleBackgroundSlots(background)));
  const setBackground = (patch: Partial<Background>) => {
    for (const slot of ["color", "color2"] as const) {
      if (slot in patch) chosenBackgroundSlots.current.add(slot);
    }
    onChange({ background: { ...background, ...patch } });
  };
  const length = settings.length ?? template.default_length;
  const lengthStep = template.max_length - template.min_length > 120 ? 1 : 0.5;
  const err = (path: string) => errors[path] ?? [];
  const brand: Brand = settings.brand ?? {};
  const kit = readBrandKit();
  const setBrand = (patch: Partial<Brand>) => onChange({ brand: { ...brand, ...patch } });

  return (
    <div className="studio-look-panel">
      <section className="studio-look-section" aria-label="Style">
        <h2>Style</h2>
        {themes.length > 0 && (
          <Row label="Theme" labelId={ids.theme} errors={err("settings.theme")}>
            <ThemeSwatches themes={themes} value={settings.theme} onChange={(id) => onChange({ theme: id })} labelId={ids.theme} />
          </Row>
        )}

        <Row
          label="Background"
          labelId={ids.background}
          errors={[...err("settings.background"), ...err("settings.background.color"), ...err("settings.background.color2")]}
          hint={
            background.kind === "transparent"
              ? "See-through: WebM, MOV and PNG keep it. Choosing MP4 produces a MOV file. GIF has limited transparency."
              : undefined
          }
        >
          <Segments
            value={background.kind}
            options={BACKGROUNDS}
            onChange={(kind) => {
              const next = changeBackgroundKind(background, kind, theme, chosenBackgroundSlots.current);
              for (const slot of visibleBackgroundSlots(next)) chosenBackgroundSlots.current.add(slot);
              onChange({ background: next });
            }}
            aria-labelledby={ids.background}
          />
          {background.kind === "solid" && (
            <ColorInput label="Color" value={background.color} fallback={theme?.bg ?? "#FFFFFF"} theme={theme} onChange={(color) => setBackground({ color })} />
          )}
          {background.kind === "gradient" && (
            <div className="flex flex-col gap-4">
              <ColorInput label="From" value={background.color} fallback={theme?.bg ?? "#FFFFFF"} theme={theme} onChange={(color) => setBackground({ color })} />
              <ColorInput
                label="To"
                value={background.color2}
                fallback={theme?.accent?.[0] ?? "#2563EB"}
                theme={theme}
                onChange={(color2) => setBackground({ color2 })}
              />
            </div>
          )}
        </Row>

      </section>
      <section className="studio-look-section" aria-label="Motion">
        <h2>Motion</h2>
        <Row label="Energy" labelId={ids.energy} hint="How quickly things move in." errors={err("settings.energy")}>
          <Segments value={settings.energy} options={ENERGIES} onChange={(energy) => onChange({ energy })} aria-labelledby={ids.energy} />
        </Row>
        <Row label="Ending" labelId={ids.ending} hint="What happens in the last moment of the video." errors={err("settings.ending")}>
          <Segments value={settings.ending} options={ENDINGS} onChange={(ending) => onChange({ ending })} aria-labelledby={ids.ending} />
        </Row>
        {!template.length_from_params && (
          <Row label="Length" htmlFor={ids.length} labelId={`${ids.length}-label`} errors={err("settings.length")}>
            <div className="flex items-center gap-3">
              <input
                id={ids.length}
                type="range"
                min={template.min_length}
                max={template.max_length}
                step={lengthStep}
                value={length}
                aria-valuetext={formatSeconds(length)}
                onChange={(event) => onChange({ length: Number(event.target.value) })}
                className="studio-range h-2 flex-1 cursor-pointer"
              />
              <span className="studio-value-chip">{formatSeconds(length)}</span>
            </div>
          </Row>
        )}

      </section>
      <section className="studio-look-section" aria-label="Details">
        <h2>Details</h2>
        {isPortrait(settings.aspect) && (
          <div className="studio-setting-row">
            <div>
              <label htmlFor={ids.safe} className="text-[13px] font-medium text-fg">
                Keep clear of app buttons
              </label>
              <p className="mt-0.5 text-xs leading-relaxed text-fg-subtle">
                Leaves room at the bottom and right for the buttons TikTok, Reels and Shorts put on top of videos.
              </p>
            </div>
            <Switch id={ids.safe} checked={settings.safe_zone} onCheckedChange={(safe_zone) => onChange({ safe_zone })} className="mt-0.5" />
          </div>
        )}

        <div className="studio-setting-row">
          <div><label htmlFor={ids.locale}>Numbers and dates</label><p>How numbers are written in the video.</p></div>
          <Select value={settings.locale} onValueChange={(locale) => onChange({ locale })}>
            <SelectTrigger id={ids.locale} className={cn(inputClass, "h-9 rounded-lg")}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {LOCALES.map((locale) => (
                <SelectItem key={locale.value} value={locale.value} className="text-sm">
                  {locale.label} <span className="ml-1 font-mono text-fg-subtle">{locale.sample}</span>
                </SelectItem>
              ))}
              {!LOCALES.some((locale) => locale.value === settings.locale) && (
                <SelectItem value={settings.locale} className="text-sm">
                  {settings.locale}
                </SelectItem>
              )}
            </SelectContent>
          </Select>
        </div>
        {err("settings.locale").length > 0 && <p role="alert" className="text-xs text-danger">{err("settings.locale").join(" ")}</p>}
      </section>
      <section className="studio-look-section" aria-label="Brand">
        <h2>Brand</h2>
        <Row label="Logo" labelId={`${ids.brandLogo}-label`} htmlFor={ids.brandLogo} errors={err("settings.brand.logo")}
          hint="Shown small in a corner of this video.">
          <ImageWidget
            field={LOGO_FIELD}
            id={ids.brandLogo}
            value={brand.logo ?? null}
            onChange={(value) => setBrand({ logo: typeof value === "string" ? value : null })}
            invalid={err("settings.brand.logo").length > 0}
          />
        </Row>
        <Row label="Main color" labelId={`${ids.brandMain}-label`} errors={err("settings.brand.accent")}>
          <ColorControl
            id={ids.brandMain}
            label="Main color"
            value={brand.accent}
            fallback={theme?.accent?.[0] ?? "#2563EB"}
            theme={theme}
            pickerLabel="Main color"
            onChange={(accent) => setBrand({ accent })}
          />
        </Row>
        <Row label="Second color" labelId={`${ids.brandSecond}-label`} errors={err("settings.brand.accent2")}>
          <ColorControl
            id={ids.brandSecond}
            label="Second color"
            value={brand.accent2}
            fallback={theme?.accent?.[1] ?? "#F97316"}
            theme={theme}
            pickerLabel="Second color"
            onChange={(accent2) => setBrand({ accent2 })}
          />
        </Row>
        <Row label="Font" labelId={`${ids.brandFont}-label`} errors={err("settings.brand.font")}>
          <Select value={brand.font ?? TEMPLATE_FONT} onValueChange={(value) => setBrand({ font: value === TEMPLATE_FONT ? null : value })}>
            <SelectTrigger id={ids.brandFont} aria-labelledby={`${ids.brandFont}-label`} className={cn(inputClass, "h-9 rounded-lg")}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={TEMPLATE_FONT} className="text-sm">Template's own font</SelectItem>
              {BRAND_FONTS.map((font) => (
                <SelectItem key={font.value} value={font.value} className="text-sm" style={{ fontFamily: fontStack(font.value) }}>
                  {font.label}
                </SelectItem>
              ))}
              {brand.font && !BRAND_FONTS.some((font) => font.value === brand.font) && (
                <SelectItem value={brand.font} className="text-sm">{brand.font}</SelectItem>
              )}
            </SelectContent>
          </Select>
        </Row>
        <div className="flex flex-wrap items-center gap-3">
          {kit ? (
            <>
              <Button type="button" size="sm" variant="secondary" onClick={() => onChange({ brand: { ...kit } })}>
                Use my brand
              </Button>
              <p className="text-xs text-fg-subtle">Applies your saved logo, colors and font to this video.</p>
            </>
          ) : (
            <p className="text-xs text-fg-subtle">
              You haven't saved a brand yet. <a className="underline" href="#/settings/profile">Set up your brand</a>.
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
