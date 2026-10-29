import { useState } from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { changeBackgroundKind } from "./background";
import { LookPanel } from "./LookPanel";
import { initialSettings } from "./options";
import { CATALOG } from "./test/fixtures";
import type { Background, Theme } from "./types";

const themes: Theme[] = [...CATALOG.themes!, {
  id: "midnight", name: "Midnight", dark: true, bg: "#0B1020", text: "#F3F5FA",
  accent: ["#7C9CFF", "#5EEAD4", "#FBBF24"],
}];

function Panel({ background = { kind: "theme", color: null, color2: null }, theme = "clean" }: { background?: Background; theme?: string }) {
  const [settings, setSettings] = useState(initialSettings(CATALOG.templates[0], { background, theme }));
  return <>
    <LookPanel settings={settings} onChange={(patch) => setSettings((previous) => ({ ...previous, ...patch }))} template={CATALOG.templates[0]} themes={themes} errors={{}} />
    <output data-testid="background">{JSON.stringify(settings.background)}</output>
  </>;
}

const current = (): Background => JSON.parse(screen.getByTestId("background").textContent!);
const choose = (label: string) => within(screen.getByRole("radiogroup", { name: "Background" })).getByRole("radio", { name: label });

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
