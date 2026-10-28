import { createContext, useContext } from "react";

import type { Theme } from "../types";

export interface FormContextValue {
  /** Number formatting of the video (table cells, number fields). */
  locale: string;
  /** The video's theme: its colors are offered by color fields. */
  theme: Theme | undefined;
  /** Error messages by field path ("params.items.2.value"). */
  errors: Record<string, string[]>;
}

export const FormContext = createContext<FormContextValue>({ locale: "en", theme: undefined, errors: {} });

export const useFormContext = () => useContext(FormContext);

export function useFieldErrors(path: string): string[] {
  return useContext(FormContext).errors[path] ?? [];
}
