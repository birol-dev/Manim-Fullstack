import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resetCatalogCache } from "./api";
import { SIDEBAR_KEY } from "./appearance";
import { posterQueue } from "./hooks";
import StudioApp from "./StudioApp";
import { installFakeStudio, type FakeStudio } from "./test/fakeStudio";

vi.mock("@/App", () => ({ default: () => <div>Author workspace</div> }));

let viewport = { width: 1440, height: 900 };
let studio: FakeStudio;

function matches(query: string) {
  const maxWidth = /\(max-width: (\d+)px\)/.exec(query);
  const maxHeight = /\(max-height: (\d+)px\)/.exec(query);
  if (maxWidth) return viewport.width <= Number(maxWidth[1]);
  if (maxHeight) return viewport.height <= Number(maxHeight[1]);
  return false;
}

beforeEach(() => {
  resetCatalogCache();
  posterQueue.clear();
  viewport = { width: 1440, height: 900 };
  window.history.replaceState(null, "", "/#/");
  studio = installFakeStudio();
  vi.spyOn(window, "matchMedia").mockImplementation((query) => ({
    get matches() { return matches(query); },
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  } as MediaQueryList));
});

function open() {
  return render(<StudioApp />);
}

async function rail() {
  return screen.findByRole("navigation", { name: "Studio" });
}

async function libraryPanel() {
  return screen.findByRole("navigation", { name: "Library" });
}

async function loaded() {
  await screen.findByRole("heading", { name: "What are you making?" });
}

describe("rail and side panel", () => {
  it("keeps every destination in the rail and the create list in the panel", async () => {
    open();
    await loaded();
    const nav = await rail();
    for (const [name, href] of [["Home", "#/"], ["Templates", "#/templates"], ["Your videos", "#/videos"], ["Exports", "#/exports"]]) {
      expect(within(nav).getByRole("link", { name })).toHaveAttribute("href", href);
    }
    expect(within(nav).getByRole("link", { name: "Home" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Connect to AI" })).toHaveAttribute("href", "#/settings/ai");
    expect(within(nav).getByRole("link", { name: "Settings" })).toHaveAttribute("href", "#/settings");
    expect(within(nav).getByRole("link", { name: "Author mode" })).toHaveAttribute("href", "#/author");

    const panel = await libraryPanel();
    expect(screen.getByRole("searchbox", { name: "Search designs" })).toHaveAttribute("aria-keyshortcuts", "Control+k Meta+k /");
    expect(within(panel).getByRole("heading", { name: "Create" })).toBeInTheDocument();
    const categories = within(panel).getByRole("group", { name: "Template categories" });
    expect(within(categories).getByRole("link", { name: "Timers & countdowns" })).toHaveAttribute("href", "#/templates/timers");
    expect(within(categories).getByRole("link", { name: "Show numbers" })).toBeInTheDocument();
    expect(within(panel).getByRole("heading", { name: "Recents" })).toBeInTheDocument();
    expect(within(panel).getByText("Your videos will appear here.")).toBeInTheDocument();
    // The appearance control moved to Settings.
    expect(screen.queryByRole("radiogroup", { name: "Appearance" })).not.toBeInTheDocument();
  });

  it("lists the five most recent videos in the panel, newest first", async () => {
    for (let i = 1; i <= 6; i++) studio.projects.push({ id: `p${i}`, title: `Video ${i}`, template: "countdown", params: {}, settings: {}, created: i, updated: i });
    open();
    await loaded();
    const panel = await libraryPanel();
    await within(panel).findByRole("link", { name: /Video 6/ });
    const links = within(panel).getAllByRole("link").filter((link) => link.getAttribute("href")?.startsWith("#/project/"));
    expect(links.map((link) => link.getAttribute("href"))).toEqual(["#/project/p6", "#/project/p5", "#/project/p4", "#/project/p3", "#/project/p2"]);
    expect(within(panel).queryByRole("link", { name: /Video 1/ })).not.toBeInTheDocument();
    expect((await rail()).querySelector(".studio-nav-count")).toHaveTextContent("6");
  });

  it("collapses to the rail and remembers the choice", async () => {
    const user = userEvent.setup();
    const first = open();
    await loaded();
    await user.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    expect(localStorage.getItem(SIDEBAR_KEY)).toBe("true");
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
    const nav = await rail();
    expect(within(nav).getByRole("link", { name: "Home" })).toBeInTheDocument();

    first.unmount();
    open();
    const expand = await screen.findByRole("button", { name: "Expand sidebar" });
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
    await user.click(expand);
    expect(await screen.findByRole("searchbox", { name: "Search designs" })).toBeInTheDocument();
    expect(localStorage.getItem(SIDEBAR_KEY)).toBe("false");
  });

  it("uses the same panel and rail destinations in the phone drawer", async () => {
    const user = userEvent.setup();
    viewport = { width: 800, height: 680 };
    open();
    await loaded();
    const toggle = screen.getByRole("button", { name: "Open navigation" });
    await user.click(toggle);
    const drawer = await screen.findByRole("dialog", { name: "Navigation" });
    expect(within(drawer).getByRole("searchbox", { name: "Search designs" })).toBeInTheDocument();
    expect(within(drawer).getByRole("group", { name: "Template categories" })).toBeInTheDocument();
    expect(within(drawer).getByRole("heading", { name: "Recents" })).toBeInTheDocument();
    expect(within(drawer).getByRole("link", { name: "Home" })).toHaveAttribute("aria-current", "page");
    expect(within(drawer).getByRole("link", { name: "Settings" })).toHaveAttribute("href", "#/settings");
    expect(within(drawer).getByRole("link", { name: "Author mode" })).toHaveAttribute("href", "#/author");

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(toggle).toHaveFocus();
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    expect(await screen.findByRole("searchbox", { name: "Search designs" })).toHaveFocus();

    await user.click(screen.getByRole("link", { name: "Your videos" }));
    expect(await screen.findByRole("heading", { name: "No videos yet" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("fades only the panel edges with more content", async () => {
    viewport = { width: 1000, height: 620 };
    const scrollHeight = vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockReturnValue(600);
    const clientHeight = vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(300);
    try {
      open();
      const panel = await libraryPanel();
      expect(panel).toHaveAttribute("data-fade", "bottom");
      panel.scrollTop = 150;
      fireEvent.scroll(panel);
      expect(panel).toHaveAttribute("data-fade", "both");
      panel.scrollTop = 300;
      fireEvent.scroll(panel);
      expect(panel).toHaveAttribute("data-fade", "top");
    } finally {
      scrollHeight.mockRestore();
      clientHeight.mockRestore();
    }
  });
});
