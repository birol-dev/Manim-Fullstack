import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { cancelMotion, getMotion, startMotion } from "./api";
import { PreviewPanel, type PreviewFeed } from "./PreviewPanel";
import type { MotionPreview, PreviewRequest } from "./types";

vi.mock("./api", async (original) => ({ ...await original<typeof import("./api")>(), startMotion: vi.fn(), getMotion: vi.fn(), cancelMotion: vi.fn() }));

const request: PreviewRequest = { template: "countdown", params: { seconds: 300 }, settings: { aspect: "16:9" }, mode: "poster" };
const feed: PreviewFeed = { response: { mode: "poster", url: "/still.png", width: 480, height: 270 }, pending: false, error: null, retry: vi.fn() };
const props = { view: "poster" as const, onViewChange: vi.fn(), poster: feed, storyboard: feed, aspect: "16:9" as const, transparent: false, length: 305, motionRequest: request, motionSession: "test-editor" };
const done: MotionPreview = { id: "m1", status: "done", url: "/motion.mp4", duration: 20, truncated: true };

beforeEach(() => {
  vi.mocked(startMotion).mockReset().mockResolvedValue(done);
  vi.mocked(getMotion).mockReset().mockResolvedValue(done);
  vi.mocked(cancelMotion).mockReset().mockResolvedValue({ id: "m1", status: "cancelled" });
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
});

