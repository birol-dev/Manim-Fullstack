import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import { EditorPage } from "./Editor";
import { posterQueue } from "./hooks";
import { installFakeStudio, type FakeStudio } from "./test/fakeStudio";

let studio: FakeStudio;
beforeEach(() => { posterQueue.clear(); studio = installFakeStudio(); });
function open(template = "countdown") { return render(<TooltipProvider><EditorPage catalog={studio.catalog} route={{ kind: "new", template, preset: template === "countdown" ? "break-timer" : "sales" }} onProjectCreated={() => {}} /></TooltipProvider>); }

it("undoes grouped typing and title changes, then saves and previews the restored content", async () => {
  const user = userEvent.setup(); const view = open();
  expect(screen.getByRole("button", { name: "Undo" })).toBeDisabled();
  const title = screen.getByRole("textbox", { name: "Title" });
  await user.clear(title); await user.type(title, "A new title");
  await user.click(screen.getByRole("button", { name: "Undo" }));
  expect(screen.getByRole("textbox", { name: "Title" })).toHaveValue("Quiet reading time");
  expect(screen.getByRole("button", { name: "Undo" })).toBeDisabled();
  fireEvent.keyDown(window, { key: "y", ctrlKey: true });
  expect(screen.getByRole("textbox", { name: "Title" })).toHaveValue("A new title");
  await screen.findByText("Saved");
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(studio.projects[0].params.title).toBe("Quiet reading time"));
  await waitFor(() => expect(studio.previews().at(-1)?.params.title).toBe("Quiet reading time"));
  await user.clear(screen.getByRole("textbox", { name: "Video title" }));
  await user.type(screen.getByRole("textbox", { name: "Video title" }), "Renamed");
  await user.click(screen.getByRole("button", { name: "Undo" }));
  expect(screen.getByRole("textbox", { name: "Video title" })).toHaveValue("Countdown timer");
  await screen.findByText("Saved");
  view.unmount();
  await act(async () => {});
  open();
  expect(screen.getByRole("button", { name: "Undo" })).toBeDisabled();
});

it("leaves native undo to typed focused fields, uses editor undo after blur, and opens Export with Ctrl+E", async () => {
  const user = userEvent.setup(); open();
  const title = screen.getByRole("textbox", { name: "Title" });
  await user.type(title, "!");
  const native = new KeyboardEvent("keydown", { key: "z", ctrlKey: true, bubbles: true, cancelable: true });
  act(() => title.dispatchEvent(native));
  expect(native.defaultPrevented).toBe(false);
  await user.tab();
  fireEvent.keyDown(window, { key: "z", metaKey: true });
  expect(screen.getByRole("textbox", { name: "Title" })).toHaveValue("Quiet reading time");
  fireEvent.keyDown(window, { key: "Z", metaKey: true, shiftKey: true });
  expect(screen.getByRole("textbox", { name: "Title" })).toHaveValue("Quiet reading time!");
  fireEvent.keyDown(window, { key: "e", ctrlKey: true });
  expect(await screen.findByRole("dialog")).toBeInTheDocument();
});

