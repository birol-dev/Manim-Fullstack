import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resetCatalogCache } from "./api";
import { APPEARANCE_KEY, CATEGORIES_KEY, readAppearance, readCategoriesOpen, readCollapsed, setAppearance, setCollapsed, SIDEBAR_KEY } from "./appearance";
import { readRecentColors, RECENT_COLORS_KEY, rememberColor } from "./color";
import {
  BRAND_COLOR_KEY,
  BRAND_KIT_KEY,
  flushPreferences,
  loadPreferences,
  needsOnboarding,
  PREFERENCE_FLUSH_MS,
  readBrandColor,
  readBrandKit,
  readBrandName,
  readDefaultFormat,
  readDefaultTheme,
  readOnboardingDone,
  readPreference,
  resetPreferencesForTests,
  setBrandColor,
  setBrandKit,
  setBrandName,
  setDefaultFormat,
  setDefaultTheme,
  setOnboardingDone,
} from "./preferences";
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

  it("restores the theme and collapsed panel from the workspace with empty storage", async () => {
    const user = userEvent.setup();
    servePreferences({
      appearance: "dark",
      sidebar_collapsed: true,
      template_categories_open: false,
      recent_colors: ["#123456"],
      seen_exports: ["e1"],
      onboarding_done: true,
    });

    await loadPreferences(500);
    expect(localStorage.getItem(APPEARANCE_KEY)).toBe("dark");
    expect(readRecentColors()).toEqual(["#123456"]);

    const view = render(<StudioApp />);
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(await screen.findByRole("button", { name: "Expand sidebar" })).toBeInTheDocument();
    expect(screen.queryByRole("searchbox", { name: "Search designs" })).not.toBeInTheDocument();
    expect(readCategoriesOpen()).toBe(false);

    await user.click(screen.getByRole("button", { name: "Expand sidebar" }));
    expect(await screen.findByRole("searchbox", { name: "Search designs" })).toBeInTheDocument();
    expect(await screen.findByRole("group", { name: "Template categories" })).toBeInTheDocument();
    expect(localStorage.getItem(SIDEBAR_KEY)).toBe("false");
    view.unmount();
  });

  it("reads and writes the onboarding, brand and default-video choices", async () => {
    servePreferences({
      onboarding_done: false,
      brand_name: "  Server Brand  ",
      brand_color: "#00ff00",
      brand_kit: { accent: "#0000ff", logo: "server.svg" },
      default_format: "mp4",
      default_theme: "clean",
    });
    await loadPreferences(500);
    expect(readOnboardingDone()).toBe(false);
    expect(readBrandName()).toBe("Server Brand");
    expect(readBrandColor()).toBe("#00FF00");
    expect(readBrandKit()).toEqual({ accent: "#0000FF", logo: "server.svg" });
    expect(readDefaultFormat()).toBe("mp4");
    expect(readDefaultTheme()).toBe("clean");

    setOnboardingDone(true);
    setBrandName("Acme Studio");
    setBrandColor("#ff3366");
    const kit = { accent: "#12ab34", accent2: null, font: "JetBrains Mono", logo: "brand.svg" };
    setBrandKit(kit);
    setDefaultFormat("gif");
    setDefaultTheme("midnight");
    expect(readOnboardingDone()).toBe(true);
    expect(readBrandName()).toBe("Acme Studio");
    expect(readBrandColor()).toBe("#FF3366");
    expect(readBrandKit()).toEqual({ accent: "#12AB34", accent2: null, font: "JetBrains Mono", logo: "brand.svg" });
    expect(readDefaultFormat()).toBe("gif");
    expect(readDefaultTheme()).toBe("midnight");

    setBrandName("x".repeat(120));
    expect(readBrandName()).toHaveLength(80);

    await flushPreferences();
    const patch = studio.calls.find((call) => call.method === "PATCH" && call.path === "/api/studio/preferences");
    expect(patch?.body).toMatchObject({
      onboarding_done: true,
      brand_name: "x".repeat(80),
      brand_color: "#FF3366",
      brand_kit: { accent: "#12AB34", accent2: null, font: "JetBrains Mono", logo: "brand.svg" },
      default_format: "gif",
      default_theme: "midnight",
    });
  });

  it("starts a new video's brand from brand_color when the kit has no main colour", async () => {
    servePreferences({ brand_color: "#00ff00", brand_kit: { logo: "brand.png" } });
    await loadPreferences(500);
    expect(readBrandKit()).toEqual({ logo: "brand.png", accent: "#00FF00" });

    // A kit's own accent wins; a malformed kit is ignored rather than breaking the fallback.
    setBrandKit({ accent: "#123456" });
    expect(readBrandKit()).toEqual({ accent: "#123456" });
    resetPreferencesForTests();
    localStorage.setItem(BRAND_KIT_KEY, JSON.stringify({ accent: "blue", logo: "../outside.png" }));
    localStorage.setItem(BRAND_COLOR_KEY, "#FF3366");
    expect(readBrandKit()).toEqual({ accent: "#FF3366" });
  });

  it("falls back to defaults when neither the workspace nor the cache has a value", async () => {
    // Until the workspace answers (a test without a preferences mock), the gallery stays put.
    expect(needsOnboarding()).toBe(false);
    servePreferences({});
    await loadPreferences(500);
    expect(readAppearance()).toBe("system");
    expect(readCollapsed()).toBe(false);
    expect(readCategoriesOpen()).toBeNull();
    expect(readRecentColors()).toEqual([]);
    expect(readPreference("seen_exports")).toBeUndefined();
    // A real answer with no onboarding key starts the tour, until it writes `true`.
    expect(needsOnboarding()).toBe(true);
    expect(readOnboardingDone()).toBe(false);
    expect(readBrandName()).toBe("");
    expect(readBrandColor()).toBeNull();
    expect(readDefaultFormat()).toBeNull();
    expect(readDefaultTheme()).toBeNull();
  });
});
