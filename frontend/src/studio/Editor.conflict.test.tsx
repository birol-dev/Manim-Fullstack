/** An assistant's save and the open Editor: the editor stops instead of overwriting it. */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";

import { EditorPage } from "./Editor";
import { posterQueue } from "./hooks";
import { installFakeStudio, type FakeStudio } from "./test/fakeStudio";

let studio: FakeStudio;

beforeEach(() => {
  posterQueue.clear();
  studio = installFakeStudio();
});

function open() {
  return render(
    <TooltipProvider>
      <EditorPage catalog={studio.catalog} route={{ kind: "project", id: "p9" }} onProjectCreated={() => {}} />
    </TooltipProvider>,
  );
}

it("stops at a save conflict, keeps the person's edits, then loads the newest copy on request", async () => {
  const user = userEvent.setup();
  studio.projects.push({
    id: "p9", title: "My timer", template: "countdown",
    params: { title: "Mine", seconds: 300, style: "ring" }, settings: {}, revision: 1, created: 1, updated: 1,
  });
  open();
  const title = await screen.findByRole("textbox", { name: "Title" });
  const videoTitle = screen.getByRole("textbox", { name: "Video title" });

  // An assistant saves the same project through MCP while this Editor is open.
  Object.assign(studio.projects[0], {
    title: "Assistant timer",
    params: { ...studio.projects[0].params, title: "From the assistant", seconds: 60 },
    revision: 3,
    updated: 2,
  });
  fireEvent.change(title, { target: { value: "My unsaved edit" } });

  expect(await screen.findByText("This video was changed somewhere else.", {}, { timeout: 3000 })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Load the newest version" })).toBeInTheDocument();
  expect(title).toHaveValue("My unsaved edit"); // the person's edits stay on screen
  expect(studio.calls.filter((call) => call.method === "PUT")).toHaveLength(1); // no retry, no overwrite
  expect(studio.projects[0].title).toBe("Assistant timer");
  expect(studio.projects[0].revision).toBe(3);
  expect(studio.projects[0].params).toMatchObject({ title: "From the assistant", seconds: 60 });
  expect(screen.getByRole("button", { name: "Undo" })).toBeEnabled();
  fireEvent.change(title, { target: { value: "Still my unsaved edit" } });
  fireEvent(window, new Event("pagehide"));
  expect(title).toHaveValue("Still my unsaved edit");
  expect(studio.calls.filter((call) => call.method === "PUT")).toHaveLength(1);
  expect(studio.calls.find((call) => call.method === "PUT")?.body).toMatchObject({ base_revision: 1 });

  await user.click(screen.getByRole("button", { name: "Load the newest version" }));
  await waitFor(() => expect(screen.getByRole("textbox", { name: "Title" })).toHaveValue("From the assistant"));
  expect(screen.getByRole("textbox", { name: "Video title" })).toHaveValue("Assistant timer");
  expect(screen.getByRole("textbox", { name: "Video title" })).not.toBe(videoTitle);
  expect(screen.queryByText("This video was changed somewhere else.")).not.toBeInTheDocument();
  // Edits that never reached the project can no longer be undone into it.
  expect(screen.getByRole("button", { name: "Undo" })).toBeDisabled();

  fireEvent.change(screen.getByRole("textbox", { name: "Title" }), { target: { value: "New after load" } });
  await waitFor(() => expect(studio.projects[0].revision).toBe(4), { timeout: 3000 });
  expect(studio.projects[0].params.title).toBe("New after load");
  await user.click(screen.getByRole("button", { name: "Undo" }));
  expect(screen.getByRole("textbox", { name: "Title" })).toHaveValue("From the assistant");
});
