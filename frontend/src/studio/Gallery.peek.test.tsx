import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { Gallery } from "./Gallery";
import { FAVOURITE_DESIGNS_KEY } from "./preferences";
import { CATALOG } from "./test/fixtures";
import type { Route } from "./router";
import type { SetupStatus } from "./setup";
import type { Catalog, ExportJob, ProjectSummary } from "./types";

// CSS imports are stubbed out in tests, so read the stylesheet itself.
const homeCss = readFileSync(resolve(process.cwd(), "src/studio/home.css"), "utf8");

let mockSetupStatus: SetupStatus | null = null;

vi.mock("./hooks", () => ({
  useNearViewport: () => true,
  usePoster: () => ({ response: { url: "/still.png", width: 640, height: 360 }, error: null }),
}));

vi.mock("./setup", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./setup")>();
  return {
    ...actual,
    useSetupStatus: () => ({ status: mockSetupStatus, error: null, refresh: () => {} }),
  };
});

let fine = true;
let reduced = false;
let listeners: Set<() => void>;
let play: ReturnType<typeof vi.spyOn>;
let pause: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  vi.useFakeTimers();
  localStorage.removeItem(FAVOURITE_DESIGNS_KEY);
  fine = true;
  reduced = false;
  mockSetupStatus = null;
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

interface OpenOptions {
  peeks?: boolean;
  home?: boolean;
  route?: Route;
  projects?: ProjectSummary[];
  exports?: ExportJob[];
  catalog?: Catalog;
}

