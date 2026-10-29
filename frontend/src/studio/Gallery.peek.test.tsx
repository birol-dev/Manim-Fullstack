import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { Gallery } from "./Gallery";
import { CATALOG } from "./test/fixtures";

vi.mock("./hooks", () => ({
  useNearViewport: () => true,
  usePoster: () => ({ response: { url: "/still.png", width: 640, height: 360 }, error: null }),
}));

let fine = true;
let reduced = false;
let listeners: Set<() => void>;
let play: ReturnType<typeof vi.spyOn>;
let pause: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  vi.useFakeTimers();
  fine = true;
  reduced = false;
  listeners = new Set();
  vi.spyOn(window, "matchMedia").mockImplementation((query) => ({
    get matches() { return query.includes("reduced-motion") ? reduced : fine; },
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
    addEventListener: (_type: string, listener: EventListenerOrEventListenerObject) => { listeners.add(listener as () => void); },
    removeEventListener: (_type: string, listener: EventListenerOrEventListenerObject) => { listeners.delete(listener as () => void); },
  } as MediaQueryList));
  play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
  pause = vi.spyOn(HTMLMediaElement.prototype, "pause");
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function open({ peeks = true, home = false } = {}) {
  const catalog = structuredClone(CATALOG);
  for (const section of catalog.sections) {
    for (const card of section.cards) card.peek_url = peeks ? `/peeks/${card.id}.mp4` : null;
  }
  return render(<Gallery catalog={catalog} route={home ? { kind: "gallery" } : { kind: "templates" }}
    library={{ projects: [{ id: "saved", template: "countdown", title: "Saved timer", updated: 1, poster_url: "/saved.png" }] } as never}
    exports={{} as never} />);
}

function first() {
  const card = screen.getByRole("link", { name: /Classroom timer/ });
  return { card, video: card.querySelector("video")! };
}

async function dwell(card: HTMLElement) {
  fireEvent.pointerEnter(card, { pointerType: "mouse" });
  await act(() => vi.advanceTimersByTimeAsync(300));
}

async function ready(video: HTMLVideoElement) {
  await act(async () => { fireEvent.canPlay(video); });
}

it("has no src before dwell, preserves the card name, and overlays just the artwork", async () => {
  open();
  const { card, video } = first();
  expect(video).not.toHaveAttribute("src");
  expect(video).toHaveAttribute("preload", "none");
  expect(video).toHaveAttribute("aria-hidden", "true");
  expect(video).toHaveAttribute("tabindex", "-1");
  expect(video).toHaveAttribute("playsinline");
  expect(video.parentElement).toHaveClass("studio-poster-artwork");
  expect(video.parentElement?.querySelector(".studio-poster-image")).toBeTruthy();
  expect(card.querySelector(".studio-poster-ambient")).toBeTruthy();
  expect(card).toHaveAttribute("href", "#/new/countdown/classroom-timer");
  fireEvent.pointerEnter(card, { pointerType: "mouse" });
  fireEvent.canPlay(video); // an early media event must not bypass dwell
  await act(() => vi.advanceTimersByTimeAsync(299));
  expect(video).not.toHaveAttribute("src");
  expect(play).not.toHaveBeenCalled();
  await act(() => vi.advanceTimersByTimeAsync(1));
  expect(video).toHaveAttribute("src", "/peeks/classroom-timer.mp4");
  expect(video).toHaveAttribute("data-visible", "false");
  await ready(video);
  expect(play).toHaveBeenCalledTimes(1);
  expect(video.muted).toBe(true);
  expect(video).toHaveAttribute("data-visible", "true");
});

it("plays once, holds the last frame, and rewinds after fading out on leave", async () => {
  open();
  const { card, video } = first();
  await dwell(card);
  await ready(video);
  video.currentTime = 4;
  fireEvent.ended(video);
  await ready(video);
  expect(play).toHaveBeenCalledTimes(1);
  expect(video.loop).toBe(false);
  expect(video.currentTime).toBe(4);
  expect(video).toHaveAttribute("data-visible", "true");
  fireEvent.pointerLeave(card);
  expect(pause).toHaveBeenCalled();
  expect(video).toHaveAttribute("data-visible", "false");
  expect(video.currentTime).toBe(4);
  await act(() => vi.advanceTimersByTimeAsync(150));
  expect(video.currentTime).toBe(0);
  await dwell(card);
  await ready(video);
  expect(play).toHaveBeenCalledTimes(2);
  expect(video.currentTime).toBe(0);
});

