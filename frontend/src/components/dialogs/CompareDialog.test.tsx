import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { media } from "@/test/fakeServer";
import { CompareDialog } from "./CompareDialog";

function setClip(video: HTMLVideoElement, duration: number, currentTime: number, ended = false) {
  Object.defineProperty(video, "duration", { configurable: true, value: duration });
  Object.defineProperty(video, "ended", { configurable: true, value: ended });
  Object.defineProperty(video, "currentTime", { configurable: true, writable: true, value: currentTime });
}

describe("CompareDialog", () => {
  it("keeps the time readout running on the longer clip when A is shorter", () => {
    render(<CompareDialog open onOpenChange={() => {}} videos={[media("Short"), media("Long")]} />);
    const [a, b] = Array.from(document.querySelectorAll("video"));
    setClip(a, 2, 0);
    setClip(b, 5, 0);
    act(() => {
      fireEvent.loadedMetadata(a);
      fireEvent.loadedMetadata(b);
    });
    expect(screen.getByText("0.0s / 5.0s")).toBeInTheDocument();

    // A has finished; only B keeps firing timeupdate.
    setClip(a, 2, 2, true);
    setClip(b, 5, 3.4);
    act(() => void fireEvent.timeUpdate(b));
    expect(screen.getByText("3.4s / 5.0s")).toBeInTheDocument();
    expect((screen.getByLabelText("Playback position") as HTMLInputElement).value).toBe("3.4");
  });
});