it("renders only on click, plays silently inline with controls, and returns to the still after an edit", async () => {
  const view = render(<PreviewPanel {...props} />);
  expect(startMotion).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Play animation" })).toHaveClass("studio-motion-controls");
  expect(screen.getByRole("button", { name: "Play animation" })).toHaveTextContent("Play");
  expect(screen.getByText("16:9 · 5 min 5 s")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Play animation" }));
  const video = await screen.findByLabelText("Your animation") as HTMLVideoElement;
  expect(startMotion).toHaveBeenCalledOnce();
  expect(video).toHaveAttribute("loop");
  expect(video.muted).toBe(true);
  expect(video).toHaveAttribute("playsinline");
  expect(video).toHaveAttribute("poster", "/still.png");
  expect(screen.getByText("First 20 seconds")).toBeInTheDocument();
  Object.defineProperty(video, "duration", { configurable: true, value: 20 });
  Object.defineProperty(video, "paused", { configurable: true, value: false });
  fireEvent.loadedMetadata(video);
  fireEvent.change(screen.getByRole("slider", { name: "Preview position" }), { target: { value: "8" } });
  expect(video.currentTime).toBe(8);
  expect(screen.getByText("0:08 / 0:20")).toBeInTheDocument();
  fireEvent.keyDown(screen.getByLabelText("Animation preview"), { code: "Space" });
  expect(video.pause).toHaveBeenCalledOnce();
  fireEvent.pause(video);
  fireEvent.click(screen.getByRole("button", { name: "Play animation" }));
  expect(video.play).toHaveBeenCalled();
  view.rerender(<PreviewPanel {...props} motionRequest={{ ...request, params: { seconds: 60 } }} />);
  expect(screen.queryByLabelText("Your animation")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Play animation" })).toBeInTheDocument();
  expect(startMotion).toHaveBeenCalledOnce();
  view.rerender(<PreviewPanel {...props} />);
  expect(screen.queryByLabelText("Your animation")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Play animation" })).toBeInTheDocument();
});

it("keeps the Play pill below the artwork, in the caption row", () => {
  render(<PreviewPanel {...props} />);
  const frame = screen.getByRole("img", { name: "Preview of your video" }).closest(".studio-preview-frame")!;
  const play = screen.getByRole("button", { name: "Play animation" });
  expect(frame).not.toContainElement(play);
  expect(play.closest(".studio-preview-caption-row")).not.toBeNull();
  expect(play.closest(".studio-preview-caption-row")).toHaveTextContent("16:9 · 5 min 5 s");
  play.focus();
  expect(play).toHaveFocus();
});

it("hides the playback bar after a moment and brings it back on movement, focus, or pause", async () => {
  render(<PreviewPanel {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "Play animation" }));
  const video = await screen.findByLabelText("Your animation");
  fireEvent.pause(video);
  const container = screen.getByLabelText("Animation preview");
  const controls = screen.getByRole("slider", { name: "Preview position" }).closest<HTMLElement>(".studio-motion-controls")!;
  expect(controls).toHaveAttribute("data-controls", "shown");
  vi.useFakeTimers();
  try {
    fireEvent.play(video);
    act(() => { vi.advanceTimersByTime(2_000); });
    expect(controls).toHaveAttribute("data-controls", "hidden");
    fireEvent.pointerMove(container);
    expect(controls).toHaveAttribute("data-controls", "shown");
    act(() => { vi.advanceTimersByTime(2_000); });
    expect(controls).toHaveAttribute("data-controls", "hidden");
    fireEvent.focus(container);
    expect(controls).toHaveAttribute("data-controls", "shown");
    fireEvent.blur(container);
    act(() => { vi.advanceTimersByTime(2_000); });
    expect(controls).toHaveAttribute("data-controls", "hidden");
    fireEvent.pause(video);
    expect(controls).toHaveAttribute("data-controls", "shown");
  } finally {
    vi.useRealTimers();
  }
});

it("polls one preview, prevents repeat clicks, and cancels on edit", async () => {
  vi.mocked(startMotion).mockResolvedValue({ id: "m1", status: "rendering" });
  vi.mocked(getMotion).mockResolvedValue({ id: "m1", status: "rendering" });
  const view = render(<PreviewPanel {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "Play animation" }));
  const making = (await screen.findByText("Making a quick preview…")).closest<HTMLElement>(".studio-motion-controls");
  expect(making).not.toBeNull();
  expect(screen.getByRole("img", { name: "Preview of your video" }).closest(".studio-preview-frame")).not.toContainElement(making);
  expect(making!.closest(".studio-preview-caption-row")).not.toBeNull();
  expect(screen.getByRole("img", { name: "Preview of your video" })).toHaveAttribute("src", "/still.png");
  expect(screen.getByRole("progressbar", { name: "Making a quick preview" })).not.toHaveAttribute("aria-valuenow");
  expect(screen.getByRole("button", { name: "Cancel preview" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Play animation" })).not.toBeInTheDocument();
  await waitFor(() => expect(getMotion).toHaveBeenCalledWith("m1"));
  view.rerender(<PreviewPanel {...props} motionRequest={{ ...request, params: { seconds: 60 } }} />);
  expect(cancelMotion).toHaveBeenCalledWith("m1");
  expect(startMotion).toHaveBeenCalledOnce();
});

it("cancels from the making pill and ignores a later completed response", async () => {
  vi.mocked(startMotion).mockResolvedValue({ id: "m1", status: "rendering" });
  render(<PreviewPanel {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "Play animation" }));
  await screen.findByRole("button", { name: "Cancel preview" });
  await act(async () => {});
  fireEvent.click(screen.getByRole("button", { name: "Cancel preview" }));
  expect(cancelMotion).toHaveBeenCalledWith("m1");
  expect(screen.getByRole("button", { name: "Play animation" })).toBeInTheDocument();
  expect(screen.queryByLabelText("Your animation")).not.toBeInTheDocument();
  expect(screen.getByRole("img", { name: "Preview of your video" })).toBeInTheDocument();
});

it("cancels a making request even before its POST returns", async () => {
  let finish!: (value: MotionPreview) => void;
  vi.mocked(startMotion).mockReturnValue(new Promise((resolve) => { finish = resolve; }));
  render(<PreviewPanel {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "Play animation" }));
  fireEvent.click(screen.getByRole("button", { name: "Cancel preview" }));
  await act(async () => finish({ id: "m1", status: "rendering" }));
  expect(cancelMotion).toHaveBeenCalledWith("m1");
  expect(screen.getByRole("button", { name: "Play animation" })).toBeInTheDocument();
  expect(screen.queryByLabelText("Your animation")).not.toBeInTheDocument();
});

it("cancels a late POST result instead of showing outdated motion", async () => {
  let finish!: (value: MotionPreview) => void;
  vi.mocked(startMotion).mockReturnValue(new Promise((resolve) => { finish = resolve; }));
  const view = render(<PreviewPanel {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "Play animation" }));
  view.rerender(<PreviewPanel {...props} motionRequest={{ ...request, params: { seconds: 60 } }} />);
  await act(async () => finish({ id: "m1", status: "rendering" }));
  expect(cancelMotion).toHaveBeenCalledWith("m1");
  expect(screen.queryByLabelText("Your animation")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Play animation" })).toBeInTheDocument();
});

it("offers a friendly retry after a render error", async () => {
  vi.mocked(startMotion).mockRejectedValueOnce(new Error("private backend details"));
  render(<PreviewPanel {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "Play animation" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't play this preview");
  expect(screen.queryByText("private backend details")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByLabelText("Your animation")).toBeInTheDocument();
  expect(startMotion).toHaveBeenCalledTimes(2);
});

it("leaves storyboard mode free of playback controls", () => {
  render(<PreviewPanel {...props} view="storyboard" />);
  expect(screen.queryByRole("button", { name: "Play animation" })).not.toBeInTheDocument();
  expect(startMotion).not.toHaveBeenCalled();
});

it("requires an explicit gesture to unmute and offers playback volume", async () => {
  render(<PreviewPanel {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "Play animation" }));
  const video = await screen.findByLabelText("Your animation") as HTMLVideoElement;
  expect(video.muted).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Unmute preview" }));
  expect(video.muted).toBe(false);
  fireEvent.change(screen.getByRole("slider", { name: "Preview volume" }), { target: { value: ".3" } });
  expect(video.volume).toBe(.3);
  fireEvent.click(screen.getByRole("button", { name: "Mute preview" }));
  expect(video.muted).toBe(true);
});
