import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { ExportDialog } from "./exports";
import { installFakeStudio } from "./test/fakeStudio";
import type { ExportJob } from "./types";

const request = () => ({ template: "countdown", params: { seconds: 7 }, settings: {}, title: "Timer" });

it("keeps the same media well through progress and completion and shows metadata once", async () => {
  const user = userEvent.setup();
  const studio = installFakeStudio();
  const running: ExportJob = { id: "e1", template: "countdown", format: "mp4", quality: "draft", status: "rendering", progress: 25, created: 1, message: "Rendering animation 1 of 10" };
  studio.exports = [running];
  studio.reply = (call) => call.path === "/api/studio/exports" && call.method === "POST" ? { status: 202, body: running } : null;
  const onSeen = vi.fn();
  render(<ExportDialog open onOpenChange={vi.fn()} request={request} transparentBackground={false} onFieldErrors={vi.fn()} onSeen={onSeen} posterUrl="/poster.png" />);
  const dialog = screen.getByRole("dialog");
  await user.click(within(dialog).getByRole("button", { name: "Make video" }));
  expect(await within(dialog).findByRole("heading", { name: "Making your video…" })).toBeInTheDocument();
  const well = within(dialog).getByRole("img", { name: "Preview of your export" }).closest(".studio-result-well");
  expect(well).toHaveAttribute("data-state", "making");
  expect(within(dialog).getAllByText("25%")).toHaveLength(1);
  expect(within(dialog).getByText("Rendering")).toBeInTheDocument();
  expect(within(dialog).getByRole("progressbar", { name: "Export progress" })).toHaveAttribute("aria-valuenow", "25");
  expect(within(dialog).getByText("You can close this. It keeps going in Your exports.")).toBeInTheDocument();
  expect(onSeen).not.toHaveBeenCalled();
  studio.exports = [{ ...running, status: "done", progress: 100, url: "/timer.mp4", filename: "timer.mp4", size: 2048, duration: 7 }];
  await within(dialog).findByRole("heading", { name: "Your file is ready" });
  expect(dialog.querySelector(".studio-result-well")).toBe(well);
  expect(well).toHaveAttribute("data-state", "done");
  expect(within(dialog).getByLabelText("Your exported video")).toHaveAttribute("poster", "/poster.png");
  expect(dialog.querySelector(".studio-file-meta")).toHaveTextContent(/^timer\.mp4$/);
  expect(within(dialog).queryByRole("progressbar")).not.toBeInTheDocument();
  expect(onSeen).toHaveBeenCalledWith("e1");
});

it.each([
  ["GIF", "Make GIF", "Making your GIF…"],
  ["Picture (PNG)", "Make picture", "Making your picture…"],
])("names a %s export while making it", async (format, action, title) => {
  const user = userEvent.setup();
  installFakeStudio();
  render(<ExportDialog open onOpenChange={vi.fn()} request={request} transparentBackground={false} onFieldErrors={vi.fn()} />);
  const dialog = screen.getByRole("dialog");
  await user.click(within(dialog).getByRole("radio", { name: format }));
  await user.click(within(dialog).getByRole("button", { name: action }));
  expect(await within(dialog).findByRole("heading", { name: title })).toBeInTheDocument();
  expect(within(dialog).getByText("Starting")).toBeInTheDocument();
  expect(within(dialog).getByRole("button", { name: "Cancel export" })).toBeInTheDocument();
});

it("keeps a completion unseen while closed, then marks it seen when the result is opened", async () => {
  const user = userEvent.setup();
  const studio = installFakeStudio();
  const onSeen = vi.fn();
  const onActivity = vi.fn();
  const props = { onOpenChange: vi.fn(), request, transparentBackground: false, onFieldErrors: vi.fn(), onSeen, onActivity };
  const view = render(<ExportDialog {...props} open />);
  await user.click(screen.getByRole("button", { name: "Make video" }));
  await screen.findByRole("heading", { name: "Making your video…" });
  view.rerender(<ExportDialog {...props} open={false} />);
  studio.exports = [{ ...studio.exports[0], status: "done", url: "/timer.mp4", filename: "timer.mp4", progress: 100 }];
  await waitFor(() => expect(onActivity).toHaveBeenCalledTimes(2));
  expect(onSeen).not.toHaveBeenCalled();
  view.rerender(<ExportDialog {...props} open />);
  await screen.findByRole("heading", { name: "Your file is ready" });
  expect(onSeen).toHaveBeenCalledWith("e1");
});
