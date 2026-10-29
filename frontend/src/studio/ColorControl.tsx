import { useState } from "react";
import { ColorPickerButton } from "./ColorPicker";
import { parseHex, rememberColor } from "./color";

import { cn } from "@/lib/utils";

import { inputClass } from "./components";
import type { Theme } from "./types";

const HEX = /^#[0-9a-f]{6}$/i;

/** Shared by content colours and Look's background/gradient colours. */
export function ColorControl({ id, label, value, onChange, theme, fallback, nullable = true, pickerLabel = "Pick any color", describedBy, invalid }: {
  id: string;
  label: string;
  value: unknown;
  onChange: (value: string | null) => void;
  theme?: Theme;
  fallback?: string;
  nullable?: boolean;
  pickerLabel?: string;
  describedBy?: string;
  invalid?: boolean;
}) {
  const current = typeof value === "string" && HEX.test(value) ? value.toUpperCase() : null;
  const swatches = Array.from(new Set([...(theme?.accent ?? []), theme?.text, theme?.bg].filter((color): color is string => !!color).map((color) => color.toUpperCase())));
  const custom = current !== null && !swatches.includes(current);
  const [draft, setDraft] = useState<string | null>(null);
  const defaultColor = fallback ?? theme?.accent?.[0] ?? "#2563EB";
  const light = custom && (parseInt(current.slice(1, 3), 16) * .299 + parseInt(current.slice(3, 5), 16) * .587 + parseInt(current.slice(5, 7), 16) * .114) > 160;
  return (
    <div className="studio-color-control">
      <div role="radiogroup" aria-labelledby={`${id}-label`} aria-describedby={describedBy} aria-invalid={invalid || undefined} className="studio-color-strip">
        {nullable && (
          <button type="button" role="radio" aria-checked={current === null} onClick={() => onChange(null)} className={cn("studio-theme-color", current === null && "studio-color-selected")}>
            <span aria-hidden style={{ background: defaultColor }} />Theme color
          </button>
        )}
        {swatches.map((swatch) => (
          <button key={swatch} type="button" role="radio" aria-checked={current === swatch} aria-label={swatch} title={swatch} onClick={() => onChange(swatch)} className={cn("studio-color-swatch", current === swatch && "studio-color-selected")} style={{ background: swatch }} />
        ))}
        <ColorPickerButton id={id} className={cn("studio-custom-color", custom && "studio-color-selected")} style={custom ? { background: current, color: light ? "#18181B" : "#FFFFFF" } : undefined} title={pickerLabel} aria-label={pickerLabel} aria-describedby={describedBy} aria-invalid={invalid || undefined} value={current ?? defaultColor} swatches={swatches} onChange={(hex) => { setDraft(null); onChange(hex); }} />
      </div>
      {custom && (
        <input type="text" aria-label={`${label}, color code`} value={draft ?? current} placeholder="#FF3366" maxLength={7} onChange={(event) => {
          const text = event.target.value.trim();
          setDraft(text);
          const hex = parseHex(text);
          if (hex) onChange(hex);
          else if (!text && nullable) onChange(null);
        }} onBlur={() => {
          const hex = parseHex(draft ?? current);
          if (hex && !swatches.includes(hex)) rememberColor(hex);
          setDraft(null);
        }} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); event.currentTarget.blur(); } }} className={cn(inputClass, "studio-color-code")} />
      )}
    </div>
  );
}
