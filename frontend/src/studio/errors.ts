/** Field errors from 422 responses, matched to the form fields that show them. */
import { ApiError } from "@/lib/api";

import type { FieldError } from "./types";

/**
 * The field errors in an API error: the studio's `{detail, errors: [{field, message}]}`, or
 * FastAPI's own request validation `{detail: [{loc, msg}]}`. Empty for other errors.
 */
export function fieldErrorsOf(error: unknown): FieldError[] {
  if (!(error instanceof ApiError) || error.status !== 422) return [];
  const body = error.body as { errors?: unknown; detail?: unknown } | null;
  const out: FieldError[] = [];
  if (Array.isArray(body?.errors)) {
    for (const item of body.errors) {
      if (item && typeof item === "object" && typeof (item as FieldError).field === "string") {
        out.push({ field: (item as FieldError).field, message: String((item as FieldError).message ?? "Check this field.") });
      }
    }
  }
  if (!out.length && Array.isArray(body?.detail)) {
    for (const item of body.detail as Array<{ loc?: unknown[]; msg?: string }>) {
      const loc = Array.isArray(item?.loc) ? item.loc.filter((part) => part !== "body") : [];
      out.push({ field: loc.join("."), message: item?.msg ?? "Check this field." });
    }
  }
  return out;
}

/** Pydantic messages read like code ("Value error, Use a color..."); keep the human part. */
export function friendlyFieldMessage(message: string): string {
  const cleaned = message.replace(/^Value error,\s*/i, "").replace(/^Assertion failed,\s*/i, "");
  const tooLong = /String should have at most (\d+) characters?/i.exec(cleaned);
  if (tooLong) return `Use at most ${tooLong[1]} characters.`;
  const tooShort = /String should have at least (\d+) characters?/i.exec(cleaned);
  if (tooShort) return tooShort[1] === "1" ? "This can't be empty." : `Use at least ${tooShort[1]} characters.`;
  const max = /should be less than or equal to ([\d.]+)/i.exec(cleaned);
  if (max) return `Use ${max[1]} or less.`;
  const min = /should be greater than or equal to ([\d.]+)/i.exec(cleaned);
  if (min) return `Use ${min[1]} or more.`;
  const fewItems = /List should have at least (\d+) items?/i.exec(cleaned);
  if (fewItems) return `Add at least ${fewItems[1]}.`;
  const manyItems = /List should have at most (\d+) items?/i.exec(cleaned);
  if (manyItems) return `Use at most ${manyItems[1]}.`;
  if (/Input should be a valid number/i.test(cleaned)) return "Type a number.";
  if (/Input should be a valid integer/i.test(cleaned)) return "Type a whole number.";
  if (/Field required/i.test(cleaned)) return "This is needed.";
  if (/Input should be /i.test(cleaned) && /'[^']+'/.test(cleaned)) return "Pick one of the options.";
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}

export interface MatchedErrors {
  /** Messages by the field path that shows them. */
  byPath: Record<string, string[]>;
  /** Errors no field on screen can show. */
  unmatched: FieldError[];
}

/**
 * Match each error to the deepest known path that is a prefix of its field
 * ("params.accent.str" → "params.accent"; "params.items.2.value" stays exact when shown).
 */
export function matchErrors(errors: FieldError[], knownPaths: Iterable<string>): MatchedErrors {
  const known = new Set(knownPaths);
  const byPath: Record<string, string[]> = {};
  const unmatched: FieldError[] = [];
  for (const error of errors) {
    const parts = error.field.split(".").filter(Boolean);
    let matched: string | null = null;
    for (let length = parts.length; length > 0; length -= 1) {
      const candidate = parts.slice(0, length).join(".");
      if (known.has(candidate)) {
        matched = candidate;
        break;
      }
    }
    if (matched) (byPath[matched] ??= []).push(friendlyFieldMessage(error.message));
    else unmatched.push(error);
  }
  return { byPath, unmatched };
}

/** Does any error sit at or under *prefix* (to badge a collapsed list row or a tab)? */
export function hasErrorsUnder(byPath: Record<string, string[]>, prefix: string): boolean {
  return Object.keys(byPath).some((path) => path === prefix || path.startsWith(`${prefix}.`));
}
