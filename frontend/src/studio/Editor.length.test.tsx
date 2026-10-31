/** The caption shows the measured duration and follows an edit after one debounce. */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";

import { EditorPage } from "./Editor";
import { posterQueue } from "./hooks";
import { installFakeStudio, type FakeStudio } from "./test/fakeStudio";
import type { PreviewRequest } from "./types";

const lengthOf = (body: unknown) => (body as Omit<PreviewRequest, "mode">).params.seconds;

let studio: FakeStudio;

beforeEach(() => {
  posterQueue.clear();
  studio = installFakeStudio();
  // The timing pass measures the current params; here the countdown's seconds stand in for it.
  studio.reply = (call) => call.path === "/api/studio/length"
    ? { status: 200, body: { length: lengthOf(call.body) } }
    : null;
});

function open() {
  return render(
    <TooltipProvider>
      <EditorPage catalog={studio.catalog} route={{ kind: "new", template: "countdown", preset: "classroom-timer" }} onProjectCreated={() => {}} />
    </TooltipProvider>,
  );
}

it("shows the measured length and follows a param edit without rendering", async () => {
  const user = userEvent.setup();
  open();
  expect(await screen.findByText("16:9 · 5 min", {}, { timeout: 2000 })).toBeInTheDocument();

  const timer = screen.getByRole("textbox", { name: "Timer length" });
  await user.clear(timer);
  await user.type(timer, "1:00{Enter}");

  expect(await screen.findByText("16:9 · 1 min", {}, { timeout: 2000 })).toBeInTheDocument();
  expect(screen.queryByText("16:9 · 5 min")).not.toBeInTheDocument();
  // The caption comes from the timing pass for the edited params.
  expect(studio.calls.filter((call) => call.path === "/api/studio/length").length).toBeGreaterThanOrEqual(2);
});

it("updates the steps caption from 2 to 7 steps within one debounce", async () => {
  const steps = [{ text: "First step" }, { text: "Second step" }];
  studio.catalog.templates.push({
    ...studio.catalog.templates[0], id: "steps", title: "Steps", default_aspect: "9:16",
    default_length: 14, length_from_params: false, defaults: { steps }, presets: [],
    schema: {
      type: "object", properties: {
        steps: {
          type: "array", title: "Steps", minItems: 2, maxItems: 7, "x-widget": "list", "x-item-title": "Step",
          items: { type: "object", properties: { text: { type: "string", title: "Step", default: "Next step", "x-widget": "text" } } },
        },
      },
    },
  });
  studio.reply = (call) => {
    if (call.path !== "/api/studio/length") return null;
    const count = ((call.body as PreviewRequest).params.steps as unknown[]).length;
    return { status: 200, body: { length: count === 2 ? 11.5 : count === 7 ? 30.97 : null } };
  };
  render(<TooltipProvider><EditorPage catalog={studio.catalog} route={{ kind: "new", template: "steps", preset: "default" }} onProjectCreated={() => {}} /></TooltipProvider>);
  expect(await screen.findByText("9:16 · 12 seconds", {}, { timeout: 2000 })).toBeInTheDocument();
  const before = studio.calls.filter((call) => call.path === "/api/studio/length").length;
  for (let index = 0; index < 5; index++) fireEvent.click(screen.getByRole("button", { name: "Add step" }));
  expect(await screen.findByText("9:16 · 31 seconds", {}, { timeout: 2000 })).toBeInTheDocument();
  expect(studio.calls.filter((call) => call.path === "/api/studio/length")).toHaveLength(before + 1);
  expect(screen.getByRole("button", { name: "Add step" })).toBeDisabled();
});

it("keeps the existing caption when no duration is available", async () => {
  studio.reply = (call) => call.path === "/api/studio/length" ? { status: 200, body: { length: null } } : null;
  open();
  await waitFor(() => expect(studio.calls.some((call) => call.path === "/api/studio/length")).toBe(true));
  expect(screen.getByText("16:9 · 5 min")).toBeInTheDocument();
});
