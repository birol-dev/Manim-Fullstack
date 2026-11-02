import type { Background, BackgroundKind, Theme } from "./types";

/** Tint the background with the theme's accents, keeping its light/dark character. */
function tint(base: string, accent: string, amount: number): string {
  const channels = [1, 3, 5].map((offset) => {
    const start = parseInt(base.slice(offset, offset + 2), 16);
    const end = parseInt(accent.slice(offset, offset + 2), 16);
    return Math.round(start + (end - start) * amount).toString(16).padStart(2, "0");
  });
  return `#${channels.join("")}`.toUpperCase();
}

export type BackgroundSlot = "color" | "color2";

/** Slots already visible in a saved background can intentionally use Theme color. */
export function visibleBackgroundSlots(background: Background): BackgroundSlot[] {
  return background.kind === "gradient" ? ["color", "color2"] : background.kind === "solid" ? ["color"] : [];
}

export function changeBackgroundKind(background: Background, kind: BackgroundKind, theme: Theme | undefined, chosen: ReadonlySet<BackgroundSlot>): Background {
  const base = theme?.bg ?? "#F6F5F2";
  const accents = (theme?.accent ?? []).filter((color) => color.toUpperCase() !== base.toUpperCase());
  const first = accents[0] ?? "#2563EB";
  const second = accents[1] ?? "#F97316";
  const next = { ...background, kind };
  if ((kind === "solid" || kind === "gradient") && !next.color && !chosen.has("color")) {
    next.color = tint(base, first, 0.18);
  }
  if (kind === "gradient" && !next.color2 && !chosen.has("color2")) {
    next.color2 = tint(base, second, 0.3);
  }
  return next;
}
