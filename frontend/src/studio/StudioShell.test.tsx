import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resetCatalogCache } from "./api";
import { CATEGORIES_KEY } from "./appearance";
import { posterQueue } from "./hooks";
import StudioApp from "./StudioApp";
import { installFakeStudio } from "./test/fakeStudio";

vi.mock("@/App", () => ({ default: () => <div>Author workspace</div> }));

let viewport = { width: 1440, height: 900 };

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
  installFakeStudio();
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

async function sidebar() {
  return screen.findByRole("navigation", { name: "Studio" });
}

async function loaded() {
  await screen.findByRole("heading", { name: "What are you making?" });
}

describe("sidebar on short windows", () => {
  it("starts with the template categories closed and keeps every destination in the nav", async () => {
    const user = userEvent.setup();
    viewport = { width: 1000, height: 680 };
    open();
    await loaded();
    const nav = await sidebar();
    expect(within(nav).queryByRole("group", { name: "Template categories" })).not.toBeInTheDocument();
    expect(within(nav).getByRole("button", { name: "Expand template categories" })).toHaveAttribute("aria-expanded", "false");
    for (const name of ["Home", "Templates", "Your videos", "Exports"]) {
      expect(within(nav).getByRole("link", { name })).toBeInTheDocument();
    }
    expect(screen.getByRole("button", { name: "Connect to AI" })).toBeInTheDocument();
    expect(screen.getByRole("radiogroup", { name: "Appearance" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Author mode" })).toBeInTheDocument();
    expect(localStorage.getItem(CATEGORIES_KEY)).toBeNull();
    await user.click(within(nav).getByRole("button", { name: "Expand template categories" }));
    expect(within(nav).getByRole("link", { name: "Timers & countdowns" })).toBeInTheDocument();
  });

  it("lets an explicit expand win on short windows and remembers it", async () => {
    const user = userEvent.setup();
    viewport = { width: 1000, height: 680 };
    const first = open();
    await loaded();
    const nav = await sidebar();
    await user.click(within(nav).getByRole("button", { name: "Expand template categories" }));
    expect(within(nav).getByRole("group", { name: "Template categories" })).toBeInTheDocument();
    expect(localStorage.getItem(CATEGORIES_KEY)).toBe("true");
    first.unmount();
    open();
    expect(await screen.findByRole("group", { name: "Template categories" })).toBeInTheDocument();
  });

  it("keeps an explicit collapse on tall windows and remembers it", async () => {
    const user = userEvent.setup();
    const first = open();
    await loaded();
    const nav = await sidebar();
    expect(within(nav).getByRole("group", { name: "Template categories" })).toBeInTheDocument();
    expect(localStorage.getItem(CATEGORIES_KEY)).toBeNull();
    await user.click(within(nav).getByRole("button", { name: "Collapse template categories" }));
    expect(within(nav).queryByRole("group", { name: "Template categories" })).not.toBeInTheDocument();
    expect(localStorage.getItem(CATEGORIES_KEY)).toBe("false");
    first.unmount();
    open();
    await loaded();
    expect(screen.queryByRole("group", { name: "Template categories" })).not.toBeInTheDocument();
  });

  it("uses the same collapsed default in the mobile drawer and remembers the choice", async () => {
    const user = userEvent.setup();
    viewport = { width: 800, height: 680 };
    open();
    await loaded();
    await user.click(screen.getByRole("button", { name: "Open navigation" }));
    const drawer = await screen.findByRole("dialog", { name: "Navigation" });
    expect(within(drawer).queryByRole("group", { name: "Template categories" })).not.toBeInTheDocument();
    await user.click(within(drawer).getByRole("button", { name: "Expand template categories" }));
    expect(within(drawer).getByRole("group", { name: "Template categories" })).toBeInTheDocument();
    expect(localStorage.getItem(CATEGORIES_KEY)).toBe("true");
  });
});

describe("sidebar overflow", () => {
  it("fades only the edges with more nav items", async () => {
    viewport = { width: 1000, height: 620 };
    const scrollHeight = vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockReturnValue(600);
    const clientHeight = vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(300);
    try {
      open();
      const nav = await sidebar();
      expect(nav).toHaveAttribute("data-fade", "bottom");
      nav.scrollTop = 150;
      fireEvent.scroll(nav);
      expect(nav).toHaveAttribute("data-fade", "both");
      nav.scrollTop = 300;
      fireEvent.scroll(nav);
      expect(nav).toHaveAttribute("data-fade", "top");
    } finally {
      scrollHeight.mockRestore();
      clientHeight.mockRestore();
    }
  });
});
