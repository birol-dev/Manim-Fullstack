import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";

import { resetCatalogCache } from "./api";
import { APPEARANCE_KEY, SIDEBAR_KEY } from "./appearance";
import { posterQueue, SEEN_EXPORTS_KEY } from "./hooks";
import { parseRoute, routeHash } from "./router";
import StudioApp from "./StudioApp";
import { installFakeStudio, type FakeStudio } from "./test/fakeStudio";

vi.mock("@/App", () => ({ default: () => <div>Author workspace</div> }));

let studio: FakeStudio;

beforeEach(() => {
  resetCatalogCache();
  posterQueue.clear();
  window.history.replaceState(null, "", "/#/");
  studio = installFakeStudio();
});

function open(hash: string) {
  window.history.replaceState(null, "", `/${hash}`);
  return render(<StudioApp />);
}

describe("routes", () => {
  it("parses and builds hash routes", () => {
    expect(parseRoute("")).toEqual({ kind: "gallery" });
    expect(parseRoute("#/")).toEqual({ kind: "gallery" });
    expect(parseRoute("#/author")).toEqual({ kind: "author" });
    expect(parseRoute("#/new/countdown/break-timer")).toEqual({ kind: "new", template: "countdown", preset: "break-timer" });
    expect(parseRoute("#/project/abc%20d")).toEqual({ kind: "project", id: "abc d" });
    expect(parseRoute("#/nonsense")).toEqual({ kind: "gallery" });
    expect(routeHash({ kind: "project", id: "a/b" })).toBe("#/project/a%2Fb");
    expect(parseRoute("#/templates/timers?q=quiet+reading")).toEqual({ kind: "templates", category: "timers", query: "quiet reading" });
    expect(parseRoute("#/templates")).toEqual({ kind: "templates" });
    expect(parseRoute("#/videos")).toEqual({ kind: "videos" });
    expect(parseRoute("#/exports")).toEqual({ kind: "exports" });
    expect(routeHash({ kind: "templates", category: "a/b", query: "sale & party" })).toBe("#/templates/a%2Fb?q=sale+%26+party");
    expect(parseRoute("#/templates/%E0%A4%A")).toEqual({ kind: "templates", category: "%E0%A4%A" });
  });
});