function open({ peeks = true, home = false, route, projects, exports, catalog: customCatalog }: OpenOptions = {}) {
  const catalog = customCatalog ?? structuredClone(CATALOG);
  if (!customCatalog) {
    for (const section of catalog.sections) {
      for (const card of section.cards) card.peek_url = peeks ? `/peeks/${card.id}.mp4` : null;
    }
  }
  return render(<Gallery catalog={catalog} route={route ?? (home ? { kind: "gallery" } : { kind: "templates" })}
    library={{ projects: projects ?? [{ id: "saved", template: "countdown", title: "Saved timer", updated: 1, poster_url: "/saved.png" }] } as never}
    exports={{ jobs: exports ?? [], error: null, cancel: vi.fn(), retry: vi.fn() } as never} />);
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

const doneExport: ExportJob = { id: "e1", template: "countdown", format: "mp4", quality: "720p", status: "done", progress: 100, created: 1 };

describe("home setup and chapters", () => {
  it("shows which setup steps are done and highlights the next one", () => {
    mockSetupStatus = { platform: "windows", mode: "desktop", components: [], ai_apps: [], data_folder: "C:\\Videos" };
    open({
      home: true,
      projects: [{ id: "p1", title: "My timer", template: "countdown", updated: 1 }],
      exports: [doneExport],
    });
    const tray = screen.getByRole("region", { name: "Finish your setup — 2/4" });
    expect(within(tray).getByRole("link", { name: /Make your first video/ })).toHaveAttribute("data-done", "true");
    expect(within(tray).getByRole("link", { name: /Export a video/ })).toHaveAttribute("data-done", "true");
    expect(within(tray).getByRole("link", { name: /Connect your AI/ })).toHaveAttribute("data-next", "true");
    expect(within(tray).getByRole("link", { name: /Tell us your name/ })).not.toHaveAttribute("data-done");
    expect(within(tray).getByText("So we know what to call you.")).toBeInTheDocument();
    expect(within(tray).queryByText("It goes on what you make.")).not.toBeInTheDocument();
  });

  it("hides the setup tray once every step is done", () => {
    mockSetupStatus = {
      platform: "windows",
      mode: "desktop",
      components: [],
      ai_apps: [{ id: "claude-desktop", label: "Claude Desktop", detected: true, connected: true, needs_repair: false, restart_hint: null, error: null }],
      data_folder: "C:\\Videos",
    };
    localStorage.setItem("studio:brand-name", "Ada");
    open({
      home: true,
      projects: [{ id: "p1", title: "My timer", template: "countdown", updated: 1 }],
      exports: [doneExport],
    });
    expect(screen.queryByRole("region", { name: /Finish your setup/ })).not.toBeInTheDocument();
  });

  it("lays chapters out as a zig-zag and links to the whole chapter", () => {
    open({ home: true });
    const chapter = screen.getByRole("region", { name: "Timers & countdowns" });
    const cards = within(chapter).getAllByRole("link").filter((link) => link.getAttribute("href")?.startsWith("#/new/"));
    expect(cards).toHaveLength(2);
    expect(cards[0].closest("li")).toHaveClass("studio-home-zig-0");
    expect(cards[1].closest("li")).toHaveClass("studio-home-zig-1");
    expect(within(chapter).getByRole("link", { name: "See all 2" })).toHaveAttribute("href", "#/templates/timers");
  });

  it("shows a clear empty state when no template matches the search", () => {
    open({ route: { kind: "templates", query: "zebra" } });
    expect(screen.getByRole("heading", { name: 'Nothing matches "zebra"' })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Clear search" })).toHaveAttribute("href", "#/templates");
    expect(screen.getByRole("link", { name: "See all templates" })).toHaveAttribute("href", "#/templates");
  });

  it("hearts a card and shows it in Your favourites on Home", () => {
    open({ home: true });
    expect(screen.queryByRole("region", { name: "Your favourites" })).not.toBeInTheDocument();
    const heart = screen.getByRole("button", { name: "Add Classroom timer to favourites" });
    expect(heart).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(heart);
    expect(heart).toHaveAttribute("aria-pressed", "true");
    expect(JSON.parse(localStorage.getItem(FAVOURITE_DESIGNS_KEY)!)).toEqual(["countdown/classroom-timer"]);
    const row = screen.getByRole("region", { name: "Your favourites" });
    expect(within(row).getByRole("link", { name: /Classroom timer/ })).toBeInTheDocument();
  });

  it("shows Recently used only once two designs were worked on", () => {
    open({ home: true });
    expect(screen.queryByRole("region", { name: "Recently used" })).not.toBeInTheDocument();

    cleanup();
    open({
      home: true,
      projects: [
        { id: "p1", title: "My timer", template: "countdown", updated: 2 },
        { id: "p2", title: "My chart", template: "chart", updated: 1 },
      ],
    });
    const row = screen.getByRole("region", { name: "Recently used" });
    expect(within(row).getByRole("link", { name: /Classroom timer/ })).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: /Sales chart/ })).toBeInTheDocument();
    expect(within(row).getAllByRole("link")).toHaveLength(2);
  });

  it("keeps the heart quiet until hover or focus, visible when set, and reachable on touch", () => {
    const heart = /\.studio-card-favourite \{([\s\S]*?)\n\}/.exec(homeCss)?.[1] ?? "";
    expect(heart).toContain("opacity: 0");
    expect(heart).not.toContain("border:");
    expect(heart).not.toContain("box-shadow:");
    expect(homeCss).toMatch(/\.studio-card-favourite\[aria-pressed="true"\] \{[^}]*opacity: 1/);
    expect(homeCss).toMatch(/:is\(:hover, :focus-within\) \.studio-card-favourite \{[^}]*opacity: 1/);
    expect(homeCss).toMatch(/:is\(\.studio-template-grid, \.studio-home-zigzag\) > li \{ position: relative/);
    expect(homeCss).toMatch(/@media \(hover: none\), \(any-pointer: coarse\) \{\s*:root\[data-surface="studio"\] \.studio-card-favourite \{ opacity: 1; \}/);
  });

  it("lets the hero reach the window edge and settles it inside the column on wide canvases", () => {
    const hero = /\.studio-home-hero \{([^}]*)\}/.exec(homeCss)?.[1] ?? "";
    expect(hero).toContain("margin-right: calc(-1 * var(--home-bleed))");
    expect(hero).toContain("overflow: hidden");

    // Past the shell's 1440px column the bleed would end in mid-air, so the hero stops
    // bleeding and every frame moves fully inside the column.
    const wide = /@media \(min-width: 1500px\) \{([\s\S]*?)\n\}/.exec(homeCss)?.[1] ?? "";
    expect(wide).toContain("margin-right: 0");
    expect(wide).toMatch(/\.studio-home-frame-0 \{ left: 8px; \}/);
    expect(wide).toMatch(/\.studio-home-frame-1 \{ right: 12px; \}/);
    expect(wide).not.toMatch(/right: -/);
  });
});
