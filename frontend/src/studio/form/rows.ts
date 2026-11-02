import { useState } from "react";

let lastRowId = 0;
export const newRowId = () => `row-${++lastRowId}`;

/**
 * Stable React keys for the rows of a list or table, so moving or removing a row keeps each
 * row's inputs (and focus) with its own data. Rows added from outside get index keys.
 */
export function useRowIds(count: number) {
  const [ids, setIds] = useState<string[]>(() => Array.from({ length: count }, newRowId));
  const keys = Array.from({ length: count }, (_, index) => ids[index] ?? `extra-${index}`);
  return {
    keys,
    add: (n = 1) => setIds([...keys, ...Array.from({ length: n }, newRowId)]),
    remove: (index: number) => setIds(keys.filter((_, i) => i !== index)),
    move: (from: number, to: number) => {
      const next = [...keys];
      [next[from], next[to]] = [next[to], next[from]];
      setIds(next);
    },
  };
}

export function moveItem<T>(items: T[], from: number, to: number): T[] {
  if (to < 0 || to >= items.length) return items;
  const next = [...items];
  [next[from], next[to]] = [next[to], next[from]];
  return next;
}
