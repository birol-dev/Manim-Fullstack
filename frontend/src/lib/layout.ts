/**
 * Height-aware sizes for the editor/preview vs. bottom panel split.
 *
 * At 1024x700 (and in a real browser window, where the viewport is ~100 px
 * shorter) a 26% console plus the preview's header and footer left the video
 * area at ~200 px. Short viewports now start with a smaller console, and the
 * top row keeps enough height for a ~300 px preview stage. Saved (user-dragged)
 * layouts still win; they are only clamped by these limits.
 */

/** Top bar (h-11) + status bar (h-6). */
export const APP_CHROME_PX = 44 + 24;
/** Preview header (h-10) + path footer (h-7). */
export const PREVIEW_CHROME_PX = 40 + 28;
export const PREVIEW_STAGE_MIN_PX = 300;
export const BOTTOM_MIN_PX = 120;
/** The console's collapsed height (its tab bar). */
export const BOTTOM_COLLAPSED_PX = 36;
/** The old fixed minimum for the top row; never go below it. */
export const TOP_MIN_FLOOR_PX = 240;
/** Below this viewport height the console starts smaller than 26%. */
export const SHORT_VIEWPORT_PX = 760;

export interface WorkPanelSizes {
  /** Default bottom (console/timeline) panel height, in px. */
  bottomDefaultPx: number;
  /** Minimum height of the editor + preview row, in px. */
  topMinPx: number;
  /** Minimum height of the console/timeline panel, in px (120 unless the window is tiny). */
  bottomMinPx: number;
}

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

export function workPanelSizes(viewportHeight: number): WorkPanelSizes {
  const work = Math.max(0, viewportHeight - APP_CHROME_PX);
  // Space the top row can have while the console keeps its minimum (and the 1 px handle).
  const roomForTop = Math.max(0, work - BOTTOM_MIN_PX - 1);
  // Room for a ~300 px preview stage, but never more than the room left. (The old 240 px floor
  // plus the 120 px console minimum exceeded the work area below ~430 px of viewport, so the two
  // minimums overlapped; whenever there is room for 240 px this gives at least 240 as before.)
  const topMin = Math.min(PREVIEW_STAGE_MIN_PX + PREVIEW_CHROME_PX, roomForTop);
  // On absurdly short windows the console minimum gives way too (down to its 36 px collapsed bar).
  const bottomMin = Math.min(BOTTOM_MIN_PX, Math.max(BOTTOM_COLLAPSED_PX, work - 1));
  const bottomPreferred =
    viewportHeight < SHORT_VIEWPORT_PX
      ? clamp(viewportHeight * 0.22, BOTTOM_MIN_PX, Math.max(BOTTOM_MIN_PX, work * 0.26))
      : work * 0.26;
  // The default console must fit next to the top row's minimum (it can't push the top row below it).
  const bottomDefault = Math.max(0, Math.min(bottomPreferred, work - topMin - 1));
  return { bottomDefaultPx: Math.round(Math.max(bottomDefault, Math.min(bottomMin, work))), topMinPx: Math.round(topMin), bottomMinPx: Math.round(bottomMin) };
}

/** Toasts: below the top bar (h-11) and the preview header (h-10), plus a gap. */
export const TOAST_TOP_PX = 44 + 40 + 8;

/** Below this viewport width the editor/preview split favours the preview. */
export const NARROW_VIEWPORT_PX = 1200;

export interface HorizontalDefaults {
  /** Default sidebar width, in px. */
  sidebarPx: number;
  /** Default preview share of the editor + preview row, in percent. */
  previewPercent: number;
}

/**
 * Default widths. At 1024 px the 240 px sidebar and a 42% preview left the video
 * at 325x183; narrow windows now start with the sidebar at 208 px and the row split
 * 50/50 (video ~383x215, the editor's toolbar wraps its file name onto its own row
 * instead of truncating it). Saved (user-dragged) layouts still win.
 */
export function horizontalDefaults(viewportWidth: number): HorizontalDefaults {
  return viewportWidth < NARROW_VIEWPORT_PX ? { sidebarPx: 208, previewPercent: 50 } : { sidebarPx: 240, previewPercent: 42 };
}
