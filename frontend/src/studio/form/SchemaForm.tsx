/** The form generated from a template's JSON Schema. */
import { createContext, useContext, useId, useState } from "react";
import { ChevronDown, ChevronUp, ChevronRight, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { hasErrorsUnder } from "../errors";
import { arrayChoiceChanges, arrayChoices, itemBadge, newItem, type ArrayChoice, type FieldSpec } from "../schemaForm";
import type { Params } from "../types";
import { useFormContext } from "./context";
import {
  ChoiceWidget,
  ArrayChoiceWidget,
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
  showEmphasisTip?: boolean;
  compactLabel?: string;
  arrayOptions?: ArrayChoice[];
}

const GROUP_WIDGETS = new Set(["choice", "color", "list", "table", "image", "icon"]);
const EmphasisPath = createContext<string | null | undefined>(undefined);

/** Follow field order, including repeated rows, to choose one hint per form. */
function firstEmphasisPath(fields: FieldSpec[], values: Params, prefix: string): string | null {
  for (const field of fields) {
    const path = `${prefix}.${field.key}`;
    if (field.emphasis) return path;
    const items = values[field.key];
    if (field.widget === "list" && field.itemFields && Array.isArray(items)) {
      for (let index = 0; index < items.length; index++) {
        const found = firstEmphasisPath(field.itemFields, (items[index] as Params) ?? {}, `${path}.${index}`);
        if (found) return found;
      }
    }
  }
  return null;
}

export function FieldRenderer({ field, value, onChange, path, showEmphasisTip = false, compactLabel, arrayOptions }: FieldRendererProps) {
  const id = useId();
  const { errors: allErrors } = useFormContext();
  const errors = allErrors[path] ?? [];
  const description = compactLabel ? undefined
    : field.widget === "choice" && field.optionHelp ? field.optionHelp[String(value ?? field.default ?? "")]
    : field.help ?? (showEmphasisTip || field.choiceOf ? undefined : field.description);
  const describedBy = [errors.length ? `${id}-error` : null, description ? `${id}-help` : null, showEmphasisTip ? `${id}-tip` : null].filter(Boolean).join(" ") || undefined;
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
      control = field.choiceOf ? <ArrayChoiceWidget {...props} options={arrayOptions ?? []} /> : <NumberWidget {...props} />;
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

  const group = !!field.choiceOf || (GROUP_WIDGETS.has(field.widget) && !(field.widget === "choice" && (field.options?.length ?? 0) > 4));
  return (
    <FieldShell
      id={id}
      labelId={`${id}-label`}
      label={compactLabel ?? field.title}
      compact={!!compactLabel}
      className={compactLabel ? "studio-compact-field" : undefined}
      description={description}
      errors={errors}
      group={group}
      counter={field.widget === "text" || field.widget === "textarea" ? (focused) => <Counter value={value} max={field.maxLength} focused={focused} /> : undefined}
      tip={
        showEmphasisTip ? (
          <>
            Tip: *best* → <strong className="text-accent">best</strong>
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
  onChange: (key: string, value: unknown, related?: Params) => void;
  prefix?: string;
  className?: string;
}

export function SchemaForm({ fields, values, onChange, prefix = "params", className }: SchemaFormProps) {
  const inherited = useContext(EmphasisPath);
  const emphasisPath = inherited === undefined ? firstEmphasisPath(fields, values, prefix) : inherited;
  return (
    <EmphasisPath.Provider value={emphasisPath}>
      <div className={cn("flex flex-col gap-7", className)}>
        {fields.map((field) => (
          <FieldRenderer
            key={field.key}
            field={field}
            value={values?.[field.key]}
            onChange={(value) => onChange(field.key, value, arrayChoiceChanges(fields, values, field.key, value))}
            arrayOptions={field.choiceOf ? arrayChoices(fields.find((source) => source.key === field.choiceOf), values) : undefined}
            path={`${prefix}.${field.key}`}
            showEmphasisTip={`${prefix}.${field.key}` === emphasisPath}
          />
        ))}
      </div>
    </EmphasisPath.Provider>
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
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set(items.length > 2 ? rowIds.keys.slice(1) : []));
  const min = field.minItems ?? 0;
  const max = field.maxItems ?? Infinity;
  const itemTitle = field.itemTitle || "Item";

  const update = (index: number, key: string, next: unknown, related: Params = {}) =>
    onChange(items.map((item, i) => (i === index ? { ...item, ...related, [key]: next } : item)));
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
        const actions = (
          <span className="studio-row-actions">
            <Button variant="ghost" size="icon-sm" onClick={() => move(index, index - 1)} disabled={index === 0} aria-label={`Move ${name} up`}><ChevronUp /></Button>
            <Button variant="ghost" size="icon-sm" onClick={() => move(index, index + 1)} disabled={index === items.length - 1} aria-label={`Move ${name} down`}><ChevronDown /></Button>
            <Button variant="danger-ghost" size="icon-sm" onClick={() => remove(index)} disabled={items.length <= min} aria-label={`Remove ${name}`}><Trash2 /></Button>
          </span>
        );
        if (fields.length === 1) {
          return (
            <div key={key} className={cn("studio-compact-item", broken && "studio-list-item-invalid")}>
              <span aria-hidden className="studio-item-badge">{itemBadge(itemTitle, index)}</span>
              <FieldRenderer field={fields[0]} value={item?.[fields[0].key]} onChange={(next) => update(index, fields[0].key, next)} path={`${path}.${index}.${fields[0].key}`} compactLabel={name} />
              {actions}
            </div>
          );
        }
        return (
          <div key={key} className={cn("studio-list-item", broken && "studio-list-item-invalid")}>
            <div className="studio-list-heading">
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
              {actions}
            </div>
            {open && (
              <SchemaForm
                className="gap-4 border-t border-line px-3 pb-3 pt-3"
                fields={fields}
                values={item ?? {}}
                onChange={(fieldKey, next, related) => update(index, fieldKey, next, related)}
                prefix={`${path}.${index}`}
              />
            )}
          </div>
        );
      })}
      <div className="flex items-center gap-2">
        <Button size="md" className="studio-add-row" onClick={add} disabled={items.length >= max}>
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
