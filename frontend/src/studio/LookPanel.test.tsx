import { useState } from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { changeBackgroundKind } from "./background";
import { LookPanel } from "./LookPanel";
import { initialSettings } from "./options";
import { BRAND_KIT_KEY, resetPreferencesForTests } from "./preferences";
import { CATALOG } from "./test/fixtures";
import { installFakeStudio, type FakeStudio } from "./test/fakeStudio";
import type { Background, Brand, Theme } from "./types";

const themes: Theme[] = [...CATALOG.themes!, {
  id: "midnight", name: "Midnight", dark: true, bg: "#0B1020", text: "#F3F5FA",
  accent: ["#7C9CFF", "#5EEAD4", "#FBBF24"],
}];

let studio: FakeStudio;

beforeEach(() => {
  resetPreferencesForTests();
  localStorage.clear();
  studio = installFakeStudio();
});

function Panel({
  background = { kind: "theme", color: null, color2: null }, theme = "clean", brand,
}: { background?: Background; theme?: string; brand?: Brand }) {
  const [settings, setSettings] = useState(initialSettings(CATALOG.templates[0], { background, theme, ...(brand ? { brand } : {}) }));
  return <>
    <LookPanel settings={settings} onChange={(patch) => setSettings((previous) => ({ ...previous, ...patch }))} template={CATALOG.templates[0]} themes={themes} errors={{}} />
    <output data-testid="background">{JSON.stringify(settings.background)}</output>
    <output data-testid="brand">{JSON.stringify(settings.brand ?? null)}</output>
  </>;
}

const current = (): Background => JSON.parse(screen.getByTestId("background").textContent!);
const currentBrand = (): Brand | null => JSON.parse(screen.getByTestId("brand").textContent!);
const choose = (label: string) => within(screen.getByRole("radiogroup", { name: "Background" })).getByRole("radio", { name: label });
const brandGroup = () => within(screen.getByRole("region", { name: "Brand" }));

