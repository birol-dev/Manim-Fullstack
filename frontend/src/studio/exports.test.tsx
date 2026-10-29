import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Toaster, toast } from "sonner";
import { afterEach, expect, it, vi } from "vitest";

import { ExportDialog, ExportsPage } from "./exports";
import { installFakeStudio } from "./test/fakeStudio";
import type { ExportJob } from "./types";

const request = () => ({ template: "countdown", params: { seconds: 7 }, settings: {}, title: "Timer" });

const base: ExportJob = {
  id: "e1",
  template: "countdown",
  title: "Weekend sale",
  format: "mp4",
  quality: "720p",
  status: "done",
  progress: 100,
  created: 1,
  url: "/media/studio/exports/weekend-sale-a900e4.mp4",
  filename: "weekend-sale-a900e4.mp4",
  size: 341938,
  duration: 9,
};

type TestJob = Partial<ExportJob> & { width?: number; height?: number; finished?: number | string };

const job = (overrides: TestJob = {}) => ({ ...base, created: Math.floor(Date.now() / 1000), ...overrides }) as ExportJob;

function renderPage(jobs: ExportJob[]) {
  const retry = vi.fn();
  const cancel = vi.fn();
  const view = render(<ExportsPage exports={{ jobs, error: null, cancel, retry }} />);
  return { ...view, retry, cancel };
}

afterEach(() => {
  act(() => { toast.dismiss(); });
});

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

it("shows a muted video or image thumbnail for finished files and keeps the icon for the rest", () => {
  const { container } = renderPage([
    job(),
    job({ id: "e2", title: "Sale sticker", format: "gif", url: "/media/studio/exports/sticker.gif", filename: "sticker.gif" }),
    job({ id: "e3", title: "See-through sale", format: "mov", url: "/media/studio/exports/sale.mov" }),
    job({ id: "e4", title: "Sale intro", status: "rendering", progress: 40, url: null }),
  ]);

  const video = container.querySelector("video")!;
  expect(video).toBeInTheDocument();
  expect(video).toHaveAttribute("src", "/media/studio/exports/weekend-sale-a900e4.mp4#t=0.5");
  expect(video).toHaveAttribute("preload", "metadata");
  expect(video).toHaveAttribute("playsinline");
  expect((video as HTMLVideoElement).muted).toBe(true);
  expect(video).toHaveAttribute("tabindex", "-1");
  expect(video).toHaveAttribute("aria-hidden", "true");
  expect(video).not.toHaveAttribute("controls");

  const image = container.querySelector("img")!;
  expect(image).toHaveAttribute("src", "/media/studio/exports/sticker.gif");
  expect(image).toHaveAttribute("loading", "lazy");
  expect(image).toHaveAttribute("aria-hidden", "true");

  const movRow = screen.getByText("See-through sale").closest("li")!;
  expect(movRow.querySelector("video")).toBeNull();
  expect(movRow.querySelector(".studio-export-icon")).toBeInTheDocument();
  const runningRow = screen.getByText("Sale intro").closest("li")!;
  expect(runningRow.querySelector(".studio-export-icon")).toBeInTheDocument();

  fireEvent.error(video);
  const fallbackRow = screen.getByText("Weekend sale").closest("li")!;
  expect(fallbackRow.querySelector("video")).toBeNull();
  expect(fallbackRow.querySelector(".studio-export-icon")).toBeInTheDocument();
});

it("opens a finished file in a viewer sized to its shape and returns focus when it closes", async () => {
  const user = userEvent.setup();
  renderPage([job({ width: 720, height: 1280 })]);
  const title = screen.getByRole("button", { name: "Weekend sale" });

  await user.click(title);
  const dialog = await screen.findByRole("dialog", { name: "Weekend sale" });
  expect(within(dialog).getByText("Video (MP4) · 720p · 334 KB")).toBeInTheDocument();
  const video = dialog.querySelector("video")!;
  expect(video).toHaveAttribute("src", "/media/studio/exports/weekend-sale-a900e4.mp4");
  expect(video).toHaveAttribute("controls");
  expect(video).toHaveAttribute("autoplay");
  expect(video).toHaveAttribute("aria-label", "Weekend sale");
  expect(video).not.toHaveAttribute("muted");
  expect(within(dialog).getByRole("link", { name: "Download" })).toHaveAttribute("download", "weekend-sale-a900e4.mp4");
  expect(within(dialog).getByRole("link", { name: "Download" })).toHaveAttribute("href", "/media/studio/exports/weekend-sale-a900e4.mp4");
  expect(dialog.querySelector(".studio-export-viewer-media")).toContainElement(video);

  await user.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  await waitFor(() => expect(title).toHaveFocus());
});

