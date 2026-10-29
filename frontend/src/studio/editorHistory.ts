import { stableKey } from "./preview";

/** Immutable snapshots; grouping affects history only, never autosave timing. */
export class EditorHistory<T> {
  current: T;
  private past: T[] = [];
  private future: T[] = [];
  private group: unknown = null;
  private time = 0;
  private limit: number;
  constructor(initial: T, limit = 100) { this.current = initial; this.limit = limit; }
  get canUndo() { return this.past.length > 0; }
  get canRedo() { return this.future.length > 0; }
  boundary() { this.group = null; }
  change(next: T, group: unknown = null, now = Date.now()) {
    if (stableKey(next) === stableKey(this.current)) return false;
    if (!group || group !== this.group || now - this.time >= 600 || this.future.length) {
      this.past.push(this.current);
      if (this.past.length > this.limit) this.past.shift();
    }
    this.current = next;
    this.future = [];
    this.group = group;
    this.time = now;
    return true;
  }
  undo() {
    if (!this.canUndo) return false;
    this.future.push(this.current);
    this.current = this.past.pop()!;
    this.boundary();
    return true;
  }
  redo() {
    if (!this.canRedo) return false;
    this.past.push(this.current);
    this.current = this.future.pop()!;
    this.boundary();
    return true;
  }
}

export function isTextEditor(target: EventTarget | null): target is HTMLElement {
  return target instanceof HTMLElement && (target.isContentEditable || target instanceof HTMLTextAreaElement ||
    (target instanceof HTMLInputElement && ["text", "search", "email", "url", "tel", "password", "number"].includes(target.type)));
}
