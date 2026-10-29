export type Appearance = "light" | "dark" | "system";
export const APPEARANCE_KEY = "studio:appearance";
export const SIDEBAR_KEY = "studio:sidebar-collapsed";
export const CATEGORIES_KEY = "studio:template-categories-open";

export function readAppearance(): Appearance {
  try {
    const value = localStorage.getItem(APPEARANCE_KEY);
    if (value === "light" || value === "dark") return value;
  } catch { /* Local preferences are optional when storage is unavailable. */ }
  return "system";
}

export function readCollapsed(): boolean {
  try { return localStorage.getItem(SIDEBAR_KEY) === "true"; } catch { return false; }
}

/** The template categories' open state, or null until the person makes a choice. */
export function readCategoriesOpen(): boolean | null {
  try {
    const value = localStorage.getItem(CATEGORIES_KEY);
    if (value === "true") return true;
    if (value === "false") return false;
  } catch { /* Local preferences are optional when storage is unavailable. */ }
  return null;
}

export function storePreference(key: string, value: string) {
  try { localStorage.setItem(key, value); } catch { /* Keep the in-memory choice. */ }
}
