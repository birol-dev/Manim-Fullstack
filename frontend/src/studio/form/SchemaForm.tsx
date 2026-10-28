/** The form generated from a template's JSON Schema. */
import { useId, useState } from "react";
import { ChevronDown, ChevronUp, ChevronRight, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { hasErrorsUnder } from "../errors";
import { newItem, type FieldSpec } from "../schemaForm";
import type { Params } from "../types";
import { useFormContext } from "./context";
import {
  ChoiceWidget,
  ColorWidget,
  Counter,
  DurationWidget,
  FieldShell,
  JsonWidget,
  NumberWidget,
  TextWidget,
  ToggleWidget,
  type WidgetProps,
} from "./fields";
import { IconWidget, ImageWidget } from "./media";
import { moveItem, useRowIds } from "./rows";
import { TableWidget } from "./TableWidget";

interface FieldRendererProps {
  field: FieldSpec;
  value: unknown;
  onChange: (value: unknown) => void;
  /** Value path for errors, e.g. "params.items.2.value". */
  path: string;
}

const GROUP_WIDGETS = new Set(["choice", "color", "list", "table", "image", "icon"]);

export function FieldRenderer({ field, value, onChange, path }: FieldRendererProps) {
  const id = useId();
  const { errors: allErrors } = useFormContext();
  const errors = allErrors[path] ?? [];
  const describedBy = [errors.length ? `${id}-error` : null, field.description ? `${id}-help` : null].filter(Boolean).join(" ") || undefined;
  const props: WidgetProps = { field, value, onChange, id, describedBy, invalid: errors.length > 0 };

  if (field.widget === "toggle") {
    return (
      <div className="flex flex-col gap-1.5">
        <ToggleWidget {...props} />
        {errors.length > 0 && (
          <p id={`${id}-error`} role="alert" className="text-xs text-danger">
            {errors.join(" ")}
          </p>
        )}
      </div>
    );
  }

  let control;
  switch (field.widget) {
    case "text":
    case "textarea":
      control = <TextWidget {...props} />;
      break;
    case "number":
    case "integer":
      control = <NumberWidget {...props} />;
      break;
    case "duration":
      control = <DurationWidget {...props} />;
      break;
    case "choice":
      control = <ChoiceWidget {...props} />;
      break;
    case "color":
      control = <ColorWidget {...props} />;
      break;
    case "image":
      control = <ImageWidget {...props} />;
      break;
    case "icon":
      control = <IconWidget {...props} />;
      break;
    case "list":
      control = <ListWidget field={field} value={value} onChange={onChange} path={path} id={id} />;
      break;
    case "table":
      control = <TableWidget field={field} value={value} onChange={onChange} path={path} id={id} describedBy={describedBy} />;
      break;
    default:
      control = <JsonWidget {...props} />;
  }

  const group = GROUP_WIDGETS.has(field.widget) && !(field.widget === "choice" && (field.options?.length ?? 0) > 4);
  return (
    <FieldShell
      id={id}
      labelId={`${id}-label`}
      label={field.title}
      description={field.description}
      errors={errors}
      group={group}
      counter={field.widget === "text" || field.widget === "textarea" ? <Counter value={value} max={field.maxLength} /> : undefined}
      tip={
        field.emphasis ? (
          <>
            Tip: *best* becomes <span className="font-semibold text-accent">best</span>, in the theme's highlight color.
          </>
        ) : undefined
      }
    >
      {control}
    </FieldShell>
  );
}

interface SchemaFormProps {
  fields: FieldSpec[];
  values: Params;
  onChange: (key: string, value: unknown) => void;
  prefix?: string;
  className?: string;
}

export function SchemaForm({ fields, values, onChange, prefix = "params", className }: SchemaFormProps) {
  return (
    <div className={cn("flex flex-col gap-5", className)}>
      {fields.map((field) => (
        <FieldRenderer
          key={field.key}
          field={field}
          value={values?.[field.key]}
          onChange={(value) => onChange(field.key, value)}
          path={`${prefix}.${field.key}`}
        />
      ))}
    </div>
  );
}

/** A short summary of a row for its header: its first non-empty text. */
function itemSummary(item: Params | undefined, fields: FieldSpec[]): string {
  for (const field of fields) {
    const value = item?.[field.key];
    if ((field.widget === "text" || field.widget === "textarea") && typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

interface ListWidgetProps {
  field: FieldSpec;
  value: unknown;
  onChange: (value: unknown) => void;
  path: string;
  id: string;
}

/** Repeated groups as cards with add / remove / move up-down. */
export function ListWidget({ field, value, onChange, path, id }: ListWidgetProps) {
  const { errors } = useFormContext();
  const items = Array.isArray(value) ? (value as Params[]) : [];
  const fields = field.itemFields ?? [];
  const rowIds = useRowIds(items.length);
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set());
  const min = field.minItems ?? 0;
  const max = field.maxItems ?? Infinity;
  const itemTitle = field.itemTitle || "Item";

  const update = (index: number, key: string, next: unknown) =>
    onChange(items.map((item, i) => (i === index ? { ...item, [key]: next } : item)));
  const add = () => {
    rowIds.add();
    onChange([...items, newItem(fields)]);
  };
  const remove = (index: number) => {
    rowIds.remove(index);
    onChange(items.filter((_, i) => i !== index));
  };
  const move = (from: number, to: number) => {
    if (to < 0 || to >= items.length) return;
    rowIds.move(from, to);
    onChange(moveItem(items, from, to));
  };
  const toggle = (key: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  return (
    <div role="group" aria-labelledby={`${id}-label`} className="flex flex-col gap-2">
      {items.map((item, index) => {
        const key = rowIds.keys[index];
        const open = !collapsed.has(key);
        const summary = itemSummary(item, fields);
        const name = `${itemTitle} ${index + 1}`;
        const broken = hasErrorsUnder(errors, `${path}.${index}`);
        return (
          <div key={key} className={cn("rounded-xl border bg-raised/30", broken ? "border-danger/60" : "border-line-strong")}>
            <div className="flex items-center gap-1 py-1 pl-1 pr-1.5">
              <button
                type="button"
                onClick={() => toggle(key)}
                aria-expanded={open}
                className="flex min-w-0 flex-1 items-center gap-1.5 rounded-md px-1.5 py-1 text-left hover:bg-raised"
              >
                <ChevronRight aria-hidden className={cn("size-4 shrink-0 text-fg-subtle transition-transform", open && "rotate-90")} />
                <span className="shrink-0 text-[13px] font-medium text-fg">{name}</span>
                {summary && <span className="truncate text-xs text-fg-subtle">· {summary}</span>}
                {broken && <span className="ml-1 size-1.5 shrink-0 rounded-full bg-danger" aria-label="has a problem" />}
              </button>
              <Button variant="ghost" size="icon-sm" onClick={() => move(index, index - 1)} disabled={index === 0} aria-label={`Move ${name} up`}>
                <ChevronUp />
              </Button>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => move(index, index + 1)}
                disabled={index === items.length - 1}
                aria-label={`Move ${name} down`}
              >
                <ChevronDown />
              </Button>
              <Button variant="danger-ghost" size="icon-sm" onClick={() => remove(index)} disabled={items.length <= min} aria-label={`Remove ${name}`}>
                <Trash2 />
              </Button>
            </div>
            {open && (
              <SchemaForm
                className="gap-4 border-t border-line px-3 pb-3 pt-3"
                fields={fields}
                values={item ?? {}}
                onChange={(fieldKey, next) => update(index, fieldKey, next)}
                prefix={`${path}.${index}`}
              />
            )}
          </div>
        );
      })}
      <div className="flex items-center gap-2">
        <Button size="sm" onClick={add} disabled={items.length >= max}>
          <Plus />
          Add {itemTitle.toLowerCase()}
        </Button>
        {Number.isFinite(max) && (
          <span className="text-xs text-fg-subtle">
            {items.length} of {max}
          </span>
        )}
      </div>
    </div>
  );
}
