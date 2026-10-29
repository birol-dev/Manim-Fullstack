import { act, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { PreviewPanel, type PreviewFeed } from "./PreviewPanel";

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
