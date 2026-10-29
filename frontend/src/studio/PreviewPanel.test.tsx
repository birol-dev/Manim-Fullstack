import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { act, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { PreviewPanel, type PreviewFeed } from "./PreviewPanel";

// CSS imports are stubbed out in tests, so read the stylesheet itself.
const previewCss = readFileSync(resolve(process.cwd(), "src/studio/preview.css"), "utf8");

it("refits all frames on resize and keeps the duration caption directly below the grid", () => {
  let resize: ResizeObserverCallback;
  const disconnect = vi.fn();
  vi.stubGlobal("ResizeObserver", class {
    constructor(callback: ResizeObserverCallback) { resize = callback; }
    observe() {}
    disconnect = disconnect;
  });
  try {
    const poster: PreviewFeed = { response: null, pending: false, error: null, retry: vi.fn() };
    const storyboard: PreviewFeed = { ...poster, response: { mode: "storyboard", url: "/sheet.png", width: 1920, height: 1080, storyboard: { frames: 9, columns: 3, frame_size: [640, 360], times: [0, 1, 2, 3, 4, 5, 6, 7, 17.03], length: 17.03 } } };
    const props = { onViewChange: vi.fn(), poster, storyboard, aspect: "16:9" as const, transparent: false, length: null };
    const view = render(<PreviewPanel {...props} view="storyboard" />);
    const grid = screen.getByRole("img", { name: "Storyboard: moments from your video" }).closest<HTMLElement>(".studio-storyboard-grid")!;
    act(() => resize([{ contentRect: { width: 1000, height: 730 } } as ResizeObserverEntry], {} as ResizeObserver));
    expect(grid.style.getPropertyValue("--storyboard-columns")).toBe("3");
    expect(parseFloat(grid.style.width)).toBeGreaterThan(900);
    expect(grid.nextElementSibling).toHaveTextContent("16:9 · 17 seconds");
    expect(grid.querySelectorAll("figure")).toHaveLength(9);
    act(() => resize([{ contentRect: { width: 342, height: 730 } } as ResizeObserverEntry], {} as ResizeObserver));
    expect(parseFloat(grid.style.width)).toBeLessThanOrEqual(310);
    expect(grid.style.getPropertyValue("--storyboard-columns")).not.toBe("3");
    view.rerender(<PreviewPanel {...props} view="poster" />);
    expect(screen.getByText("16:9 · 17 seconds")).toBeInTheDocument();
    expect(disconnect).toHaveBeenCalledOnce();
  } finally {
    vi.unstubAllGlobals();
  }
});

it("fills the preview area with artwork sized from its stage at the chosen ratio", () => {
  const feed: PreviewFeed = { response: { mode: "poster", url: "/still.png", width: 480, height: 270 }, pending: false, error: null, retry: vi.fn() };
  const view = render(<PreviewPanel view="poster" onViewChange={vi.fn()} poster={feed} storyboard={feed} aspect="16:9" transparent={false} length={120} />);
  const frame = screen.getByRole("img", { name: "Preview of your video" }).closest<HTMLElement>(".studio-preview-frame")!;
  const stage = frame.parentElement!;
  // The stage takes the height next to the form column; the frame derives both dimensions
  // from it, so the still never falls back to a fixed band.
  expect(stage).toHaveClass("studio-preview-stage", "flex-1", "min-h-0");
  expect(frame.style.getPropertyValue("--studio-preview-ratio")).toBe(String(16 / 9));
  const rule = /\.studio-preview-frame\s*\{([^}]*)\}/.exec(previewCss)?.[1] ?? "";
  expect(rule).toContain("aspect-ratio: var(--studio-preview-ratio)");
  expect(rule).toMatch(/width:\s*min\(100cqw, calc\(100cqh \* var\(--studio-preview-ratio\)\)\)/);
  expect(rule).toMatch(/max-width:\s*100%/);
  expect(rule).toMatch(/max-height:\s*100%/);
  view.rerender(<PreviewPanel view="poster" onViewChange={vi.fn()} poster={feed} storyboard={feed} aspect="9:16" transparent={false} length={120} />);
  expect(frame.style.getPropertyValue("--studio-preview-ratio")).toBe(String(9 / 16));
});