it("cancels a brief hover and pending media playback on leave", async () => {
  open();
  const { card, video } = first();
  fireEvent.pointerEnter(card);
  await act(() => vi.advanceTimersByTimeAsync(200));
  fireEvent.pointerLeave(card);
  await act(() => vi.advanceTimersByTimeAsync(500));
  expect(video).not.toHaveAttribute("src");
  await dwell(card);
  fireEvent.pointerLeave(card);
  await ready(video);
  expect(play).toHaveBeenCalledTimes(1);
  expect(video).toHaveAttribute("data-visible", "false");
});

it("supports focus-visible dwell and resets on blur, ignoring pointer-style focus", async () => {
  open();
  const { card, video } = first();
  const matches = vi.spyOn(card, "matches").mockReturnValue(false);
  fireEvent.focus(card);
  await act(() => vi.advanceTimersByTimeAsync(400));
  expect(video).not.toHaveAttribute("src");
  matches.mockReturnValue(true);
  fireEvent.focus(card);
  await act(() => vi.advanceTimersByTimeAsync(300));
  await ready(video);
  expect(play).toHaveBeenCalledTimes(1);
  video.currentTime = 2;
  fireEvent.blur(card);
  await act(() => vi.advanceTimersByTimeAsync(150));
  expect(video.currentTime).toBe(0);
  expect(video).toHaveAttribute("data-visible", "false");
});

it.each(["reduced motion", "coarse pointer", "touch event"])("disables peeks for %s", async (preference) => {
  if (preference === "reduced motion") reduced = true;
  if (preference === "coarse pointer") fine = false;
  open();
  const { card, video } = first();
  fireEvent.pointerEnter(card, { pointerType: preference === "touch event" ? "touch" : "mouse" });
  if (preference !== "touch event") fireEvent.focus(card);
  await act(() => vi.advanceTimersByTimeAsync(1000));
  await ready(video);
  expect(video).not.toHaveAttribute("src");
  expect(play).not.toHaveBeenCalled();
});

it("stops playback when media preferences change", async () => {
  open();
  const { card, video } = first();
  await dwell(card);
  await ready(video);
  reduced = true;
  act(() => { listeners.forEach((listener) => listener()); });
  expect(video).not.toHaveAttribute("src");
  expect(video).toHaveAttribute("data-visible", "false");
  expect(pause).toHaveBeenCalled();
});

it("allows only one peek app-wide, including pending dwell across galleries", async () => {
  open();
  const { card, video } = first();
  await dwell(card);
  await ready(video);
  open(); // another Gallery instance must share ownership
  const next = screen.getAllByRole("link", { name: /Classroom timer/ })[1];
  await dwell(next);
  expect(video).toHaveAttribute("data-visible", "false");
  await ready(next.querySelector("video")!);
  expect(play).toHaveBeenCalledTimes(2);
  fireEvent.pointerLeave(next);
  fireEvent.pointerEnter(card);
  await act(() => vi.advanceTimersByTimeAsync(200));
  fireEvent.pointerEnter(next);
  await act(() => vi.advanceTimersByTimeAsync(100));
  await ready(video);
  expect(play).toHaveBeenCalledTimes(2);
});

it("leaves cards without peeks and saved project cards unchanged", async () => {
  open({ peeks: false, home: true });
  const card = screen.getByRole("link", { name: /Classroom timer/ });
  const project = screen.getByRole("link", { name: /Saved timer/ });
  expect(card.querySelector("video")).toBeNull();
  expect(project.querySelector("video")).toBeNull();
  await dwell(card);
  await dwell(project);
  expect(play).not.toHaveBeenCalled();
});

it("cancels dwell and playback on unmount", async () => {
  const view = open();
  const { card, video } = first();
  await dwell(card);
  await ready(video);
  view.unmount();
  expect(pause).toHaveBeenCalled();
  expect(video).not.toHaveAttribute("src");
  await act(() => vi.advanceTimersByTimeAsync(1000));
  expect(play).toHaveBeenCalledTimes(1);
});
