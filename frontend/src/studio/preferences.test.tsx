import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resetCatalogCache } from "./api";
import { APPEARANCE_KEY, CATEGORIES_KEY, readAppearance, readCategoriesOpen, readCollapsed, setAppearance, setCollapsed, SIDEBAR_KEY } from "./appearance";
import { readRecentColors, RECENT_COLORS_KEY, rememberColor } from "./color";
import { loadPreferences, PREFERENCE_FLUSH_MS, readPreference, resetPreferencesForTests } from "./preferences";
import StudioApp from "./StudioApp";
import { installFakeStudio, type FakeStudio } from "./test/fakeStudio";

let studio: FakeStudio;

beforeEach(() => {
  resetPreferencesForTests();
  resetCatalogCache();
  window.history.replaceState(null, "", "/#/");
  studio = installFakeStudio();
  studio.reply = (call) => call.path === "/api/studio/preferences" && call.method === "PATCH"
    ? { status: 200, body: { ...(call.body as object) } }
    : null;
});

function servePreferences(body: unknown) {
  const previous = studio.reply;
  studio.reply = (call) => call.path === "/api/studio/preferences" && call.method === "GET"
    ? { status: 200, body }
    : previous?.(call) ?? null;
}

describe("workspace preferences", () => {
  it("prefers the server value once loaded and keeps the cache for absent keys", async () => {
    localStorage.setItem(APPEARANCE_KEY, "dark");
    localStorage.setItem(SIDEBAR_KEY, "true");
    expect(readAppearance()).toBe("dark");
    expect(readCollapsed()).toBe(true);
    servePreferences({ appearance: "light" });

    await loadPreferences(500);

    expect(readAppearance()).toBe("light");
    expect(localStorage.getItem(APPEARANCE_KEY)).toBe("light");
    // The workspace had no opinion on the sidebar, so the local cache still wins.
    expect(readCollapsed()).toBe(true);
    expect(localStorage.getItem(SIDEBAR_KEY)).toBe("true");
  });

  it("uses the cache while the server is still loading and when it cannot be reached", async () => {
    localStorage.setItem(APPEARANCE_KEY, "dark");
    localStorage.setItem(CATEGORIES_KEY, "false");
    vi.spyOn(globalThis, "fetch").mockImplementation(() => new Promise(() => {}));

    const loading = loadPreferences(10);
    expect(readAppearance()).toBe("dark");
    expect(readCategoriesOpen()).toBe(false);
    await loading;
    expect(readAppearance()).toBe("dark");
    expect(readCategoriesOpen()).toBe(false);

    resetPreferencesForTests();
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("offline"));
    await loadPreferences(500);
    expect(readAppearance()).toBe("dark");
    expect(readCategoriesOpen()).toBe(false);
  });

  it("writes to the local cache at once and to the workspace once, coalesced", async () => {
    servePreferences({});
    await loadPreferences(500);
    vi.useFakeTimers();
    try {
      setAppearance("dark");
      setCollapsed(true);
      rememberColor("#ff3366");
      expect(localStorage.getItem(APPEARANCE_KEY)).toBe("dark");
      expect(localStorage.getItem(SIDEBAR_KEY)).toBe("true");
      expect(JSON.parse(localStorage.getItem(RECENT_COLORS_KEY)!)).toEqual(["#FF3366"]);
      expect(readAppearance()).toBe("dark");
      expect(studio.calls.filter((call) => call.method === "PATCH")).toHaveLength(0);

      await vi.advanceTimersByTimeAsync(PREFERENCE_FLUSH_MS);
      const patches = studio.calls.filter((call) => call.method === "PATCH");
      expect(patches).toHaveLength(1);
      expect(patches[0].body).toEqual({
        appearance: "dark",
        sidebar_collapsed: true,
        recent_colors: ["#FF3366"],
      });
    } finally {
      vi.useRealTimers();
    }
  });

  it("restores the theme, collapsed sidebar and categories from the workspace with empty storage", async () => {
    const user = userEvent.setup();
    servePreferences({
      appearance: "dark",
      sidebar_collapsed: true,
      template_categories_open: false,
      recent_colors: ["#123456"],
      seen_exports: ["e1"],
    });

    await loadPreferences(500);
    expect(localStorage.getItem(APPEARANCE_KEY)).toBe("dark");
    expect(readRecentColors()).toEqual(["#123456"]);

    const view = render(<StudioApp />);
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(await screen.findByRole("button", { name: "Expand sidebar" })).toBeInTheDocument();
    const appearance = await screen.findByRole("radiogroup", { name: "Appearance" });
    expect(within(appearance).getByRole("radio", { name: "Dark" })).toBeChecked();
    expect(readCategoriesOpen()).toBe(false);

    await user.click(screen.getByRole("button", { name: "Expand sidebar" }));
    const toggle = await screen.findByRole("button", { name: "Expand template categories" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("group", { name: "Template categories" })).not.toBeInTheDocument();
    expect(localStorage.getItem(SIDEBAR_KEY)).toBe("false");
    view.unmount();
  });

  it("falls back to defaults when neither the workspace nor the cache has a value", async () => {
    servePreferences({});
    await loadPreferences(500);
    expect(readAppearance()).toBe("system");
    expect(readCollapsed()).toBe(false);
    expect(readCategoriesOpen()).toBeNull();
    expect(readRecentColors()).toEqual([]);
    expect(readPreference("seen_exports")).toBeUndefined();
  });
});
