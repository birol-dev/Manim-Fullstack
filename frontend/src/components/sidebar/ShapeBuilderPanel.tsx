import { useMemo, useState } from "react";
import { Check, Copy, CornerDownLeft } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { Section } from "@/components/ui/panel";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { MANIM_COLORS, type ManimColorName } from "@/lib/constants";
import {
  ANIMATION_LABELS,
  buildShapeCode,
  DEFAULT_SHAPE_OPTIONS,
  defaultVariableName,
  EMPHASIS_ANIMATIONS,
  ENTRY_ANIMATIONS,
  EXIT_ANIMATIONS,
  isFillable,
  SHAPES,
  type ShapeKind,
  type ShapeOptions,
} from "@/lib/shapeBuilder";
import { cn } from "@/lib/utils";
import { SidebarPanel } from "./SidebarPanel";

interface ShapeBuilderPanelProps {
  canInsert: boolean;
  onInsert: (code: string) => void;
}

type NumberField = "scale" | "rotation" | "shiftX" | "shiftY";

const NUMBER_FIELDS: Array<{ key: NumberField; label: string; step: number }> = [
  { key: "scale", label: "Scale", step: 0.1 },
  { key: "rotation", label: "Rotate (°)", step: 15 },
  { key: "shiftX", label: "Shift X", step: 0.5 },
  { key: "shiftY", label: "Shift Y", step: 0.5 },
];

