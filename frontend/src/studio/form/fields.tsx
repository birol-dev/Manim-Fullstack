/** The simple form widgets: text, numbers, durations, choices, toggles, colors. */
import { useState, type ReactNode } from "react";
import { Minus, Palette, Plus } from "lucide-react";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

import { inputClass, Segments } from "../components";
import { formatDuration, parseDuration, type FieldSpec } from "../schemaForm";
import { formatCellNumber, parseLocaleNumber } from "../table";
import { useFormContext } from "./context";

export interface WidgetProps {
  field: FieldSpec;
  value: unknown;
  onChange: (value: unknown) => void;
  /** The control's id (the label points at it). */
  id: string;
  /** Ids of the help and error text. */
  describedBy?: string;
  invalid: boolean;
}

interface FieldShellProps {
  id: string;
  label: ReactNode;
  labelId?: string;
  description?: string;
  errors: string[];
  counter?: ReactNode;
  tip?: ReactNode;
  /** Groups (radio groups, lists) are labelled by id; their label isn't a <label>. */
  group?: boolean;
  children: ReactNode;
  className?: string;
}

/** Label, control, help text, error text. */
export function FieldShell({ id, label, labelId, description, errors, counter, tip, group, children, className }: FieldShellProps) {
  const LabelTag = group ? "span" : "label";
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <div className="flex items-baseline justify-between gap-2">
        <LabelTag id={labelId} {...(group ? {} : { htmlFor: id })} className="text-[13px] font-medium text-fg">
          {label}
        </LabelTag>
        {counter}
      </div>
      {children}
      {errors.length > 0 && (
        <p id={`${id}-error`} role="alert" className="text-xs text-danger">
          {errors.join(" ")}
        </p>
      )}
      {description && (
        <p id={`${id}-help`} className="text-xs leading-relaxed text-fg-subtle">
          {description}
        </p>
      )}
      {tip && <p className="text-xs leading-relaxed text-fg-subtle">{tip}</p>}
    </div>
  );
}

export function TextWidget({ field, value, onChange, id, describedBy, invalid }: WidgetProps) {
  const text = typeof value === "string" ? value : value == null ? "" : String(value);
  const common = {
    id,
    value: text,
    maxLength: field.maxLength,
    placeholder: field.placeholder,
    "aria-describedby": describedBy,
    "aria-invalid": invalid || undefined,
    onChange: (event: { target: { value: string } }) => onChange(event.target.value),
  };
  if (field.widget === "textarea") {
    return <textarea {...common} rows={3} className={cn(inputClass, "min-h-20 resize-y py-2 leading-relaxed")} />;
  }
  return <input {...common} type="text" className={cn(inputClass, "h-9")} />;
}

export function Counter({ value, max }: { value: unknown; max?: number }) {
  if (!max) return null;
  const length = typeof value === "string" ? [...value].length : 0;
  return (
    <span className={cn("text-xs tabular-nums", length >= max ? "text-warning" : "text-fg-subtle")} aria-label={`${length} of ${max} characters`}>
      {length}/{max}
    </span>
  );
}

function clamp(value: number, field: FieldSpec) {
  let result = value;
  if (field.minimum !== undefined) result = Math.max(field.minimum, result);
  if (field.maximum !== undefined) result = Math.min(field.maximum, result);
  return result;
}

function rangeHint(field: FieldSpec, locale: string): string | null {
  const fmt = (n: number) => formatCellNumber(n, locale);
  if (field.minimum !== undefined && field.maximum !== undefined) return `From ${fmt(field.minimum)} to ${fmt(field.maximum)}.`;
  if (field.minimum !== undefined) return `At least ${fmt(field.minimum)}.`;
  if (field.maximum !== undefined) return `At most ${fmt(field.maximum)}.`;
  return null;
}