describe("gallery", () => {
  it("uses library routes, restores query and category on history navigation, and keeps the editor full-screen", async () => {
    const user = userEvent.setup();
    open("#/");
    const search = await screen.findByRole("searchbox", { name: "Search designs" });
    expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute("aria-current", "page");
    await user.type(search, "revenue");
    expect(window.location.hash).toBe("#/templates?q=revenue");
    expect(search).toHaveFocus();
    await user.click(screen.getByRole("link", { name: "Timers & countdowns" }));
    await screen.findByRole("heading", { name: "Timers & countdowns" });
    expect(screen.getByRole("navigation", { name: "Breadcrumb" })).toHaveTextContent("Templates");
    act(() => window.history.back());
    await waitFor(() => expect(search).toHaveValue("revenue"));
    expect(screen.getByRole("link", { name: /Sales chart/ })).toBeInTheDocument();
    act(() => window.history.forward());
    await waitFor(() => expect(search).toHaveValue(""));
    await user.click(screen.getByRole("link", { name: /Classroom timer/ }));
    await screen.findByRole("textbox", { name: "Title" });
    expect(screen.queryByRole("complementary", { name: "Main navigation" })).not.toBeInTheDocument();
  });

  it("remembers the icon rail and expands it for search shortcuts without hijacking slash in a field", async () => {
    const user = userEvent.setup();
    const first = open("#/");
    await screen.findByRole("heading", { name: "What are you making?" });
    await user.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    expect(localStorage.getItem(SIDEBAR_KEY)).toBe("true");
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
    first.unmount();
    open("#/");
    expect(await screen.findByRole("button", { name: "Expand sidebar" })).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    const search = await screen.findByRole("searchbox", { name: "Search designs" });
    await waitFor(() => expect(search).toHaveFocus());
    expect(localStorage.getItem(SIDEBAR_KEY)).toBe("false");
    await user.type(search, "/");
    expect(search).toHaveValue("/");
    act(() => search.blur());
    fireEvent.keyDown(window, { key: "/" });
    await waitFor(() => expect(search).toHaveFocus());
    act(() => search.blur());
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    await waitFor(() => expect(search).toHaveFocus());
  });

  it("persists all appearance choices, scopes them to Studio, and themes dialog and toast portals", async () => {
    const user = userEvent.setup();
    localStorage.setItem(APPEARANCE_KEY, "dark");
    const first = open("#/");
    const appearance = await screen.findByRole("radiogroup", { name: "Appearance" });
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(within(appearance).getByRole("radio", { name: "Dark" })).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Connect to AI" }));
    expect((await screen.findByRole("dialog")).closest("html")).toHaveAttribute("data-theme", "dark");
    act(() => { toast("Theme preview", { id: "theme-preview" }); });
    await waitFor(() => expect(document.querySelector("[data-sonner-toaster]")).toHaveAttribute("data-sonner-theme", "dark"));
    act(() => { toast.dismiss("theme-preview"); });
    await user.keyboard("{Escape}");
    await user.click(within(appearance).getByRole("radio", { name: "Light" }));
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
    expect(localStorage.getItem(APPEARANCE_KEY)).toBe("light");
    first.unmount();
    open("#/");
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
    const group = await screen.findByRole("radiogroup", { name: "Appearance" });
    await user.click(within(group).getByRole("radio", { name: "System" }));
    expect(document.documentElement).not.toHaveAttribute("data-theme");
    expect(localStorage.getItem(APPEARANCE_KEY)).toBe("system");
    await user.click(within(group).getByRole("radio", { name: "Dark" }));
    await user.click(screen.getByRole("link", { name: "Author mode" }));
    await screen.findByText("Author workspace");
    expect(document.documentElement).not.toHaveAttribute("data-theme");
  });

  it("works when local preferences cannot be read or saved", async () => {
    const user = userEvent.setup();
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("Storage unavailable"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("Storage unavailable"); });
    open("#/");
    const group = await screen.findByRole("radiogroup", { name: "Appearance" });
    expect(document.documentElement).not.toHaveAttribute("data-theme");
    await user.click(within(group).getByRole("radio", { name: "Dark" }));
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    await user.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    expect(screen.getByRole("button", { name: "Expand sidebar" })).toBeInTheDocument();
  });

  it("uses a modal navigation drawer below 900px, focuses search by shortcut and closes on navigation", async () => {
    const user = userEvent.setup();
    const matchMedia = window.matchMedia.bind(window);
    vi.spyOn(window, "matchMedia").mockImplementation((query) => ({ ...matchMedia(query), matches: query === "(max-width: 899px)" }));
    open("#/");
    const toggle = await screen.findByRole("button", { name: "Open navigation" });
    await user.click(toggle);
    const drawer = await screen.findByRole("dialog", { name: "Navigation" });
    expect(within(drawer).getByRole("link", { name: "Home" })).toHaveAttribute("aria-current", "page");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(toggle).toHaveFocus();
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    expect(await screen.findByRole("searchbox", { name: "Search designs" })).toHaveFocus();
    await user.click(screen.getByRole("link", { name: "Your videos" }));
    expect(await screen.findByRole("heading", { name: "No videos yet" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows a first-run welcome, the latest four videos, then the full sorted video library", async () => {
    const user = userEvent.setup();
    const view = open("#/");
    const steps = await screen.findByRole("list", { name: "How making a video works" });
    expect(within(steps).getAllByRole("listitem")).toHaveLength(3);
    expect(within(steps).getByText("Pick a template")).toBeInTheDocument();
    expect(within(steps).getByText("Change the words, colours and format")).toBeInTheDocument();
    expect(within(steps).getByText("Export a video")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Continue editing" })).not.toBeInTheDocument();
    view.unmount();
    for (let i = 1; i <= 5; i++) studio.projects.push({ id: `p${i}`, title: `Video ${i}`, template: "countdown", params: {}, settings: {}, created: i, updated: i });
    open("#/");
    expect(await screen.findByRole("heading", { name: "Continue editing" })).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "How making a video works" })).not.toBeInTheDocument();
    const recent = screen.getByRole("region", { name: "Continue editing" });
    await within(recent).findByRole("link", { name: /Video 5/ });
    expect(within(recent).getAllByRole("link").filter((link) => link.getAttribute("href")?.startsWith("#/project/"))).toHaveLength(4);
    expect(within(recent).queryByRole("link", { name: /Video 1/ })).not.toBeInTheDocument();
    await user.click(within(recent).getByRole("link", { name: "See all" }));
    await screen.findByRole("heading", { name: "Your videos" });
    const libraryLinks = () => within(screen.getByRole("main")).getAllByRole("link").filter((link) => link.getAttribute("href")?.startsWith("#/project/"));
    expect(libraryLinks().map((link) => link.getAttribute("href"))).toEqual(["#/project/p5", "#/project/p4", "#/project/p3", "#/project/p2", "#/project/p1"]);
    await user.click(screen.getByRole("combobox", { name: "Sort videos" }));
    await user.click(screen.getByRole("option", { name: "Name" }));
    expect(libraryLinks()[0]).toHaveAttribute("href", "#/project/p1");
  });

  it("renames inline, cancels with Escape, duplicates saved content, and updates sidebar counts", async () => {
    const user = userEvent.setup();
    studio.projects.push({ id: "p9", title: "My timer", template: "countdown", params: { title: "Keep this", seconds: 75 }, settings: { theme: "midnight", aspect: "9:16" }, created: 1, updated: 1 });
    open("#/videos");
    const options = await screen.findByRole("button", { name: "Options for My timer" });
    act(() => options.focus());
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("menuitem", { name: "Rename" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(options).toHaveFocus();
    await user.click(options);
    await user.click(screen.getByRole("menuitem", { name: "Rename" }));
    const name = screen.getByRole("textbox", { name: "Video name" });
    expect(name).toHaveFocus();
    await user.clear(name);
    await user.type(name, "Discard{Escape}");
    expect(studio.projects[0].title).toBe("My timer");
    await user.click(screen.getByRole("button", { name: "Options for My timer" }));
    await user.click(screen.getByRole("menuitem", { name: "Rename" }));
    await user.clear(screen.getByRole("textbox", { name: "Video name" }));
    expect(screen.getByRole("button", { name: "Save name" })).toBeDisabled();
    await user.type(screen.getByRole("textbox", { name: "Video name" }), "My renamed timer{Enter}");
    await screen.findByRole("link", { name: /My renamed timer/ });
    expect(studio.projects[0].title).toBe("My renamed timer");
    await user.click(screen.getByRole("button", { name: "Options for My renamed timer" }));
    await user.click(screen.getByRole("menuitem", { name: "Duplicate" }));
    await screen.findByRole("link", { name: /My renamed timer \(copy\)/ });
    expect(studio.projects[1]).toMatchObject({ title: "My renamed timer (copy)", params: { title: "Keep this", seconds: 75 }, settings: { theme: "midnight", aspect: "9:16" } });
    expect(screen.getByRole("link", { name: "Your videos" }).querySelector(".studio-nav-count")).toHaveTextContent("2");
  });

  it("shows library empty states and keeps export activity in sync with the page", async () => {
    const user = userEvent.setup();
    const view = open("#/videos");
    expect(await screen.findByRole("heading", { name: "No videos yet" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Browse templates/ })).toHaveAttribute("href", "#/templates");
    await user.click(screen.getByRole("link", { name: "Exports" }));
    expect(await screen.findByRole("heading", { name: "No exports yet" })).toBeInTheDocument();
    view.unmount();
    localStorage.setItem(SEEN_EXPORTS_KEY, "[]");
    studio.exports.push({ id: "e9", template: "countdown", title: "Ready timer", format: "mp4", quality: "720p", status: "done", progress: 100, created: 1, url: "/media/timer.mp4", filename: "timer.mp4" });
    open("#/");
    const exportsLink = await screen.findByRole("link", { name: "Exports" });
    await waitFor(() => expect(exportsLink).toHaveAttribute("aria-description"));
    expect(exportsLink.querySelector(".studio-nav-count")).toHaveTextContent("1");
    await user.click(exportsLink);
    expect(await screen.findByText("Ready timer")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download" })).toHaveAttribute("download", "timer.mp4");
    await waitFor(() => expect(JSON.parse(localStorage.getItem(SEEN_EXPORTS_KEY)!)).toContain("e9"));
    await user.click(screen.getByRole("link", { name: "Home" }));
    await screen.findByRole("heading", { name: "What are you making?" });
    expect(exportsLink).not.toHaveAttribute("aria-description");
  });

  it("scopes Studio tokens to Studio routes and clears them for Author and unmount", async () => {
    const view = open("#/");
    await screen.findByRole("searchbox", { name: "Search designs" });
    expect(document.documentElement).toHaveAttribute("data-surface", "studio");
    fireEvent.click(screen.getByRole("link", { name: /Author mode/ }));
    await screen.findByText("Author workspace");
    expect(document.documentElement).not.toHaveAttribute("data-surface");
    act(() => { window.location.hash = "#/"; });
    await screen.findByRole("searchbox", { name: "Search designs" });
    expect(document.documentElement).toHaveAttribute("data-surface", "studio");
    view.unmount();
    expect(document.documentElement).not.toHaveAttribute("data-surface");
  });

  it("combines category and search filters and restores all designs", async () => {
    const user = userEvent.setup();
    open("#/");
    const categories = await screen.findByRole("group", { name: "Template categories" });
    await user.click(within(categories).getByRole("link", { name: "Show numbers" }));
    expect(await screen.findByRole("heading", { name: "Show numbers" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Sales chart/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Classroom timer/ })).not.toBeInTheDocument();
    expect(within(categories).getByRole("link", { name: "Show numbers" })).toHaveAttribute("aria-current", "page");
    await user.type(screen.getByRole("searchbox", { name: "Search designs" }), "classroom");
    expect(screen.getByText(/Nothing matches/)).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Show all designs" }));
    await waitFor(() => expect(screen.getByRole("searchbox", { name: "Search designs" })).toHaveValue(""));
    expect(screen.getByRole("link", { name: /Classroom timer/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Templates" })).toHaveAttribute("aria-current", "page");
  });

  it("loads an uncached saved poster only near the viewport and keeps its saved content", async () => {
    const observers: Array<{ target: Element; callback: IntersectionObserverCallback }> = [];
    vi.stubGlobal("IntersectionObserver", class {
      callback: IntersectionObserverCallback;
      constructor(callback: IntersectionObserverCallback) { this.callback = callback; }
      observe(target: Element) { observers.push({ target, callback: this.callback }); }
      disconnect() {}
    });
    try {
      studio.projects.push({ id: "p9", title: "My timer", template: "countdown", params: { title: "My own timer", seconds: 75 }, settings: { aspect: "9:16", theme: "midnight" }, created: 1, updated: 1 });
      open("#/");
      const saved = await screen.findByRole("link", { name: /My timer/ });
      expect(studio.calls.some((call) => call.path === "/api/studio/projects/p9")).toBe(false);
      const observer = observers.find(({ target }) => target.contains(saved))!;
      expect(observer).toBeDefined();
      act(() => observer.callback([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver));
      await waitFor(() => expect(saved.querySelector("img")).toHaveAttribute("src", expect.stringMatching(/\/media\/studio\/previews\//)));
      expect(studio.previews()).toEqual([{ template: "countdown", params: { title: "My own timer", seconds: 75 }, settings: { aspect: "9:16", theme: "midnight" }, mode: "poster" }]);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("uses cached saved posters without fetching full projects", async () => {
    studio.projects.push({ id: "p9", title: "My timer", template: "countdown", params: {}, settings: {}, created: 1, updated: 1 });
    studio.reply = (call) => call.path === "/api/studio/projects" ? { status: 200, body: [{ id: "p9", title: "My timer", template: "countdown", updated: 1, poster_url: "/media/saved.png" }] } : null;
    open("#/");
    const saved = await screen.findByRole("link", { name: /My timer/ });
    expect(saved.querySelector("img")).toHaveAttribute("src", "/media/saved.png");
    expect(studio.calls.some((call) => call.path === "/api/studio/projects/p9")).toBe(false);
  });

  it("fetches AI credentials only on opening, copies the HTTP configuration, and refetches on reopen", async () => {
    const user = userEvent.setup();
    const clipboard = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    studio.reply = (call) => call.path === "/api/studio/connection" ? {
      status: 200, body: { available: true, url: "http://127.0.0.1:8123/mcp/", token: "test-token" },
    } : null;
    open("#/");
    const connect = await screen.findByRole("button", { name: "Connect to AI" });
    expect(studio.calls.some((call) => call.path === "/api/studio/connection")).toBe(false);
    await user.click(connect);
    const configuration = await screen.findByRole("textbox", { name: "MCP configuration" });
    expect(JSON.parse(configuration.textContent!)).toEqual({ mcpServers: { composer: {
      url: "http://127.0.0.1:8123/mcp/", headers: { Authorization: "Bearer test•••" },
    } } });
    await user.click(screen.getByRole("button", { name: "Copy configuration" }));
    expect(JSON.parse(clipboard.mock.calls[0][0])).toEqual({ mcpServers: { composer: {
      url: "http://127.0.0.1:8123/mcp/", headers: { Authorization: "Bearer test-token" },
    } } });
    await user.click(screen.getByRole("button", { name: "Show token" }));
    expect(configuration).toHaveTextContent("Bearer test-token");
    await user.click(screen.getByRole("button", { name: "Hide token" }));
    expect(configuration).not.toHaveTextContent("test-token");
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
    expect(screen.getByText(/Keep Manim Studio open/)).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("textbox", { name: "MCP configuration" })).not.toBeInTheDocument();
    await user.click(connect);
    await screen.findByRole("textbox", { name: "MCP configuration" });
    expect(studio.calls.filter((call) => call.path === "/api/studio/connection")).toHaveLength(2);
  });

  it("handles unavailable AI connections and retries connection errors", async () => {
    const user = userEvent.setup();
    let failed = true;
    studio.reply = (call) => call.path === "/api/studio/connection"
      ? failed ? { status: 503, body: { detail: "Still starting." } } : { status: 200, body: { available: false } }
      : null;
    open("#/");
    await user.click(await screen.findByRole("button", { name: "Connect to AI" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("Still starting.")).toBeInTheDocument();
    failed = false;
    await user.click(within(dialog).getByRole("button", { name: "Try again" }));
    expect(await within(dialog).findByText(/AI connections aren't available/)).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Copy configuration" })).not.toBeInTheDocument();
  });

  it("makes saved-video load failures visible and retryable", async () => {
    const user = userEvent.setup();
    let failed = true;
    studio.projects.push({ id: "p9", title: "My timer", template: "countdown", params: {}, settings: {}, created: 1, updated: 1 });
    studio.reply = (call) => call.path === "/api/studio/projects" && failed ? { status: 503, body: { detail: "Try later." } } : null;
    open("#/");
    expect(await screen.findByText(/Couldn't load your videos/)).toBeInTheDocument();
    failed = false;
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("link", { name: /My timer/ })).toBeInTheDocument();
    expect(screen.queryByText(/Couldn't load your videos/)).not.toBeInTheDocument();
  });

  it("deletes a saved video after confirmation", async () => {
    const user = userEvent.setup();
    studio.projects.push({ id: "p9", title: "My timer", template: "countdown", params: {}, settings: {}, created: 1, updated: 1 });
    open("#/");
    await user.click(await screen.findByRole("button", { name: "Options for My timer" }));
    await user.click(screen.getByRole("menuitem", { name: "Delete" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(screen.queryByRole("link", { name: /My timer/ })).not.toBeInTheDocument());
    expect(studio.projects).toHaveLength(0);
  });
  it("shows a card per design with a poster, and filters them", async () => {
    const user = userEvent.setup();
    open("#/");
    expect(await screen.findByRole("heading", { name: "What are you making?" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Timers & countdowns" })).toBeInTheDocument();
    const card = screen.getByRole("link", { name: /Classroom timer/ });
    expect(card).toHaveAttribute("href", "#/new/countdown/classroom-timer");

    await waitFor(() => expect(studio.previews()).toHaveLength(3));
    const poster = studio.previews().find((request) => request.params.title === "Quiet reading time")!;
    expect(poster).toMatchObject({ template: "countdown", mode: "poster", settings: { aspect: "16:9", theme: "clean", energy: "calm" } });
    await waitFor(() => expect(card.querySelector("img")).toHaveAttribute("src", expect.stringMatching(/\/media\/studio\/previews\/\d\.png$/)));
    const sharp = card.querySelector("img")!;
    const ambient = card.querySelector(".studio-poster-ambient")!;
    expect(ambient).toHaveAttribute("src", sharp.getAttribute("src"));
    expect(ambient).toHaveAttribute("alt", "");
    expect(ambient).toHaveAttribute("aria-hidden", "true");
    expect(ambient).toHaveAttribute("loading", "lazy");
    expect(ambient).toHaveAttribute("decoding", "async");
    expect(ambient).toHaveAttribute("data-ready", "false");
    expect(sharp).toHaveAttribute("data-ready", "false");
    expect(card.querySelector(".studio-shimmer")).toBeInTheDocument();
    fireEvent.load(sharp);
    expect(ambient).toHaveAttribute("data-ready", "true");
    expect(sharp).toHaveAttribute("data-ready", "true");
    expect(card.querySelector(".studio-shimmer")).not.toBeInTheDocument();

    const search = screen.getByRole("searchbox", { name: "Search designs" });
    await user.type(search, "revenue");
    expect(screen.getByRole("link", { name: /Sales chart/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Classroom timer/ })).not.toBeInTheDocument();
    await user.clear(search);
    await user.type(search, "classroom");
    // Template tags count too: both countdown cards match.
    expect(screen.getByRole("link", { name: /Classroom timer/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /10…1 countdown/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Sales chart/ })).not.toBeInTheDocument();
    await user.clear(search);
    await user.type(search, "zebra");
    expect(screen.getByText(/Nothing matches "zebra"/)).toBeInTheDocument();
  });

  it("finds saved videos by title alongside templates", async () => {
    const user = userEvent.setup();
    studio.projects.push(
      { id: "p9", title: "Weekend sale", template: "countdown", params: {}, settings: {}, created: 1, updated: 2 },
      { id: "p8", title: "Sale recap", template: "countdown", params: {}, settings: {}, created: 1, updated: 1 },
      { id: "p7", title: "Classroom timer", template: "countdown", params: {}, settings: {}, created: 1, updated: 0 },
    );
    open("#/");
    const search = await screen.findByRole("searchbox", { name: "Search designs" });
    await user.type(search, "sale");

    const videos = await screen.findByRole("region", { name: "Your videos" });
    expect(within(videos).getByRole("link", { name: /Weekend sale/ })).toHaveAttribute("href", "#/project/p9");
    expect(within(videos).getByRole("link", { name: /Sale recap/ })).toHaveAttribute("href", "#/project/p8");
    expect(within(videos).queryByRole("link", { name: /Classroom timer/ })).not.toBeInTheDocument();
    expect(within(videos).getByRole("button", { name: "Options for Weekend sale" })).toBeInTheDocument();
    expect(screen.getByText("2 videos and 1 template matching “sale”")).toBeInTheDocument();
    const templates = screen.getByRole("region", { name: "Templates" });
    expect(within(templates).getByRole("link", { name: /Sales chart/ })).toBeInTheDocument();
    expect(videos.compareDocumentPosition(templates) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    await user.clear(search);
    await user.type(search, "weekend");
    expect(await screen.findByText("1 video matching “weekend”")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Templates" })).not.toBeInTheDocument();

    await user.clear(search);
    await user.type(search, "zebra");
    expect(screen.getByText(/Nothing matches "zebra"/)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Your videos" })).not.toBeInTheDocument();
  });

  it("lists saved videos and links to author mode", async () => {
    studio.projects.push({ id: "p9", title: "My timer", template: "countdown", params: {}, settings: {}, created: 1, updated: Date.now() / 1000 });
    open("#/");
    const saved = await screen.findByRole("link", { name: /My timer/ });
    expect(saved).toHaveAttribute("href", "#/project/p9");
    expect(saved.closest("ul")).toHaveClass("studio-template-grid");
    expect(screen.getByRole("link", { name: /Author mode/ })).toHaveAttribute("href", "#/author");
  });
});

describe("editor", () => {
  it("does not create a project while browsing a preset, then creates one on the first edit", async () => {
    const user = userEvent.setup();
    open("#/new/countdown/classroom-timer");
    await screen.findByRole("textbox", { name: "Title" });
    await user.click(screen.getByRole("radio", { name: /Wide/ })); // Selecting the existing format is not an edit.
    await user.click(screen.getByRole("link", { name: "Back to all designs" }));
    await screen.findByRole("heading", { name: "What are you making?" });
    expect(studio.projects).toHaveLength(0);
    expect(studio.calls.some((call) => call.path === "/api/studio/projects" && call.method === "POST")).toBe(false);
    await user.click(screen.getByRole("link", { name: /Classroom timer/ }));
    fireEvent.change(await screen.findByRole("textbox", { name: "Title" }), { target: { value: "A new timer" } });
    await waitFor(() => expect(studio.projects).toHaveLength(1));
    expect(studio.projects[0].params.title).toBe("A new timer");
  });

  it("creates an untouched project when an export starts, and opens exports in a sheet", async () => {
    const user = userEvent.setup();
    open("#/new/countdown/classroom-timer");
    await user.click(await screen.findByRole("button", { name: "Export" }));
    expect(studio.projects).toHaveLength(0);
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Make video" }));
    await waitFor(() => expect(studio.projects).toHaveLength(1));
    await waitFor(() => expect(studio.exports).toHaveLength(1));
    await user.keyboard("{Escape}");
    const exports = screen.getByRole("button", { name: "Your exports" });
    await waitFor(() => expect(exports).toHaveAttribute("aria-description", "An export is running or ready to open."));
    await user.click(exports);
    const sheet = await screen.findByRole("dialog");
    expect(sheet).toHaveAttribute("data-variant", "sheet");
    expect(sheet).not.toHaveClass("-translate-x-1/2", "-translate-y-1/2");
    expect(within(sheet).getByRole("heading", { name: "Exports" })).toBeInTheDocument();
  });

  it("clears the finished-export indicator after opening Your exports", async () => {
    const user = userEvent.setup();
    localStorage.setItem(SEEN_EXPORTS_KEY, "[]");
    studio.exports.push({ id: "e0", template: "countdown", title: "Finished timer", format: "mp4", quality: "720p", status: "done", progress: 100, created: 1, url: "/media/timer.mp4" });
    open("#/new/countdown/classroom-timer");
    const exports = await screen.findByRole("button", { name: "Your exports" });
    await waitFor(() => expect(exports).toHaveAttribute("aria-description"));
    await user.click(exports);
    expect(await within(await screen.findByRole("dialog")).findByText("Finished timer")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(exports).not.toHaveAttribute("aria-description");
  });

  it("shows character counts on focus or near the limit and only one emphasis hint", async () => {
    const user = userEvent.setup();
    const chart = studio.catalog.templates.find((template) => template.id === "chart")!;
    chart.schema.properties!.another = { type: "string", title: "Another line", description: "Put *stars* around words to highlight them.", maxLength: 40, default: "Hello" };
    chart.schema.$defs!.Point.properties!.text.description = "Put *stars* around words to highlight them.";
    open("#/new/chart/sales");
    const headline = await screen.findByRole("textbox", { name: "Headline" });
    expect(screen.queryByLabelText("15 of 80 characters")).not.toBeInTheDocument();
    await user.click(headline);
    expect(screen.getByLabelText("15 of 80 characters")).toBeInTheDocument();
    await user.click(screen.getByRole("textbox", { name: "Another line" }));
    expect(screen.queryByLabelText("15 of 80 characters")).not.toBeInTheDocument();
    fireEvent.change(headline, { target: { value: "x".repeat(65) } });
    expect(screen.getByLabelText("65 of 80 characters")).toBeInTheDocument();
    fireEvent.change(headline, { target: { value: "x".repeat(80) } });
    expect(screen.getByLabelText("80 of 80 characters")).toHaveClass("text-warning");
    expect(screen.getAllByText(/Tip: \*best\* \u2192/)).toHaveLength(1);
    expect(within(headline.closest<HTMLElement>(".studio-field")!).queryByText("Put *stars* around words to highlight them.")).not.toBeInTheDocument();
    expect(headline).toHaveAccessibleDescription("Tip: *best* \u2192 best");
    expect(headline).toHaveAttribute("aria-describedby", screen.getByText(/Tip: \*best\* \u2192/).id);
  });

  it("groups Look controls and renders timed storyboard frames from the contact sheet", async () => {
    const user = userEvent.setup();
    studio.previewReply = (request) => request.mode === "storyboard" ? {
      status: 200, body: { url: "/media/sheet.png", mode: "storyboard", width: 1304, height: 744, storyboard: { frames: 4, columns: 2, frame_size: [640, 360], times: [0, 2, 4, 6], length: 8 } },
    } : null;
    open("#/new/chart/sales");
    await user.click(await screen.findByRole("tab", { name: /Look/ }));
    expect(within(screen.getByRole("region", { name: "Style" })).getByRole("radiogroup", { name: "Theme" })).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Motion" })).getByRole("radiogroup", { name: "Energy" })).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Details" })).getByRole("combobox", { name: "Numbers and dates" })).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "Storyboard" }));
    const frame = await screen.findByRole("img", { name: "Storyboard: moments from your video" });
    expect(frame).toHaveStyle({ aspectRatio: String(640 / 360) });
    expect(frame.closest(".studio-storyboard-grid")?.querySelectorAll("figure")).toHaveLength(4);
    expect(screen.getByText("16:9 · 8 seconds")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Moment at 0:06" })).toBeInTheDocument();
    expect(screen.getByText("2 s")).toBeInTheDocument();
  });

  it("puts the single emphasis hint in the first supporting repeated field", async () => {
    const chart = studio.catalog.templates.find((template) => template.id === "chart")!;
    chart.schema.properties!.headline.description = "Your headline.";
    chart.schema.$defs!.Point.properties!.text.description = "Use *stars* to highlight words.";
    chart.schema.properties!.later = { type: "string", title: "Later", description: "Use *stars* to highlight words." };
    open("#/new/chart/sales");
    const points = await screen.findByRole("group", { name: "Points" });
    expect(within(points).getByText(/Tip: \*best\* \u2192/)).toBeInTheDocument();
    expect(screen.getAllByText(/Tip: \*best\* \u2192/)).toHaveLength(1);
  });

  it("portals export dialogs outside the editor and preserves keyboard file and quality selection", async () => {
    const user = userEvent.setup();
    open("#/new/chart/sales");
    const preview = await screen.findByRole("region", { name: "Preview" });
    await user.click(screen.getByRole("button", { name: "Export" }));
    const dialog = await screen.findByRole("dialog");
    expect(preview.closest(".studio-editor")).not.toContainElement(dialog);
    expect(dialog.parentElement).toBe(document.body);
    expect(document.querySelector('[data-ui="dialog-overlay"]')?.parentElement).toBe(document.body);
    await user.click(within(dialog).getByRole("radio", { name: "GIF" }));
    const quality = within(dialog).getByRole("radio", { name: "720p" });
    act(() => quality.focus());
    await user.keyboard("[Space]");
    expect(quality).toBeChecked();
    await user.click(within(dialog).getByRole("button", { name: "Make GIF" }));
    expect(studio.exports[0]).toMatchObject({ format: "gif", quality: "720p" });
    act(() => { studio.exports[0] = { ...studio.exports[0], status: "rendering", progress: 42 }; });
    expect(await within(dialog).findByText("42%")).toBeInTheDocument();
  });

  it("keeps invalid number edits visible instead of exporting the previous value", async () => {
    open("#/new/chart/sales");
    const count = await screen.findByRole("textbox", { name: "How many" });
    fireEvent.change(count, { target: { value: "2.5" } });
    fireEvent.blur(count);
    expect(count).toHaveValue("2.5");
    expect(screen.getByText("Type a whole number.")).toBeInTheDocument();
    expect(count).toHaveAttribute("aria-invalid", "true");
    fireEvent.change(count, { target: { value: "12" } });
    fireEvent.blur(count);
    expect(count).toHaveValue("12");
    expect(screen.getByText("From 1 to 9.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
    await waitFor(() => expect(studio.projects[0]?.params.count).toBe(12));
  });

  it("replaces a numeric cell's typed draft when spreadsheet rows are pasted", async () => {
    open("#/new/chart/sales");
    const cell = await screen.findByRole("textbox", { name: "Value, row 1" });
    fireEvent.change(cell, { target: { value: "99" } });
    fireEvent.paste(cell, { clipboardData: { getData: () => "25\ttrue\n30\tfalse" } });
    expect(cell).toHaveValue("25");
    expect(screen.getByRole("textbox", { name: "Value, row 2" })).toHaveValue("30");
    await waitFor(() => expect((studio.previews().at(-1)?.params.bars as Array<{ value: number }>)[0].value).toBe(25));
  });

  it("retries a refused autosave without another edit", async () => {
    const user = userEvent.setup();
    let failed = true;
    studio.reply = (call) => call.method === "POST" && call.path === "/api/studio/projects" && failed
      ? { status: 503, body: { detail: "Save is temporarily unavailable." } } : null;
    open("#/new/countdown/classroom-timer");
    await screen.findByRole("textbox", { name: "Timer length" });
    fireEvent.change(screen.getByRole("textbox", { name: "Title" }), { target: { value: "Reading time" } });
    expect(await screen.findByText(/Save is temporarily unavailable/)).toBeInTheDocument();
    failed = false;
    await user.click(screen.getByRole("button", { name: "Retry save" }));
    await waitFor(() => expect(window.location.hash).toBe("#/project/p1"));
    expect(studio.projects).toHaveLength(1);
    expect(studio.projects[0].params.seconds).toBe(300);
    expect(await screen.findByText("Saved")).toBeInTheDocument();
  });

  it("picks up AI edits saved elsewhere without saving over them, but never over unsaved local edits", async () => {
    studio.projects.push({ id: "p9", title: "My timer", template: "countdown", params: { title: "Original", seconds: 300 }, settings: {}, created: 1, updated: 1 });
    open("#/project/p9");
    await screen.findByRole("textbox", { name: "Title" });
    // Focus without a newer version on the server changes nothing.
    await act(async () => { window.dispatchEvent(new Event("focus")); });
    expect(screen.getByRole("textbox", { name: "Title" })).toHaveValue("Original");
    Object.assign(studio.projects[0], { params: { title: "Changed by AI", seconds: 60 }, title: "AI timer", updated: 2 });
    await act(async () => { window.dispatchEvent(new Event("focus")); });
    await waitFor(() => expect(screen.getByRole("textbox", { name: "Title" })).toHaveValue("Changed by AI"));
    expect(screen.getByRole("textbox", { name: "Timer length" })).toHaveValue("1:00");
    expect(screen.getByRole("textbox", { name: "Video title" })).toHaveValue("AI timer");
    expect(screen.getByText("Updated by your AI")).toBeInTheDocument();
    expect(studio.calls.some((call) => call.method === "PUT")).toBe(false);
    fireEvent.change(screen.getByRole("textbox", { name: "Title" }), { target: { value: "My own edits" } });
    Object.assign(studio.projects[0], { params: { title: "Second AI edit", seconds: 60 }, updated: 3 });
    await act(async () => { window.dispatchEvent(new Event("focus")); });
    expect(screen.getByRole("textbox", { name: "Title" })).toHaveValue("My own edits");
  });

  it("keeps edits typed while a check for AI edits is still running", async () => {
    studio.projects.push({ id: "p9", title: "My timer", template: "countdown", params: {}, settings: {}, created: 1, updated: 1 });
    open("#/project/p9");
    const title = await screen.findByRole("textbox", { name: "Title" });
    let finish!: (result: { status: number; body: unknown }) => void;
    studio.reply = (call) => call.path === "/api/studio/projects/p9" && call.method === "GET"
      ? new Promise((resolve) => { finish = resolve; }) : null;
    await act(async () => { window.dispatchEvent(new Event("focus")); });
    fireEvent.change(title, { target: { value: "Keep my edit" } });
    await act(async () => { finish({ status: 200, body: { ...studio.projects[0], params: { title: "Remote edit" }, updated: 2 } }); });
    expect(title).toHaveValue("Keep my edit");
  });

  it("uses the server's cancellation result when an export has already finished", async () => {
    const user = userEvent.setup();
    studio.reply = (call) => call.path === "/api/studio/exports/e1" && call.method === "DELETE" ? {
      status: 200, body: { ...studio.exports[0], status: "done", url: "/media/studio/exports/e1.mp4", filename: "timer.mp4", progress: 100 },
    } : null;
    open("#/new/countdown/classroom-timer");
    await user.click(await screen.findByRole("button", { name: "Export" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Make video" }));
    await user.click(await within(dialog).findByRole("button", { name: "Cancel export" }));
    expect(await within(dialog).findByRole("heading", { name: "Your file is ready" })).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: "Download" })).toHaveAttribute("download", "timer.mp4");
  });
  it("builds the form from the schema and previews edits", async () => {
    const user = userEvent.setup();
    open("#/new/chart/sales");
    const headline = await screen.findByRole("textbox", { name: "Headline" });
    expect(headline).toHaveValue("Our *best* year");
    expect(screen.queryByText("15/80")).not.toBeInTheDocument();
    await user.click(headline);
    expect(screen.getByText("15/80")).toBeInTheDocument();
    expect(screen.getByText(/Tip: \*best\* \u2192/)).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Label, row 2" })).toHaveValue("2024");
    expect(screen.getByRole("button", { name: /^Point 1/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Change" })).toBeInTheDocument(); // the point's icon
    expect(screen.getByRole("button", { name: "Upload" })).toBeInTheDocument(); // the logo
    expect(screen.getByRole("textbox", { name: "How many" })).toHaveValue("3");
    expect(screen.getByRole("radiogroup", { name: "Format" })).toBeInTheDocument();

    // The first preview goes out at once with the whole look.
    await waitFor(() => expect(studio.previews().length).toBeGreaterThan(0));
    expect(studio.previews()[0]).toMatchObject({
      template: "chart",
      mode: "poster",
      settings: { aspect: "16:9", theme: "clean", energy: "normal", ending: "hold", locale: "en", background: { kind: "theme" } },
    });

    await user.clear(headline);
    await user.type(headline, "Big news");
    await waitFor(() => expect(studio.previews().at(-1)?.params.headline).toBe("Big news"));
    // Typing is debounced: far fewer previews than keystrokes.
    expect(studio.previews().length).toBeLessThan(5);

    // The first edit creates the project and the URL follows, without reloading the editor.
    await waitFor(() => expect(studio.projects).toHaveLength(1));
    expect(studio.projects[0]).toMatchObject({ template: "chart", title: "Sales chart" });
    await waitFor(() => expect(window.location.hash).toBe("#/project/p1"));
    expect(screen.getByRole("textbox", { name: "Headline" })).toHaveValue("Big news");
    await waitFor(() => expect(screen.getByText("Saved")).toBeInTheDocument());

    await user.click(screen.getByRole("radio", { name: /Tall/ }));
    await waitFor(() => expect(studio.previews().at(-1)?.settings.aspect).toBe("9:16"));
  });

  it("shows validation errors on the right fields", async () => {
    const user = userEvent.setup();
    studio.previewReply = (request) =>
      request.params.headline === "x"
        ? {
            status: 422,
            body: {
              detail: "Invalid input for chart.",
              errors: [
                { field: "params.headline", message: "String should have at least 3 characters" },
                { field: "params.bars.1.value", message: "Input should be less than or equal to 100" },
                { field: "settings.length", message: "Input should be less than or equal to 60" },
              ],
            },
          }
        : null;
    open("#/new/chart/sales");
    const headline = await screen.findByRole("textbox", { name: "Headline" });
    await user.clear(headline);
    await user.type(headline, "x");
    expect(await screen.findByText("Use at least 3 characters.")).toBeInTheDocument();
    expect(headline).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Row 2, Value: Use 100 or less.")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Value, row 2" })).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText(/Some fields need a fix/)).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /Look/ }));
    expect(await screen.findByText("Use 60 or less.")).toBeInTheDocument();
  });

  it("pastes rows from a spreadsheet into a table", async () => {
    open("#/new/chart/sales");
    const cell = await screen.findByRole("textbox", { name: "Label, row 1" });
    fireEvent.paste(cell, { clipboardData: { getData: () => "Label\tValue\tHighlight\nNorth\t1.234,5\tyes\nSouth\t2\tno\nWest\t3\t\n" } });
    expect(await screen.findByText("Pasted 3 rows (the header row was left out).")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Label, row 3" })).toHaveValue("West");
    expect(screen.getByRole("textbox", { name: "Value, row 1" })).toHaveValue("1234.5");
    expect(screen.getByRole("checkbox", { name: "Highlight, row 1" })).toBeChecked();
    await waitFor(() =>
      expect(studio.previews().at(-1)?.params.bars).toEqual([
        { label: "North", value: 1234.5, highlight: true },
        { label: "South", value: 2, highlight: false },
        { label: "West", value: 3, highlight: false },
      ]),
    );
  });

  it("adds, moves and removes list items", async () => {
    const user = userEvent.setup();
    open("#/new/chart/sales");
    await screen.findByRole("button", { name: /^Point 1/ });
    await user.click(screen.getByRole("button", { name: "Add point" }));
    const second = screen.getAllByRole("textbox", { name: "Text" })[1];
    await user.type(second, "Cheap");
    await user.click(screen.getByRole("button", { name: "Move Point 2 up" }));
    expect(screen.getAllByRole("textbox", { name: "Text" }).map((input) => (input as HTMLInputElement).value)).toEqual(["Cheap", "Fast"]);
    // maxItems is 3.
    await user.click(screen.getByRole("button", { name: "Add point" }));
    expect(screen.getByRole("button", { name: "Add point" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Remove Point 3" }));
    expect(screen.getAllByRole("textbox", { name: "Text" })).toHaveLength(2);
    await waitFor(() => expect(studio.previews().at(-1)?.params.points).toEqual([{ text: "Cheap", icon: null }, { text: "Fast", icon: "clock" }]));
  });

  it("uses compact labelled rows for single-field items and preserves keyboard move/delete actions", async () => {
    const user = userEvent.setup();
    const chart = studio.catalog.templates.find((template) => template.id === "chart")!;
    delete chart.schema.$defs!.Point.properties!.icon;
    chart.schema.properties!.points["x-item-title"] = "Answer";
    chart.defaults.points = [{ text: "Venus" }, { text: "Mars" }, { text: "Jupiter" }];
    open("#/new/chart/sales");
    const first = await screen.findByRole("textbox", { name: "Answer 1" });
    const second = screen.getByRole("textbox", { name: "Answer 2" });
    expect(first).toHaveValue("Venus");
    expect(second).toHaveValue("Mars");
    expect(screen.queryByRole("button", { name: /^Answer 1/ })).not.toBeInTheDocument();
    expect(first.closest(".studio-compact-item")).toHaveTextContent("A");
    await user.click(second);
    expect(second.closest(".studio-field")?.querySelector(".studio-character-counter")).toHaveTextContent("4/40");
    const move = screen.getByRole("button", { name: "Move Answer 2 up" });
    act(() => move.focus());
    await user.keyboard("{Enter}");
    expect(screen.getByRole("textbox", { name: "Answer 1" })).toBe(second);
    expect(screen.getByRole("textbox", { name: "Answer 2" })).toBe(first);
    expect(screen.getByRole("button", { name: "Move Answer 1 up" })).toBe(move);
    expect(screen.getByRole("button", { name: "Move Answer 1 up" })).toBeDisabled();
    const remove = screen.getByRole("button", { name: "Remove Answer 3" });
    act(() => remove.focus());
    await user.keyboard(" ");
    expect(screen.queryByRole("textbox", { name: "Answer 3" })).not.toBeInTheDocument();
    expect(screen.getByText("2 of 3")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add answer" }));
    expect(screen.getByRole("textbox", { name: "Answer 3" })).toHaveValue("");
    expect(screen.getByText("3 of 3")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add answer" })).toBeDisabled();
  });

  it("starts long multi-field lists with only the first card expanded and keeps collapse with moved data", async () => {
    const user = userEvent.setup();
    const chart = studio.catalog.templates.find((template) => template.id === "chart")!;
    chart.defaults.points = [{ text: "Fast", icon: "clock" }, { text: "Friendly", icon: "gift" }, { text: "Local", icon: "star" }];
    open("#/new/chart/sales");
    expect(await screen.findByRole("button", { name: /^Point 1/ })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: /^Point 2/ })).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("button", { name: /^Point 3/ })).toHaveAttribute("aria-expanded", "false");
    expect(screen.getAllByRole("textbox", { name: "Text" })).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: /^Point 2/ }));
    const second = screen.getAllByRole("textbox", { name: "Text" })[1];
    expect(second).toHaveValue("Friendly");
    await user.click(screen.getByRole("button", { name: "Move Point 2 down" }));
    expect(screen.getByRole("button", { name: /^Point 2/ })).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("button", { name: /^Point 3/ })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getAllByRole("textbox", { name: "Text" })[1]).toBe(second);
    expect(second.closest(".studio-list-item")?.querySelector(".studio-icon-field")).toBeInTheDocument();
  });

  it("shows content-timed duration in Preview without having to open Storyboard", async () => {
    studio.previewReply = (request) => request.mode === "storyboard" ? {
      status: 200, body: { url: "/media/sheet.png", mode: "storyboard", width: 1304, height: 744, storyboard: { frames: 4, columns: 2, frame_size: [640, 360], times: [0, 2, 4, 17.03], length: 17.03 } },
    } : null;
    open("#/new/countdown/classroom-timer");
    expect(await screen.findByText("16:9 · 17 seconds")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Preview" })).toHaveAttribute("aria-checked", "true");
    expect(studio.projects).toHaveLength(0);
  });

  it("uses mm:ss for durations and hides the length slider when the content sets it", async () => {
    const user = userEvent.setup();
    open("#/new/countdown/classroom-timer");
    const timer = await screen.findByRole("textbox", { name: "Timer length" });
    expect(timer).toHaveValue("5:00");
    await user.click(screen.getByRole("button", { name: "30 seconds more" }));
    expect(timer).toHaveValue("5:30");
    await user.clear(timer);
    await user.type(timer, "2:15{Enter}");
    expect(timer).toHaveValue("2:15");
    await waitFor(() => expect(studio.previews().at(-1)?.params.seconds).toBe(135));
    expect(screen.getByRole("radiogroup", { name: "Style" })).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /Look/ }));
    expect(await screen.findByRole("radiogroup", { name: "Theme" })).toBeInTheDocument();
    expect(screen.queryByRole("slider")).not.toBeInTheDocument();
  });

  it("saves a sibling choice and reordered answers together through the editor", async () => {
    const user = userEvent.setup();
    const chart = studio.catalog.templates.find((template) => template.id === "chart")!;
    delete chart.schema.$defs!.Point.properties!.icon;
    chart.schema.properties!.points["x-item-title"] = "Answer";
    chart.schema.properties!.correct = { type: "integer", title: "Correct answer", minimum: 1, maximum: 3, "x-choice-of": "points" };
    chart.defaults.points = [{ text: "Venus" }, { text: "Mars" }, { text: "Jupiter" }];
    chart.defaults.correct = 2;
    open("#/new/chart/sales");
    const correct = await screen.findByRole("radiogroup", { name: "Correct answer" });
    expect(within(correct).getByRole("radio", { name: "B Mars" })).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Move Answer 2 down" }));
    expect(within(correct).getByRole("radio", { name: "C Mars" })).toBeChecked();
    await waitFor(() => expect(studio.previews().at(-1)?.params).toMatchObject({ correct: 3, points: [{ text: "Venus" }, { text: "Jupiter" }, { text: "Mars" }] }));
    await waitFor(() => expect(studio.projects[0]?.params).toMatchObject({ correct: 3, points: [{ text: "Venus" }, { text: "Jupiter" }, { text: "Mars" }] }));
  });

  it("uses the shared colour control for background and gradient stops", async () => {
    const user = userEvent.setup();
    open("#/new/chart/sales");
    await user.click(await screen.findByRole("tab", { name: /Look/ }));
    const background = screen.getByRole("radiogroup", { name: "Background" });
    await user.click(within(background).getByRole("radio", { name: "Color" }));
    const colors = screen.getByRole("radiogroup", { name: "Color" });
    expect(within(colors).getByRole("radio", { name: "Theme color" })).not.toBeChecked();
    expect(screen.getByRole("textbox", { name: "Color, color code" })).toBeInTheDocument();
    await user.click(within(colors).getByRole("radio", { name: "Theme color" }));
    expect(screen.queryByRole("textbox", { name: "Color, color code" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Color" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Hex" }), { target: { value: "#ff3366" } });
    fireEvent.blur(screen.getByRole("textbox", { name: "Hex" }));
    await user.keyboard("{Escape}");
    expect(screen.getByRole("textbox", { name: "Color, color code" })).toHaveValue("#FF3366");
    await user.click(within(background).getByRole("radio", { name: "Gradient" }));
    expect(screen.getByRole("radiogroup", { name: "From" })).toBeInTheDocument();
    expect(screen.getByRole("radiogroup", { name: "To" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "To" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Hex" }), { target: { value: "#123456" } });
    fireEvent.blur(screen.getByRole("textbox", { name: "Hex" }));
    await user.keyboard("{Escape}");
    await waitFor(() => expect(studio.previews().at(-1)?.settings.background).toMatchObject({ kind: "gradient", color: "#FF3366", color2: "#123456" }));
  });

  it("exports a file and offers the download", async () => {
    const user = userEvent.setup();
    open("#/new/countdown/launch-countdown");
    await screen.findByRole("textbox", { name: "Timer length" });
    await user.click(screen.getByRole("button", { name: "Export" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("radio", { name: /GIF/ }));
    await user.click(within(dialog).getByRole("radio", { name: /720p/ }));
    await user.click(within(dialog).getByRole("button", { name: "Make GIF" }));
    await waitFor(() => expect(studio.exports).toHaveLength(1));
    expect(studio.exports[0]).toMatchObject({ template: "countdown", format: "gif", quality: "720p", title: "10…1 countdown" });
    expect(await within(dialog).findByText("Starting")).toBeInTheDocument();

    act(() => {
      Object.assign(studio.exports[0], { status: "done", progress: 100, url: "/media/studio/exports/e1.gif", filename: "countdown.gif", size: 2048 });
    });
    const download = await within(dialog).findByRole("link", { name: "Download" }, { timeout: 4000 });
    expect(download).toHaveAttribute("href", "/media/studio/exports/e1.gif");
    expect(download).toHaveAttribute("download", "countdown.gif");
    expect(within(dialog).getByRole("img", { name: "Your export" })).toBeInTheDocument();
    await waitFor(() => expect(JSON.parse(localStorage.getItem(SEEN_EXPORTS_KEY)!)).toContain("e1"));
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.getByRole("button", { name: "Your exports" })).not.toHaveAttribute("aria-description"));
  });

  it("explains a missing project", async () => {
    open("#/project/gone");
    expect(await screen.findByText("This video couldn't be found.")).toBeInTheDocument();
  });
});

