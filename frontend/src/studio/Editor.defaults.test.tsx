/** A new video starts with the workspace's defaults; a saved video keeps everything it had. */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";

import { EditorPage } from "./Editor";
import { posterQueue } from "./hooks";
import { BRAND_COLOR_KEY, DEFAULT_FORMAT_KEY, DEFAULT_THEME_KEY, resetPreferencesForTests } from "./preferences";
import { installFakeStudio, type FakeStudio } from "./test/fakeStudio";

let studio: FakeStudio;

beforeEach(() => {
  posterQueue.clear();
  resetPreferencesForTests();
  studio = installFakeStudio();
});

function open(template = "countdown", preset = "classroom-timer") {
  return render(
    <TooltipProvider>
      <EditorPage catalog={studio.catalog} route={{ kind: "new", template, preset }} onProjectCreated={() => {}} />
    </TooltipProvider>,
  );
}

/** The card's own choices, which the workspace's defaults replace only when they fit. */
function card(id = "classroom-timer") {
  return studio.catalog.templates[0].presets.find((item) => item.id === id)!;
}

const lastPreview = () => studio.previews().at(-1);

function setDefaults({ format = "9:16", theme = "pop", brand = "#FF3366" } = {}) {
  localStorage.setItem(DEFAULT_FORMAT_KEY, format);
  localStorage.setItem(DEFAULT_THEME_KEY, theme);
  localStorage.setItem(BRAND_COLOR_KEY, brand);
}

it("starts a new video with the workspace's format, theme and brand colour, and undo keeps them", async () => {
  setDefaults();
  const user = userEvent.setup();
  open();

  // The very first request already carries the defaults, before anything is edited.
  await waitFor(() => expect(studio.previews()[0]).toMatchObject({
    mode: "poster",
    settings: { aspect: "9:16", theme: "pop", brand: { accent: "#FF3366" } },
  }));
  expect(screen.getByRole("radio", { name: /Tall/ })).toHaveAttribute("aria-checked", "true");
  await user.click(screen.getByRole("tab", { name: "Look" }));
  expect(screen.getByRole("radio", { name: "Bold pop" })).toHaveAttribute("aria-checked", "true");

  await user.click(screen.getByRole("radio", { name: /Wide/ }));
  await waitFor(() => expect(lastPreview()?.settings.aspect).toBe("16:9"));
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(lastPreview()?.settings).toMatchObject({
    aspect: "9:16",
    theme: "pop",
    brand: { accent: "#FF3366" },
  }));
});

it("keeps the card's own format, theme and no brand colour when no defaults are set", async () => {
  card().settings = { ...card().settings, aspect: "4:5", theme: "pop" };
  open();

  await waitFor(() => expect(studio.previews()[0]?.settings).toMatchObject({ aspect: "4:5", theme: "pop" }));
  expect(lastPreview()?.settings.brand).toBeUndefined();
  expect(screen.getByRole("radio", { name: /Portrait/ })).toHaveAttribute("aria-checked", "true");
});

it("keeps the card's own format when the template cannot use the default one", async () => {
  localStorage.setItem(DEFAULT_FORMAT_KEY, "9:16");
  studio.catalog.templates[0].aspects = ["16:9", "4:5"];
  card().settings = { ...card().settings, aspect: "4:5" };
  open();

  await waitFor(() => expect(lastPreview()?.settings.aspect).toBe("4:5"));
  expect(screen.getByRole("radio", { name: /Portrait/ })).toHaveAttribute("aria-checked", "true");
});

it("keeps the card's own theme when the default names a theme that doesn't exist", async () => {
  localStorage.setItem(DEFAULT_THEME_KEY, "not-a-theme");
  open();

  await waitFor(() => expect(lastPreview()?.settings.theme).toBe("clean"));
});

it("never applies the defaults to a saved video", async () => {
  setDefaults();
  studio.projects.push({
    id: "p1",
    title: "Saved video",
    template: "countdown",
    params: { seconds: 60 },
    settings: { aspect: "1:1", theme: "clean" },
    created: 1,
    updated: 1,
  });
  render(
    <TooltipProvider>
      <EditorPage catalog={studio.catalog} route={{ kind: "project", id: "p1" }} onProjectCreated={() => {}} />
    </TooltipProvider>,
  );

  await waitFor(() => expect(lastPreview()?.settings).toMatchObject({ aspect: "1:1", theme: "clean" }));
  expect(lastPreview()?.settings.brand).toBeUndefined();
});