/** Numbers typed the way the video's language writes them ("1.234,5" in German). */
export function NumberWidget({ field, value, onChange, id, describedBy, invalid }: WidgetProps) {
  const { locale } = useFormContext();
  const [draft, setDraft] = useState<string | null>(null);
  const shown = draft ?? (typeof value === "number" ? formatCellNumber(value, locale) : value == null ? "" : String(value));
  const parsed = draft === null && typeof value === "number" ? value : parseLocaleNumber(shown, locale);
  const outOfRange =
    parsed !== null &&
    ((field.minimum !== undefined && parsed < field.minimum) || (field.maximum !== undefined && parsed > field.maximum));
  const localProblem =
    parsed === null && !(field.nullable && shown.trim() === "")
      ? field.widget === "integer"
        ? "Type a whole number."
        : "Type a number."
      : field.widget === "integer" && parsed !== null && !Number.isInteger(parsed)
        ? "Type a whole number."
      : outOfRange
        ? rangeHint(field, locale)
        : null;
  return (
    <div className="flex flex-col gap-1">
      <div className="relative flex items-center">
        <input
          id={id}
          type="text"
          inputMode={field.widget === "integer" ? "numeric" : "decimal"}
          value={shown}
          aria-describedby={describedBy}
          aria-invalid={invalid || !!localProblem || undefined}
          className={cn(inputClass, "h-9 tabular-nums", field.unit && "pr-12")}
          onChange={(event) => {
            const text = event.target.value;
            setDraft(text);
            const number = parseLocaleNumber(text, locale);
            if (number === null) {
              onChange(text.trim() === "" && field.nullable ? null : text);
              return;
            }
            onChange(number);
          }}
          onBlur={() => setDraft(null)}
        />
        {field.unit && <span className="pointer-events-none absolute right-3 text-xs text-fg-subtle">{field.unit}</span>}
      </div>
      {localProblem && <p className="text-xs text-warning">{localProblem}</p>}
    </div>
  );
}

/** Seconds shown as mm:ss, with ±30 s buttons. */
export function DurationWidget({ field, value, onChange, id, describedBy, invalid }: WidgetProps) {
  const seconds = typeof value === "number" ? value : Number(value) || 0;
  const [draft, setDraft] = useState<string | null>(null);
  const parsed = draft === null ? null : parseDuration(draft);
  const problem = draft !== null && draft.trim() !== "" && parsed === null;
  const commit = () => {
    if (draft === null) return;
    if (parsed !== null) onChange(clamp(parsed, field));
    if (parsed !== null || draft.trim() === "") setDraft(null);
  };
  const step = (delta: number) => {
    setDraft(null);
    onChange(clamp(Math.max(0, seconds + delta), field));
  };
  const atMin = field.minimum !== undefined && seconds <= field.minimum;
  const atMax = field.maximum !== undefined && seconds >= field.maximum;
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          onClick={() => step(-30)}
          disabled={atMin}
          aria-label="30 seconds less"
          className="flex size-9 shrink-0 items-center justify-center rounded-lg border border-line-strong bg-raised text-fg-muted hover:bg-overlay hover:text-fg disabled:opacity-40"
        >
          <Minus className="size-4" />
        </button>
        <input
          id={id}
          type="text"
          inputMode="numeric"
          value={draft ?? formatDuration(seconds)}
          aria-describedby={describedBy}
          aria-invalid={invalid || problem || undefined}
          placeholder="5:00"
          className={cn(inputClass, "h-9 w-28 text-center text-base font-medium tabular-nums")}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={commit}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              commit();
            } else if (event.key === "Escape") {
              setDraft(null);
            }
          }}
        />
        <button
          type="button"
          onClick={() => step(30)}
          disabled={atMax}
          aria-label="30 seconds more"
          className="flex size-9 shrink-0 items-center justify-center rounded-lg border border-line-strong bg-raised text-fg-muted hover:bg-overlay hover:text-fg disabled:opacity-40"
        >
          <Plus className="size-4" />
        </button>
        <span className="pl-1 text-xs text-fg-subtle">min:sec</span>
      </div>
      {problem && <p className="text-xs text-warning">Type minutes and seconds, like 5:00 or 1:30.</p>}
    </div>
  );
}

export function ChoiceWidget({ field, value, onChange, id, describedBy, invalid }: WidgetProps) {
  const options = field.options ?? [];
  const current = value == null ? null : String(value);
  if (options.length <= 4) {
    return (
      <Segments
        value={current}
        options={options}
        onChange={(next) => onChange(next)}
        aria-labelledby={`${id}-label`}
        aria-describedby={describedBy}
        invalid={invalid}
      />
    );
  }
  return (
    <Select value={current ?? undefined} onValueChange={(next) => onChange(next)}>
      <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid || undefined} className="h-9 rounded-lg text-sm">
        <SelectValue placeholder="Choose…" />
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option.value} value={option.value} className="text-sm">
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export function ToggleWidget({ field, value, onChange, id, describedBy }: WidgetProps) {
  return (
    <div className="flex items-start justify-between gap-3 rounded-lg border border-line bg-raised/40 px-3 py-2.5">
      <div className="min-w-0">
        <label htmlFor={id} className="text-[13px] font-medium text-fg">
          {field.title}
        </label>
        {field.description && (
          <p id={`${id}-help`} className="mt-0.5 text-xs leading-relaxed text-fg-subtle">
            {field.description}
          </p>
        )}
      </div>
      <Switch id={id} checked={value === true} onCheckedChange={(next) => onChange(next)} aria-describedby={describedBy} className="mt-0.5" />
    </div>
  );
}

