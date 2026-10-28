/** The "Look" controls: theme, energy, ending, background, length, safe zone, number style. */
import { useId, type ReactNode } from "react";
import { Check } from "lucide-react";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

import { inputClass, Segments } from "./components";
import { BACKGROUNDS, ENDINGS, ENERGIES, formatSeconds, isPortrait, LOCALES } from "./options";
import type { Background, RenderSettings, TemplateInfo, Theme } from "./types";

interface LookPanelProps {
  settings: RenderSettings;
  onChange: (patch: Partial<RenderSettings>) => void;
  template: TemplateInfo;
  themes: Theme[];
  errors: Record<string, string[]>;
}

function Row({ label, labelId, htmlFor, hint, errors, children }: { label: string; labelId?: string; htmlFor?: string; hint?: ReactNode; errors?: string[]; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
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
    <div role="radiogroup" aria-labelledby={labelId} className="grid grid-cols-3 gap-2">
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
              "group flex flex-col gap-1.5 rounded-xl border p-1.5 text-left transition-colors focus-visible:outline-2 focus-visible:outline-accent",
              active ? "border-accent bg-accent-soft" : "border-line-strong hover:border-[#3d3d47]",
            )}
          >
            <span
              aria-hidden
              className="relative flex h-12 items-end justify-between overflow-hidden rounded-lg px-2 pb-1.5"
              style={{ background: theme.bg, color: theme.text }}
            >
              <span className="text-base font-bold leading-none">Aa</span>
              <span className="flex gap-0.5">
                {theme.accent.slice(0, 3).map((color) => (
                  <span key={color} className="size-2.5 rounded-full" style={{ background: color }} />
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

function ColorInput({ label, value, fallback, onChange }: { label: string; value: string | null | undefined; fallback: string; onChange: (value: string) => void }) {
  const id = useId();
  const color = value && /^#[0-9a-f]{6}$/i.test(value) ? value : fallback;
  return (
    <div className="flex items-center gap-2">
      <input
        id={id}
        type="color"
        value={color.toLowerCase()}
        onChange={(event) => onChange(event.target.value.toUpperCase())}
        className="h-9 w-11 cursor-pointer rounded-lg border border-line-strong bg-raised p-1"
      />
      <label htmlFor={id} className="text-xs text-fg-muted">
        {label} <span className="font-mono text-fg-subtle">{color.toUpperCase()}</span>
      </label>
    </div>
  );
}

export function LookPanel({ settings, onChange, template, themes, errors }: LookPanelProps) {
  const ids = { theme: useId(), energy: useId(), ending: useId(), background: useId(), length: useId(), locale: useId(), safe: useId() };
  const theme = themes.find((item) => item.id === settings.theme);
  const background = settings.background ?? { kind: "theme" };
  const setBackground = (patch: Partial<Background>) => onChange({ background: { ...background, ...patch } });
  const length = settings.length ?? template.default_length;
  const lengthStep = template.max_length - template.min_length > 120 ? 1 : 0.5;
  const err = (path: string) => errors[path] ?? [];

  return (
    <div className="flex flex-col gap-6">
      {themes.length > 0 && (
        <Row label="Theme" labelId={ids.theme} errors={err("settings.theme")}>
          <ThemeSwatches themes={themes} value={settings.theme} onChange={(id) => onChange({ theme: id })} labelId={ids.theme} />
        </Row>
      )}

      <Row label="Energy" labelId={ids.energy} hint="How quickly things move in." errors={err("settings.energy")}>
        <Segments value={settings.energy} options={ENERGIES} onChange={(energy) => onChange({ energy })} aria-labelledby={ids.energy} />
      </Row>

      <Row label="Ending" labelId={ids.ending} hint="What happens in the last moment of the video." errors={err("settings.ending")}>
        <Segments value={settings.ending} options={ENDINGS} onChange={(ending) => onChange({ ending })} aria-labelledby={ids.ending} />
      </Row>

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
          onChange={(kind) => setBackground({ kind })}
          aria-labelledby={ids.background}
        />
        {background.kind === "solid" && (
          <ColorInput label="Color" value={background.color} fallback={theme?.bg ?? "#FFFFFF"} onChange={(color) => setBackground({ color })} />
        )}
        {background.kind === "gradient" && (
          <div className="flex flex-wrap gap-4">
            <ColorInput label="From" value={background.color} fallback={theme?.bg ?? "#FFFFFF"} onChange={(color) => setBackground({ color })} />
            <ColorInput
              label="To"
              value={background.color2}
              fallback={theme?.accent?.[0] ?? "#2563EB"}
              onChange={(color2) => setBackground({ color2 })}
            />
          </div>
        )}
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
            <span className="w-20 text-right text-sm tabular-nums text-fg">{formatSeconds(length)}</span>
          </div>
        </Row>
      )}

      {isPortrait(settings.aspect) && (
        <div className="flex items-start justify-between gap-3 rounded-lg border border-line bg-raised/40 px-3 py-2.5">
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

      <Row label="Numbers and dates" htmlFor={ids.locale} hint="How numbers are written in the video." errors={err("settings.locale")}>
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
      </Row>
    </div>
  );
}