it("undoes format, look changes, list add/remove/move, and table edits", async () => {
  studio.catalog.templates[1].defaults.logo = "logo.png";
  const user = userEvent.setup(); open("chart");
  await user.click(screen.getByRole("button", { name: "Add point" }));
  expect(screen.getByRole("button", { name: /^Point 2/ })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  expect(screen.queryByRole("button", { name: /^Point 2/ })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Add point" }));
  await user.type(screen.getAllByRole("textbox", { name: "Text" })[1], "Second point");
  await user.click(screen.getByRole("button", { name: "Move Point 2 up" }));
  expect(screen.getAllByRole("textbox", { name: "Text" })[0]).toHaveValue("Second point");
  await user.click(screen.getByRole("button", { name: "Undo" }));
  expect(screen.getAllByRole("textbox", { name: "Text" })[0]).toHaveValue("Fast");
  await user.click(screen.getByRole("button", { name: "Remove Point 2" }));
  expect(screen.queryByRole("button", { name: /^Point 2/ })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  expect(screen.getByRole("button", { name: /^Point 2/ })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Remove logo" }));
  expect(screen.queryByRole("button", { name: "Adjust" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  expect(screen.getByRole("button", { name: "Adjust" })).toBeInTheDocument();
  const cell = screen.getByRole("textbox", { name: /Label.*1|1.*Label/ });
  await user.clear(cell); await user.type(cell, "Changed");
  await user.click(screen.getByRole("button", { name: "Undo" }));
  expect(screen.getByRole("textbox", { name: /Label.*1|1.*Label/ })).toHaveValue("2023");
  const format = screen.getByRole("radio", { name: /Tall/ });
  await user.click(format); expect(format).toHaveAttribute("aria-checked", "true");
  await user.click(screen.getByRole("button", { name: "Undo" }));
  expect(screen.getByRole("radio", { name: /Wide/ })).toHaveAttribute("aria-checked", "true");
  await user.click(screen.getByRole("tab", { name: "Look" }));
  await user.click(screen.getByRole("radio", { name: /Bold pop/ }));
  await user.click(screen.getByRole("button", { name: "Undo" }));
  expect(screen.getByRole("radio", { name: /Clean light/ })).toHaveAttribute("aria-checked", "true");
}, 60_000);

it("records an AI update as one undoable step without resaving it until undo", async () => {
  studio.projects.push({ id: "p9", title: "Original project", template: "countdown", params: { title: "Original", seconds: 300 }, settings: {}, created: 1, updated: 1 });
  render(<TooltipProvider><EditorPage catalog={studio.catalog} route={{ kind: "project", id: "p9" }} onProjectCreated={() => {}} /></TooltipProvider>);
  await screen.findByRole("textbox", { name: "Title" });
  Object.assign(studio.projects[0], { title: "AI project", params: { title: "AI title", seconds: 60 }, settings: { theme: "pop" }, updated: 2 });
  await act(async () => { window.dispatchEvent(new Event("focus")); });
  await waitFor(() => expect(screen.getByRole("textbox", { name: "Title" })).toHaveValue("AI title"));
  expect(studio.calls.some((c) => c.method === "PUT")).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "Undo" }));
  expect(screen.getByRole("textbox", { name: "Title" })).toHaveValue("Original");
  expect(screen.getByRole("textbox", { name: "Video title" })).toHaveValue("Original project");
  await waitFor(() => expect(studio.projects[0].params.title).toBe("Original"));
  expect(studio.projects[0].settings.theme).toBe("clean");
  expect(screen.queryByText("Updated by your AI")).not.toBeInTheDocument();
});

it("offers Content, Look and Sound with the existing tab keyboard behaviour, retaining Sound during edits", async () => {
  const user = userEvent.setup(); open();
  expect(screen.getAllByRole("tab").map((tab) => tab.textContent?.trim())).toEqual(["Content", "Look", "Sound"]);
  screen.getByRole("tab", { name: "Content" }).focus();
  await user.keyboard("{ArrowRight}");
  expect(screen.getByRole("tab", { name: "Look" })).toHaveFocus();
  expect(screen.queryByRole("switch", { name: "Sound effects" })).not.toBeInTheDocument();
  await user.keyboard("{ArrowRight}");
  expect(screen.getByRole("tab", { name: "Sound" })).toHaveAttribute("aria-selected", "true");
  await user.click(screen.getByRole("switch", { name: "Sound effects" }));
  await screen.findByText("Saved");
  expect(screen.getByRole("tab", { name: "Sound" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("switch", { name: "Sound effects" })).not.toBeChecked();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  expect(screen.getByRole("switch", { name: "Sound effects" })).toBeChecked();
});