function OptionSelect<T extends string>({
  id,
  value,
  options,
  onChange,
}: {
  id: string;
  value: T;
  options: readonly T[];
  onChange: (value: T) => void;
}) {
  return (
    <Select value={value} onValueChange={(next) => onChange(next as T)}>
      <SelectTrigger id={id}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option} value={option}>
            {ANIMATION_LABELS[option] ?? option}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export function ShapeBuilderPanel({ canInsert, onInsert }: ShapeBuilderPanelProps) {
  const [options, setOptions] = useState<ShapeOptions>(DEFAULT_SHAPE_OPTIONS);
  // Keep raw text for number inputs so "-" or "1." can be typed.
  const [numbers, setNumbers] = useState<Record<NumberField, string>>({ scale: "1", rotation: "0", shiftX: "0", shiftY: "0" });
  const [copied, setCopied] = useState(false);

  const update = <K extends keyof ShapeOptions>(key: K, value: ShapeOptions[K]) =>
    setOptions((previous) => ({ ...previous, [key]: value }));

  const code = useMemo(() => {
    const parsed = Object.fromEntries(
      Object.entries(numbers).map(([key, raw]) => [key, Number.parseFloat(raw)]),
    ) as Record<NumberField, number>;
    return buildShapeCode({
      ...options,
      scale: Number.isFinite(parsed.scale) ? parsed.scale : 1,
      rotation: Number.isFinite(parsed.rotation) ? parsed.rotation : 0,
      shiftX: Number.isFinite(parsed.shiftX) ? parsed.shiftX : 0,
      shiftY: Number.isFinite(parsed.shiftY) ? parsed.shiftY : 0,
    });
  }, [options, numbers]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Couldn't copy to the clipboard.");
    }
  };

  return (
    <SidebarPanel title="Shape builder">
      <div className="flex flex-col gap-4">
        <p className="px-1 text-xs leading-relaxed text-fg-subtle">
          Configure an object and its animations, then insert the code into your scene at the cursor.
        </p>

        <Section title="Object">
          <div className="flex flex-col gap-3 px-1">
            <div className="grid grid-cols-2 gap-2">
              <Field label="Type" htmlFor="shape-kind">
                <Select value={options.shape} onValueChange={(value) => update("shape", value as ShapeKind)}>
                  <SelectTrigger id="shape-kind">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SHAPES.map((shape) => (
                      <SelectItem key={shape} value={shape}>
                        {shape}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field label="Variable" htmlFor="shape-variable">
                <Input
                  id="shape-variable"
                  value={options.variable}
                  placeholder={defaultVariableName(options.shape)}
                  onChange={(event) => update("variable", event.target.value)}
                  className="font-mono"
                  spellCheck={false}
                />
              </Field>
            </div>

            {options.shape === "Text" && (
              <Field label="Text" htmlFor="shape-text">
                <Input id="shape-text" value={options.text} onChange={(event) => update("text", event.target.value)} />
              </Field>
            )}
            {options.shape === "MathTex" && (
              <Field label="LaTeX" htmlFor="shape-latex" hint="Rendering MathTex needs LaTeX installed.">
                <Input
                  id="shape-latex"
                  value={options.latex}
                  onChange={(event) => update("latex", event.target.value)}
                  className="font-mono"
                  spellCheck={false}
                />
              </Field>
            )}

            <div className="flex flex-col gap-1.5">
              <span className="text-2xs font-medium text-fg-muted">
                Color <span className="font-mono text-fg-subtle">{options.color}</span>
              </span>
              <div className="grid grid-cols-6 gap-1.5" role="radiogroup" aria-label="Color">
                {MANIM_COLORS.map((color) => (
                  <button
                    key={color.name}
                    type="button"
                    role="radio"
                    aria-checked={options.color === color.name}
                    aria-label={color.name}
                    title={color.name}
                    onClick={() => update("color", color.name as ManimColorName)}
                    className={cn(
                      "h-6 rounded-md border border-black/40 transition-transform hover:scale-105",
                      options.color === color.name && "ring-2 ring-fg ring-offset-2 ring-offset-surface",
                    )}
                    style={{ backgroundColor: color.hex }}
                  />
                ))}
              </div>
            </div>

            {isFillable(options.shape) && (
              <label className="flex items-center justify-between gap-2 text-xs text-fg-muted">
                Fill with color
                <Switch checked={options.fill} onCheckedChange={(checked) => update("fill", checked)} aria-label="Fill with color" />
              </label>
            )}
          </div>
        </Section>

        <Section title="Transform">
          <div className="grid grid-cols-2 gap-2 px-1">
            {NUMBER_FIELDS.map((field) => (
              <Field key={field.key} label={field.label} htmlFor={`shape-${field.key}`}>
                <Input
                  id={`shape-${field.key}`}
                  type="number"
                  inputMode="decimal"
                  step={field.step}
                  value={numbers[field.key]}
                  onChange={(event) => setNumbers((previous) => ({ ...previous, [field.key]: event.target.value }))}
                  className="font-mono tabular-nums"
                />
              </Field>
            ))}
          </div>
        </Section>

        <Section title="Animation">
          <div className="flex flex-col gap-2 px-1">
            <Field label="Enter" htmlFor="shape-entry">
              <OptionSelect id="shape-entry" value={options.entry} options={ENTRY_ANIMATIONS} onChange={(value) => update("entry", value)} />
            </Field>
            <Field label="Emphasize" htmlFor="shape-emphasis">
              <OptionSelect id="shape-emphasis" value={options.emphasis} options={EMPHASIS_ANIMATIONS} onChange={(value) => update("emphasis", value)} />
            </Field>
            <Field label="Exit" htmlFor="shape-exit">
              <OptionSelect id="shape-exit" value={options.exit} options={EXIT_ANIMATIONS} onChange={(value) => update("exit", value)} />
            </Field>
          </div>
        </Section>

        <Section
          title="Code"
          actions={
            <Button variant="ghost" size="icon-xs" aria-label="Copy code" onClick={() => void copy()}>
              {copied ? <Check className="text-success" /> : <Copy />}
            </Button>
          }
        >
          <pre
            aria-label="Generated code"
            className="overflow-x-auto rounded-lg border border-line bg-canvas p-2.5 font-mono text-[11.5px] leading-relaxed text-fg-muted select-text"
          >
            {code}
          </pre>
        </Section>

        <Button variant="primary" size="md" disabled={!canInsert} onClick={() => onInsert(code)} className="w-full">
          <CornerDownLeft />
          Insert into scene
        </Button>
      </div>
    </SidebarPanel>
  );
}