it("starts Color with a soft theme tint and Gradient with two different colours", async () => {
  const user = userEvent.setup();
  render(<Panel />);
  await user.click(choose("Color"));
  const solid = current();
  expect(solid.kind).toBe("solid");
  expect(solid.color).toMatch(/^#[0-9A-F]{6}$/);
  expect(solid.color).not.toBe(themes[0].bg);
  expect(solid.color).not.toBe(themes[0].accent[0]);
  expect(within(screen.getByRole("radiogroup", { name: "Color" })).getByRole("radio", { name: "Theme color" })).not.toBeChecked();
  await user.click(choose("Gradient"));
  expect(current()).toMatchObject({ kind: "gradient", color: solid.color });
  expect(current().color2).toMatch(/^#[0-9A-F]{6}$/);
  expect(current().color2).not.toBe(current().color);
  const before = current();
  await user.click(choose("Theme"));
  await user.click(choose("Gradient"));
  expect(current()).toEqual(before);
});

it("prefills Color and Gradient on a saved Midnight project that still uses the theme background", async () => {
  const user = userEvent.setup();
  render(<Panel theme="midnight" background={{ kind: "theme", color: null, color2: null }} />);
  await user.click(choose("Color"));
  const solid = current();
  expect(solid.kind).toBe("solid");
  expect(solid.color).toMatch(/^#[0-9A-F]{6}$/);
  expect(solid.color).not.toBeNull();
  const midnight = themes[2];
  expect(solid.color).not.toBe(midnight.bg);
  expect(within(screen.getByRole("radiogroup", { name: "Color" })).getByRole("radio", { name: "Theme color" })).not.toBeChecked();
  await user.click(choose("Gradient"));
  expect(current()).toMatchObject({ kind: "gradient", color: solid.color });
  expect(current().color2).toMatch(/^#[0-9A-F]{6}$/);
  expect(current().color2).not.toBeNull();
  expect(current().color2).not.toBe(current().color);
});

it("uses the currently selected theme when opening Gradient for the first time", async () => {
  const user = userEvent.setup();
  render(<Panel />);
  await user.click(screen.getByRole("radio", { name: "Midnight" }));
  await user.click(choose("Gradient"));
  const expected = changeBackgroundKind({ kind: "theme", color: null, color2: null }, "gradient", themes[2], new Set());
  expect(current()).toEqual(expected);
  expect(current().color).not.toBe(changeBackgroundKind({ kind: "theme" }, "solid", themes[0], new Set()).color);
});

it("preserves previously chosen colours when changing modes", async () => {
  const user = userEvent.setup();
  render(<Panel background={{ kind: "theme", color: "#123456", color2: "#ABCDEF" }} />);
  await user.click(choose("Color"));
  expect(current()).toEqual({ kind: "solid", color: "#123456", color2: "#ABCDEF" });
  await user.click(choose("Gradient"));
  expect(current()).toEqual({ kind: "gradient", color: "#123456", color2: "#ABCDEF" });
});

it("keeps Theme color available and remembers deliberate resets across mode changes", async () => {
  const user = userEvent.setup();
  render(<Panel />);
  await user.click(choose("Gradient"));
  for (const label of ["From", "To"]) {
    await user.click(within(screen.getByRole("radiogroup", { name: label })).getByRole("radio", { name: "Theme color" }));
  }
  expect(current()).toEqual({ kind: "gradient", color: null, color2: null });
  await user.click(choose("Theme"));
  await user.click(choose("Color"));
  expect(current().color).toBeNull();
  await user.click(choose("Gradient"));
  expect(current()).toEqual({ kind: "gradient", color: null, color2: null });
});

it("keeps saved Theme color choices and seeds only the newly opened gradient slot", async () => {
  const user = userEvent.setup();
  render(<Panel background={{ kind: "solid", color: null, color2: null }} />);
  await user.click(choose("Gradient"));
  expect(current().color).toBeNull();
  expect(current().color2).toMatch(/^#[0-9A-F]{6}$/);
});

it("shows this video's logo, colors and font, each removable for the video", async () => {
  const user = userEvent.setup();
  render(<Panel brand={{ accent: "#FF3366", accent2: "#00AA88", font: "Inter", logo: "brand.svg" }} />);

  expect(brandGroup().getByRole("heading", { name: "Brand" })).toBeInTheDocument();
  expect(brandGroup().getByText("Shown small in a corner of this video.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Remove logo" })).toBeInTheDocument();

  await user.click(within(screen.getByRole("radiogroup", { name: "Main color" })).getByRole("radio", { name: "#2563EB" }));
  expect(currentBrand()?.accent).toBe("#2563EB");
  await user.click(within(screen.getByRole("radiogroup", { name: "Second color" })).getByRole("radio", { name: "Theme color" }));
  expect(currentBrand()?.accent2).toBeNull();
  await user.click(screen.getByRole("combobox", { name: "Font" }));
  await user.click(await screen.findByRole("option", { name: "JetBrains Mono" }));
  expect(currentBrand()?.font).toBe("JetBrains Mono");
  expect(screen.getByRole("combobox", { name: "Font" })).toHaveTextContent("JetBrains Mono");
  await user.click(screen.getByRole("button", { name: "Remove logo" }));
  expect(currentBrand()?.logo).toBeNull();
});

it("applies the saved kit to this video in one change", async () => {
  const user = userEvent.setup();
  const kit = { accent: "#123456", accent2: "#654321", font: "JetBrains Mono", logo: "brand.png" };
  localStorage.setItem(BRAND_KIT_KEY, JSON.stringify(kit));
  const changes = vi.fn();
  render(<LookPanel settings={initialSettings(CATALOG.templates[0], { theme: "clean" })} onChange={changes} template={CATALOG.templates[0]} themes={themes} errors={{}} />);

  await user.click(screen.getByRole("button", { name: "Use my brand" }));
  expect(changes).toHaveBeenCalledTimes(1);
  expect(changes).toHaveBeenCalledWith({ brand: kit });
});

it("points to the brand settings when no kit is saved yet", () => {
  render(<Panel />);
  expect(screen.queryByRole("button", { name: "Use my brand" })).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Set up your brand" })).toHaveAttribute("href", "#/settings/profile");
});

it("picks one of your pictures as this video's logo", async () => {
  const user = userEvent.setup();
  const previous = studio.reply;
  studio.reply = (call) => call.path === "/api/files" && call.method === "GET"
    ? { status: 200, body: { scripts: [], assets: [{ name: "brand.svg", size: 10, type: "asset", url: "" }], media: [] } }
    : previous?.(call) ?? null;
  render(<Panel />);

  await user.click(screen.getByRole("button", { name: "Your pictures" }));
  await user.click(await screen.findByRole("button", { name: "brand.svg" }));
  expect(currentBrand()?.logo).toBe("brand.svg");
});
