/** A spreadsheet-like grid for list fields drawn as a table. Accepts rows pasted from Excel / Sheets. */
import { useRef, useState, type ClipboardEvent, type KeyboardEvent } from "react";
import { ClipboardPaste, Plus, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { ColorPickerButton } from "../ColorPicker";
import { newItem, type FieldSpec } from "../schemaForm";
import { formatCellNumber, isMultiCell, parseLocaleNumber, pasteIntoRows } from "../table";
import type { Params } from "../types";
import { useFormContext } from "./context";
import { useRowIds } from "./rows";

const cellClass =
  "h-8 w-full min-w-0 rounded-md border border-transparent bg-transparent px-2 text-[13px] text-fg placeholder:text-fg-subtle hover:border-line-strong focus-visible:border-accent focus-visible:bg-raised focus-visible:outline-none aria-[invalid=true]:border-danger";

interface CellProps {
  column: FieldSpec;
  value: unknown;
  onChange: (value: unknown) => void;
  label: string;
  invalid: boolean;
  locale: string;
  onPaste: (event: ClipboardEvent<HTMLElement>) => void;
  onKeyDown: (event: KeyboardEvent<HTMLElement>) => void;
  cellRef: (element: HTMLElement | null) => void;
}

function NumberCell({ column, value, onChange, label, invalid, locale, onPaste, onKeyDown, cellRef }: CellProps) {
  const [draft, setDraft] = useState<string | null>(null);
  const bad = draft !== null && draft.trim() !== "" && parseLocaleNumber(draft, locale) === null;
  return (
    <input
      ref={cellRef}
      type="text"
      inputMode="decimal"
      aria-label={label}
      aria-invalid={invalid || bad || undefined}
      value={draft ?? formatCellNumber(value, locale)}
      onChange={(event) => {
        const text = event.target.value;
        setDraft(text);
        const number = parseLocaleNumber(text, locale);
        if (number !== null) onChange(number);
        else onChange(text.trim() === "" && column.nullable ? null : text);
      }}
      onBlur={() => setDraft(null)}
      onPaste={(event) => {
        onPaste(event);
        if (event.defaultPrevented) setDraft(null);
      }}
      onKeyDown={onKeyDown}
      className={cn(cellClass, "text-right tabular-nums")}
    />
  );
}

function Cell(props: CellProps) {
  const { column, value, onChange, label, invalid, onPaste, onKeyDown, cellRef } = props;
  const { theme } = useFormContext();
  if (column.widget === "number" || column.widget === "integer" || column.widget === "duration") return <NumberCell {...props} />;
  if (column.widget === "toggle") {
    return (
      <div className="flex h-8 items-center justify-center">
        <input
          ref={cellRef}
          type="checkbox"
          aria-label={label}
          checked={value === true}
          onChange={(event) => onChange(event.target.checked)}
          onKeyDown={onKeyDown}
          className="size-4 accent-[var(--color-accent)]"
        />
      </div>
    );
  }
  if (column.widget === "choice") {
    return (
      <select
        ref={cellRef}
        aria-label={label}
        aria-invalid={invalid || undefined}
        value={value == null ? "" : String(value)}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={onKeyDown}
        className={cn(cellClass, "cursor-pointer")}
      >
        {(column.options ?? []).map((option) => (
          <option key={option.value} value={option.value} className="bg-overlay">
            {option.label}
          </option>
        ))}
      </select>
    );
  }
  if (column.widget === "color") {
    const hex = typeof value === "string" && /^#[0-9a-f]{6}$/i.test(value) ? value : "#2563eb";
    return (
      <div className="flex h-8 items-center justify-center gap-1">
        <ColorPickerButton ref={cellRef} aria-label={label} aria-invalid={invalid || undefined} value={hex} swatches={[...new Set([...(theme?.accent ?? []), theme?.text, theme?.bg].filter((c): c is string => !!c).map((c) => c.toUpperCase()))]} onChange={onChange} onKeyDown={(event) => { if (event.key !== "Enter" && event.key !== " ") onKeyDown(event); }} className="studio-table-color" style={{ background: hex }}><span className="sr-only">Choose color</span></ColorPickerButton>
        {column.nullable && value != null && (
          <button type="button" onClick={() => onChange(null)} aria-label={`${label}: use the theme color`} className="text-fg-subtle hover:text-fg">
            <X className="size-3.5" />
          </button>
        )}
      </div>
    );
  }
  return (
    <input
      ref={cellRef}
      type="text"
      aria-label={label}
      aria-invalid={invalid || undefined}
      value={value == null ? "" : String(value)}
      maxLength={column.maxLength}
      placeholder={column.placeholder}
      onChange={(event) => onChange(column.nullable && event.target.value === "" ? null : event.target.value)}
      onPaste={onPaste}
      onKeyDown={onKeyDown}
      className={cellClass}
    />
  );
}

interface TableWidgetProps {
  field: FieldSpec;
  value: unknown;
  onChange: (value: unknown) => void;
  path: string;
  id: string;
  describedBy?: string;
}

export function TableWidget({ field, value, onChange, path, id, describedBy }: TableWidgetProps) {
  const { locale, errors } = useFormContext();
  const rows = Array.isArray(value) ? (value as Params[]) : [];
  const columns = field.itemFields ?? [];
  const rowIds = useRowIds(rows.length);
  const [notice, setNotice] = useState<string | null>(null);
  const cells = useRef(new Map<string, HTMLElement>());
  const min = field.minItems ?? 0;
  const max = field.maxItems ?? Infinity;
  const rowWord = (field.itemTitle || "row").toLowerCase();

  const setCell = (rowIndex: number, key: string, cellValue: unknown) =>
    onChange(rows.map((row, index) => (index === rowIndex ? { ...row, [key]: cellValue } : row)));

  const addRow = () => {
    if (rows.length >= max) return;
    rowIds.add();
    onChange([...rows, newItem(columns)]);
    setNotice(null);
    // Focus the new row's first cell once it exists.
    window.setTimeout(() => cells.current.get(`${rows.length}:0`)?.focus(), 0);
  };

  const removeRow = (index: number) => {
    if (rows.length <= min) return;
    rowIds.remove(index);
    onChange(rows.filter((_, i) => i !== index));
  };

  const paste = (event: ClipboardEvent<HTMLElement>, row: number, column: number) => {
    const text = event.clipboardData?.getData("text/plain") ?? "";
    if (!isMultiCell(text)) return;
    event.preventDefault();
    const result = pasteIntoRows(rows, columns, text, { row, column }, { locale, maxItems: field.maxItems, makeRow: () => newItem(columns) });
    const added = result.rows.length - rows.length;
    if (added > 0) rowIds.add(added);
    onChange(result.rows);
    const parts = [`Pasted ${result.pasted} ${result.pasted === 1 ? "row" : "rows"}${result.header ? " (the header row was left out)" : ""}.`];
    if (result.skipped.length) {
      parts.push(
        `${result.skipped.length} ${result.skipped.length === 1 ? "cell was" : "cells were"} skipped (${result.skipped.slice(0, 3).join("; ")}${result.skipped.length > 3 ? "…" : ""}).`,
      );
    }
    if (result.dropped) parts.push(`${result.dropped} ${result.dropped === 1 ? "row didn't" : "rows didn't"} fit: the limit is ${max}.`);
    setNotice(parts.join(" "));
  };

  const keyDown = (event: KeyboardEvent<HTMLElement>, row: number, column: number) => {
    const target = event.key === "Enter" || event.key === "ArrowDown" ? row + 1 : event.key === "ArrowUp" ? row - 1 : null;
    if (target === null || (event.target as HTMLElement).tagName === "SELECT") return;
    const next = cells.current.get(`${target}:${column}`);
    if (next) {
      event.preventDefault();
      next.focus();
    } else if (event.key === "Enter" && target === rows.length && rows.length < max) {
      event.preventDefault();
      addRow();
      window.setTimeout(() => cells.current.get(`${target}:${column}`)?.focus(), 0);
    }
  };

  const cellErrors: string[] = [];
  rows.forEach((_, rowIndex) => {
    columns.forEach((column) => {
      for (const message of errors[`${path}.${rowIndex}.${column.key}`] ?? []) cellErrors.push(`Row ${rowIndex + 1}, ${column.title}: ${message}`);
    });
    for (const message of errors[`${path}.${rowIndex}`] ?? []) cellErrors.push(`Row ${rowIndex + 1}: ${message}`);
  });

  return (
    <div className="flex flex-col gap-2" role="group" aria-labelledby={`${id}-label`} aria-describedby={describedBy}>
      <div className="studio-table-well overflow-x-auto">
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="bg-raised">
              <th scope="col" className="w-8 border-b border-line-strong px-2 py-1.5 text-center text-xs font-medium text-fg-subtle">
                #
              </th>
              {columns.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  title={column.help ?? column.description}
                  className={cn(
                    "border-b border-l border-line-strong px-2 py-1.5 text-xs font-medium text-fg-muted",
                    (column.widget === "number" || column.widget === "integer") && "text-right",
                  )}
                >
                  {column.title}
                  {column.unit ? <span className="font-normal text-fg-subtle"> ({column.unit})</span> : null}
                </th>
              ))}
              <th scope="col" className="w-8 border-b border-l border-line-strong">
                <span className="sr-only">Remove</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={rowIds.keys[rowIndex]} className="studio-table-row border-b border-line last:border-b-0">
                <td className="px-2 text-center text-xs tabular-nums text-fg-subtle">{rowIndex + 1}</td>
                {columns.map((column, columnIndex) => (
                  <td key={column.key} className="min-w-24 border-l border-line p-0.5">
                    <Cell
                      column={column}
                      value={row?.[column.key]}
                      locale={locale}
                      label={`${column.title}, row ${rowIndex + 1}`}
                      invalid={!!errors[`${path}.${rowIndex}.${column.key}`]?.length}
                      onChange={(cellValue) => setCell(rowIndex, column.key, cellValue)}
                      onPaste={(event) => paste(event, rowIndex, columnIndex)}
                      onKeyDown={(event) => keyDown(event, rowIndex, columnIndex)}
                      cellRef={(element) => {
                        if (element) cells.current.set(`${rowIndex}:${columnIndex}`, element);
                        else cells.current.delete(`${rowIndex}:${columnIndex}`);
                      }}
                    />
                  </td>
                ))}
                <td className="border-l border-line p-0.5 text-center">
                  <button
                    type="button"
                    onClick={() => removeRow(rowIndex)}
                    disabled={rows.length <= min}
                    aria-label={`Remove row ${rowIndex + 1}`}
                    className="studio-table-remove inline-flex size-7 items-center justify-center rounded-md text-fg-subtle hover:bg-danger-soft hover:text-danger disabled:pointer-events-none disabled:opacity-30"
                  >
                    <X className="size-3.5" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {cellErrors.length > 0 && (
        <ul role="alert" className="flex flex-col gap-0.5 text-xs text-danger">
          {cellErrors.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Button size="md" className="studio-add-row" onClick={addRow} disabled={rows.length >= max}>
          <Plus />
          Add {rowWord}
        </Button>
        <span className="text-xs text-fg-subtle">
          {rows.length}
          {Number.isFinite(max) ? ` of ${max}` : ""} {rows.length === 1 ? "row" : "rows"}
        </span>
        <span className="ml-auto flex items-center gap-1 text-xs text-fg-subtle">
          <ClipboardPaste aria-hidden className="size-3.5" />
          Paste cells from Excel or Google Sheets
        </span>
      </div>
      {notice && (
        <p role="status" className="text-xs text-fg-muted">
          {notice}
        </p>
      )}
    </div>
  );
}