const HEX = /^#[0-9a-f]{6}$/i;

/** Swatches from the theme, a "theme color" choice (null) and a custom picker. */
export function ColorWidget({ field, value, onChange, id, describedBy, invalid }: WidgetProps) {
  const { theme } = useFormContext();
  const current = typeof value === "string" && HEX.test(value) ? value.toUpperCase() : null;
  const swatches = Array.from(new Set([...(theme?.accent ?? []), theme?.text, theme?.bg].filter(Boolean).map((c) => c!.toUpperCase())));
  const [hexDraft, setHexDraft] = useState<string | null>(null);
  const custom = current && !swatches.includes(current);
  return (
    <div className="flex flex-col gap-2">
      <div role="radiogroup" aria-labelledby={`${id}-label`} aria-describedby={describedBy} aria-invalid={invalid || undefined} className="flex flex-wrap items-center gap-1.5">
        {field.nullable && (
          <button
            type="button"
            role="radio"
            aria-checked={current === null}
            onClick={() => onChange(null)}
            className={cn(
              "flex h-8 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium transition-colors",
              current === null ? "border-accent bg-accent-soft text-fg" : "border-line-strong text-fg-muted hover:text-fg",
            )}
          >
            <span aria-hidden className="size-3.5 rounded-full" style={{ background: theme?.accent?.[0] ?? "var(--color-accent)" }} />
            Theme color
          </button>
        )}
        {swatches.map((swatch) => (
          <button
            key={swatch}
            type="button"
            role="radio"
            aria-checked={current === swatch}
            aria-label={swatch}
            title={swatch}
            onClick={() => onChange(swatch)}
            className={cn(
              "size-8 rounded-full border-2 transition-transform hover:scale-105",
              current === swatch ? "border-fg ring-2 ring-accent/40" : "border-line-strong",
            )}
            style={{ background: swatch }}
          />
        ))}
        <label
          className={cn(
            "relative flex size-8 cursor-pointer items-center justify-center rounded-full border-2 text-fg-muted transition-transform hover:scale-105 focus-within:ring-2 focus-within:ring-accent",
            custom ? "border-fg" : "border-dashed border-line-strong",
          )}
          style={custom ? { background: current! } : undefined}
          title="Pick any color"
        >
          {!custom && <Palette className="size-4" />}
          <span className="sr-only">Pick any color</span>
          <input
            id={id}
            type="color"
            value={(current ?? theme?.accent?.[0] ?? "#2563EB").toLowerCase()}
            onChange={(event) => onChange(event.target.value.toUpperCase())}
            className="absolute inset-0 size-full cursor-pointer opacity-0"
          />
        </label>
        <input
          type="text"
          aria-label={`${field.title}, color code`}
          value={hexDraft ?? current ?? ""}
          placeholder={field.nullable ? "Theme" : "#2563EB"}
          maxLength={7}
          onChange={(event) => {
            const text = event.target.value.trim();
            setHexDraft(text);
            const hex = text.startsWith("#") ? text : `#${text}`;
            if (HEX.test(hex)) onChange(hex.toUpperCase());
            else if (!text && field.nullable) onChange(null);
          }}
          onBlur={() => setHexDraft(null)}
          className={cn(inputClass, "h-8 w-24 font-mono text-xs uppercase")}
        />
      </div>
    </div>
  );
}

/** Fallback for a field type the form has no widget for: its value as JSON. */
export function JsonWidget({ value, onChange, id, describedBy, invalid }: WidgetProps) {
  const [draft, setDraft] = useState<string | null>(null);
  const text = draft ?? JSON.stringify(value ?? null, null, 2);
  let problem = false;
  if (draft !== null) {
    try {
      JSON.parse(draft);
    } catch {
      problem = true;
    }
  }
  return (
    <textarea
      id={id}
      value={text}
      rows={4}
      aria-describedby={describedBy}
      aria-invalid={invalid || problem || undefined}
      onChange={(event) => {
        setDraft(event.target.value);
        try {
          onChange(JSON.parse(event.target.value));
        } catch {
          // keep the draft until it parses
        }
      }}
      onBlur={() => !problem && setDraft(null)}
      className={cn(inputClass, "py-2 font-mono text-xs")}
    />
  );
}
