export type Appearance = "light" | "dark" | "system";
export const APPEARANCE_KEY = "studio:appearance";
export const SIDEBAR_KEY = "studio:sidebar-collapsed";

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

export function storePreference(key: string, value: string) {
  try { localStorage.setItem(key, value); } catch { /* Keep the in-memory choice. */ }
}
