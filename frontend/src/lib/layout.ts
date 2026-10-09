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
/** The old fixed minimum for the top row; never go below it. */
export const TOP_MIN_FLOOR_PX = 240;
/** Below this viewport height the console starts smaller than 26%. */
export const SHORT_VIEWPORT_PX = 760;

export interface WorkPanelSizes {
  /** Default bottom (console/timeline) panel height, in px. */
  bottomDefaultPx: number;
  /** Minimum height of the editor + preview row, in px. */
  topMinPx: number;
}

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

export function workPanelSizes(viewportHeight: number): WorkPanelSizes {
  const work = Math.max(0, viewportHeight - APP_CHROME_PX);
  const bottomDefault =
    viewportHeight < SHORT_VIEWPORT_PX
      ? clamp(viewportHeight * 0.22, BOTTOM_MIN_PX, Math.max(BOTTOM_MIN_PX, work * 0.26))
      : work * 0.26;
  // Room for a ~300 px preview stage, but always leave the console its minimum.
  const topMin = clamp(work - BOTTOM_MIN_PX - 1, TOP_MIN_FLOOR_PX, PREVIEW_STAGE_MIN_PX + PREVIEW_CHROME_PX);
  return { bottomDefaultPx: Math.round(bottomDefault), topMinPx: Math.round(topMin) };
}
