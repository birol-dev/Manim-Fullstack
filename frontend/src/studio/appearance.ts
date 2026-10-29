import { APPEARANCE_KEY, CATEGORIES_KEY, readPreference, SIDEBAR_KEY, writePreference } from "./preferences";

export type Appearance = "light" | "dark" | "system";
export { APPEARANCE_KEY, SIDEBAR_KEY, CATEGORIES_KEY };

export function readAppearance(): Appearance {
  const value = readPreference("appearance");
  return value === "light" || value === "dark" ? value : "system";
}

export function readCollapsed(): boolean {
  return readPreference("sidebar_collapsed") === true;
}

/** The template categories' open state, or null until the person makes a choice. */
export function readCategoriesOpen(): boolean | null {
  const value = readPreference("template_categories_open");
  return typeof value === "boolean" ? value : null;
}

export function setAppearance(value: Appearance) {
  writePreference("appearance", value);
}

export function setCollapsed(value: boolean) {
  writePreference("sidebar_collapsed", value);
}

export function setCategoriesOpen(value: boolean | null) {
  writePreference("template_categories_open", value);
}