it("also opens the viewer from the thumbnail and shows pictures as images", async () => {
  const user = userEvent.setup();
  renderPage([job({ id: "e2", title: "Sale sticker", format: "png", url: "/media/studio/exports/sale.png", filename: "sale.png", size: 2048 })]);
  await user.click(screen.getByRole("button", { name: "Open Sale sticker" }));
  const dialog = await screen.findByRole("dialog", { name: "Sale sticker" });
  expect(within(dialog).getByRole("img", { name: "Sale sticker" })).toHaveAttribute("src", "/media/studio/exports/sale.png");
  expect(within(dialog).getByText("Picture (PNG) · 720p · 2 KB")).toBeInTheDocument();
  expect(dialog.querySelector("video")).toBeNull();
});

it("asks before deleting an export and calls the remove endpoint only after confirmation", async () => {
  const user = userEvent.setup();
  const requests: Array<{ input: RequestInfo | URL; init?: RequestInit }> = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    requests.push({ input, init });
    return { ok: true, status: 200, headers: new Headers(), json: async () => ({}) } as unknown as Response;
  }));
  try {
    const { retry } = renderPage([job()]);
    render(<Toaster />);

    await user.click(screen.getByRole("button", { name: "Options for Weekend sale" }));
    await user.click(screen.getByRole("menuitem", { name: "Delete file" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete “Weekend sale”?" });
    expect(within(dialog).getByText("The video file is removed from your computer. Your project stays.")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Keep it" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(requests).toHaveLength(0);

    await user.click(screen.getByRole("button", { name: "Options for Weekend sale" }));
    await user.click(screen.getByRole("menuitem", { name: "Delete file" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete file" }));

    await waitFor(() => expect(requests).toHaveLength(1));
    expect(String(requests[0].input)).toBe("/api/studio/exports/e1?remove=true");
    expect(requests[0].init?.method).toBe("DELETE");
    expect(await screen.findByText("Export deleted")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("button", { name: "Weekend sale" })).not.toBeInTheDocument());
    expect(retry).toHaveBeenCalled();
  } finally {
    vi.unstubAllGlobals();
  }
});

it("offers Download only for finished files and keeps Cancel on running ones", async () => {
  const user = userEvent.setup();
  renderPage([job(), job({ id: "e2", title: "Broken sale", status: "failed", error: "bad" }), job({ id: "e3", title: "Running sale", status: "rendering", progress: 20, url: null })]);
  await user.click(screen.getByRole("button", { name: "Options for Weekend sale" }));
  expect(screen.getByRole("menuitem", { name: "Download" })).toHaveAttribute("href", "/media/studio/exports/weekend-sale-a900e4.mp4");
  expect(screen.getByRole("menuitem", { name: "Download" })).toHaveAttribute("download", "weekend-sale-a900e4.mp4");
  await user.keyboard("{Escape}");
  await user.click(screen.getByRole("button", { name: "Options for Broken sale" }));
  expect(screen.queryByRole("menuitem", { name: "Download" })).not.toBeInTheDocument();
  expect(screen.getByRole("menuitem", { name: "Delete file" })).toBeInTheDocument();
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("button", { name: "Options for Running sale" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
});

it("groups finished files by local day, newest first", () => {
  const at = (days: number, hour = 12) => {
    const now = new Date();
    return Math.floor(new Date(now.getFullYear(), now.getMonth(), now.getDate() - days, hour).getTime() / 1000);
  };
  renderPage([
    job({ id: "a", title: "Today early", created: at(0, 8) }),
    job({ id: "b", title: "Today late", created: at(0, 18) }),
    job({ id: "c", title: "Finished today", created: at(1), finished: at(0, 10) }),
    job({ id: "d", title: "Yesterday file", created: at(1, 9) }),
    job({ id: "e", title: "Last week file", created: at(6) }),
  ]);

  const day = (label: string) => screen.getByRole("heading", { name: label }).closest("section")!;
  const titles = (label: string) => within(day(label)).getAllByRole("listitem").map((item) => item.querySelector(".studio-export-title")?.textContent);
  expect(titles("Today")).toEqual(["Today late", "Finished today", "Today early"]);
  expect(titles("Yesterday")).toEqual(["Yesterday file"]);
  expect(titles("Earlier")).toEqual(["Last week file"]);
  const headings = screen.getAllByRole("heading", { level: 2 }).map((heading) => heading.textContent);
  expect(headings).toEqual(["Today", "Yesterday", "Earlier"]);
});
