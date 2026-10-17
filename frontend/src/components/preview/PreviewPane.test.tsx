// A video the browser can't play gets a message and a Download button, not an empty 300x150 box.
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PreviewPane } from "./PreviewPane";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { PreviewItem } from "@/lib/types";

afterEach(() => vi.restoreAllMocks());

const video = (url: string): PreviewItem => ({
  kind: "video",
  url,
  title: "SquareToCircle",
  location: "workspace/media/videos/a/480p15/SquareToCircle.mp4",
  downloadName: "SquareToCircle.mp4",
});

function pane(preview: PreviewItem) {
  return (
    <TooltipProvider>
      <PreviewPane
        preview={preview}
        active={null}
        stepCount={0}
        lastOutcome={null}
        loop
        selectedScene="SquareToCircle"
        canRender
        canCompare={false}
        onRender={() => {}}
        onCancel={() => {}}
        onCompare={() => {}}
        onShowConsole={() => {}}
      />
    </TooltipProvider>
  );
}

describe("a video that can't play", () => {
  it("says the browser lacks H.264 when it does, and offers Download", () => {
    vi.spyOn(HTMLMediaElement.prototype, "canPlayType").mockReturnValue("");
    render(pane(video("/media/a.mp4?v=1")));
    fireEvent.error(screen.getByLabelText("Video preview: SquareToCircle"));
    expect(screen.getByText("This video can't play here")).toBeInTheDocument();
    expect(screen.getByText(/can't decode H\.264/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Video preview: SquareToCircle")).toBeNull();
    // The card's Download, next to the header's.
    expect(screen.getAllByRole("button", { name: "Download" })).toHaveLength(2);
  });

  it("says the file couldn't load when the codec is supported, and tries a new render again", () => {
    vi.spyOn(HTMLMediaElement.prototype, "canPlayType").mockReturnValue("probably");
    const { rerender } = render(pane(video("/media/a.mp4?v=1")));
    fireEvent.error(screen.getByLabelText("Video preview: SquareToCircle"));
    expect(screen.getByText(/couldn't load it/)).toBeInTheDocument();
    rerender(pane(video("/media/a.mp4?v=2")));
    expect(screen.getByLabelText("Video preview: SquareToCircle")).toHaveAttribute("src", "/media/a.mp4?v=2");
  });
});
