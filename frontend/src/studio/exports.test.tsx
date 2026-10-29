import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Toaster, toast } from "sonner";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { ExportDialog, ExportRow, ExportsPage, ExportsPanel } from "./exports";
import { resetCatalogCache, type ExportRequest } from "./api";
import { installFakeStudio } from "./test/fakeStudio";
import type { ExportJob } from "./types";

beforeEach(() => {
  resetCatalogCache();
});

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

type TestJob = Partial<ExportJob> & { width?: number; height?: number; finished?: number | string; request?: ExportRequest };

const job = (overrides: TestJob = {}) => ({ ...base, created: Math.floor(Date.now() / 1000), ...overrides }) as ExportJob;

function renderPage(jobs: ExportJob[]) {
  const retry = vi.fn();
  const cancel = vi.fn();
  const view = render(<ExportsPage exports={{ jobs, error: null, cancel, retry }} />);
  return { ...view, retry, cancel };
}

it("shows measured progress, plain messages and time left in export rows without regressing", () => {
  const running = job({ status: "rendering", progress: 40, phase: "drawing", message: "Drawing frames…", time_left: "About 1 min left", url: null });
  const cancel = vi.fn();
  const view = render(<ul><ExportRow job={running} onCancel={cancel} /></ul>);
  expect(screen.getByText("40% · Drawing frames…")).toBeInTheDocument();
  expect(screen.getByText("About 1 min left")).toBeInTheDocument();
  const bar = screen.getByRole("progressbar");
  expect(bar).toHaveAttribute("aria-valuenow", "40");
  expect(bar).toHaveClass("[&>div]:duration-700");
  expect(bar.firstElementChild).toHaveStyle({ transform: "translateX(-60%)" });
  view.rerender(<ul><ExportRow job={{ ...running, progress: 20 }} onCancel={cancel} /></ul>);
  expect(bar).toHaveAttribute("aria-valuenow", "40");
  expect(bar.firstElementChild).toHaveStyle({ transform: "translateX(-60%)" });
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(cancel).toHaveBeenCalledWith(expect.objectContaining({ id: running.id }));
  view.rerender(<ul><ExportRow job={{ ...running, progress: 95, phase: "finishing", message: "Finishing your video…" }} /></ul>);
  expect(bar).toHaveAttribute("aria-valuenow", "95");
  expect(screen.getByText("95% · Finishing your video…")).toBeInTheDocument();
  expect(screen.queryByText("About 1 min left")).not.toBeInTheDocument();
  view.rerender(<ul><ExportRow job={{ ...running, id: "fresh", progress: 0 }} /></ul>);
  expect(bar).toHaveAttribute("aria-valuenow", "0");
});

it("renders the progress message and time left in the exports panel", async () => {
  const studio = installFakeStudio();
  studio.exports = [job({ status: "rendering", progress: 62, phase: "drawing", message: "Drawing frames…", time_left: "Less than a minute left", url: null })];
  render(<ExportsPanel open onOpenChange={vi.fn()} />);
  expect(await screen.findByText("62% · Drawing frames…")).toBeInTheDocument();
  expect(screen.getByText("Less than a minute left")).toBeInTheDocument();
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "62");
});

it("keeps dialog progress monotonic through polls and clears time left while finishing", async () => {
  const user = userEvent.setup();
  const studio = installFakeStudio();
  const running = job({ status: "rendering", progress: 45, phase: "drawing", message: "Drawing frames…", time_left: "About 1 min left", url: null });
  studio.exports = [running];
  studio.reply = (call) => call.path === "/api/studio/exports" && call.method === "POST" ? { status: 202, body: running } : null;
  render(<ExportDialog open onOpenChange={vi.fn()} request={request} transparentBackground={false} onFieldErrors={vi.fn()} />);
  await user.click(screen.getByRole("button", { name: "Make video" }));
  expect(await screen.findByText("45%")).toBeInTheDocument();
  expect(screen.getByText("Drawing frames…")).toBeInTheDocument();
  expect(screen.getByText("About 1 min left")).toBeInTheDocument();
  const bar = screen.getByRole("progressbar");
  studio.exports = [{ ...running, progress: 70, time_left: "Less than a minute left" }];
  await screen.findByText("70%");
  studio.exports = [{ ...running, progress: 30, time_left: "Stale poll" }];
  await screen.findByText("Stale poll");
  expect(screen.getByText("70%")).toBeInTheDocument();
  expect(bar).toHaveAttribute("aria-valuenow", "70");
  studio.exports = [{ ...running, progress: 95, phase: "finishing", message: "Finishing your video…", time_left: null }];
  await screen.findByText("Finishing your video…");
  expect(screen.getByText("95%")).toBeInTheDocument();
  expect(screen.queryByText(/minute left|1 min left|Stale poll/)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Cancel export" })).toBeInTheDocument();
});

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

it("hides the 60 fps quality and states the real rate for a template that fixes it", async () => {
  const user = userEvent.setup();
  const studio = installFakeStudio();
  studio.catalog.templates.find((item) => item.id === "countdown")!.export_fps = 15;
  resetCatalogCache();
  render(<ExportDialog open onOpenChange={vi.fn()} request={request} transparentBackground={false} onFieldErrors={vi.fn()} />);
  await waitFor(() => expect(screen.queryByRole("radio", { name: "1080p, 60 fps" })).not.toBeInTheDocument());
  expect(screen.getByRole("radio", { name: "1080p (Full HD)" })).toBeChecked();
  expect(screen.getByText("1080p · 15 fps")).toBeInTheDocument();
  expect(screen.getByText("4K · 15 fps")).toBeInTheDocument();
  expect(screen.getByText("Made at 15 frames per second: smooth for this kind of video, and much quicker to make.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Make video" }));
  await waitFor(() => expect(studio.calls.some((call) => call.method === "POST" && call.path === "/api/studio/exports")).toBe(true));
  expect(studio.calls.find((call) => call.method === "POST" && call.path === "/api/studio/exports")?.body)
    .toEqual(expect.objectContaining({ template: "countdown", format: "mp4", quality: "1080p" }));
});

it("falls back from 60 fps to 1080p once the template's fixed rate is known", async () => {
  const user = userEvent.setup();
  const studio = installFakeStudio();
  studio.catalog.templates.find((item) => item.id === "countdown")!.export_fps = 15;
  let releaseCatalog!: () => void;
  const catalogGate = new Promise<void>((resolve) => { releaseCatalog = resolve; });
  studio.reply = async (call) => call.path === "/api/studio/catalog"
    ? (await catalogGate, { status: 200, body: studio.catalog })
    : null;
  resetCatalogCache();
  render(<ExportDialog open onOpenChange={vi.fn()} request={request} transparentBackground={false} onFieldErrors={vi.fn()} />);
  await waitFor(() => expect(studio.calls.some((call) => call.path === "/api/studio/catalog")).toBe(true));
  await user.click(screen.getByRole("radio", { name: "1080p, 60 fps" }));
  expect(screen.getByRole("radio", { name: "1080p, 60 fps" })).toBeChecked();
  releaseCatalog();
  await waitFor(() => expect(screen.queryByRole("radio", { name: "1080p, 60 fps" })).not.toBeInTheDocument());
  expect(screen.getByRole("radio", { name: "1080p (Full HD)" })).toBeChecked();
});

it("keeps the 60 fps quality for templates that do not fix a rate", async () => {
  const studio = installFakeStudio();
  render(<ExportDialog open onOpenChange={vi.fn()} request={request} transparentBackground={false} onFieldErrors={vi.fn()} />);
  await waitFor(() => expect(studio.calls.some((call) => call.path === "/api/studio/catalog")).toBe(true));
  expect(screen.getByRole("radio", { name: "1080p, 60 fps" })).toBeInTheDocument();
  expect(screen.getByText("1080p · 60 fps")).toBeInTheDocument();
  expect(screen.queryByText(/frames per second/)).not.toBeInTheDocument();
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
  expect(video).toHaveAttribute("src", "/media/studio/exports/weekend-sale-a900e4.mp4#t=5.4");
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

it("seeks video thumbnails past the intro and clamps short or unknown lengths", () => {
  const { container } = renderPage([
    job({ id: "a", title: "Long sale", duration: 20, url: "/long.mp4" }),
    job({ id: "b", title: "Short sale", duration: 0.6, url: "/short.mp4" }),
    job({ id: "c", title: "Unknown length", duration: null, url: "/unknown.mp4" }),
    job({ id: "d", title: "Barely there", duration: 0.2, url: "/tiny.mp4" }),
  ]);
  const sources = [...container.querySelectorAll("video")].map((video) => video.getAttribute("src"));
  expect(sources).toEqual(["/long.mp4#t=12", "/short.mp4#t=0.5", "/unknown.mp4#t=1", "/tiny.mp4#t=0.5"]);
});

it("applies the representative frame once the video's metadata arrives", () => {
  const { container } = renderPage([job()]);
  const video = container.querySelector("video")!;
  let currentTime = 0;
  Object.defineProperty(video, "currentTime", { configurable: true, get: () => currentTime, set: (value: number) => { currentTime = value; } });
  fireEvent.loadedMetadata(video);
  expect(currentTime).toBe(5.4);
});

it("keeps Download labelled when a narrow row hides its text, and lets the meta wrap", () => {
  renderPage([job()]);
  const link = screen.getByRole("link", { name: "Download" });
  expect(link).toHaveAttribute("aria-label", "Download");
  expect(link).toHaveAttribute("title", "Download");
  expect(link).not.toHaveClass("studio-download-icon-only");
  expect(link.querySelector(".studio-download-label")).toHaveTextContent("Download");
  expect(document.querySelector(".studio-export-meta")).not.toHaveClass("truncate");
});

it("uses the icon-only Download in the editor's exports sheet and lets the meta wrap", async () => {
  const studio = installFakeStudio();
  studio.exports = [job()];
  render(<ExportsPanel open onOpenChange={vi.fn()} />);
  const link = await screen.findByRole("link", { name: "Download" });
  expect(link).toHaveClass("studio-download-icon-only");
  expect(link).toHaveAttribute("aria-label", "Download");
  expect(link).toHaveAttribute("title", "Download");
  expect(link.querySelector(".studio-download-label")).toHaveTextContent("Download");
  expect(link.closest(".studio-exports-panel")).toBeInTheDocument();
  expect(document.querySelector(".studio-export-meta")).not.toHaveClass("truncate");
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
  expect(screen.getByRole("menuitem", { name: "Remove from list" })).toBeInTheDocument();
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

const storedRequest = (): ExportRequest => ({ template: "countdown", params: { seconds: 7 }, settings: {}, format: "mp4", quality: "720p", title: "Timer" });

it("starts a failed export again from its stored request and shows the new one", async () => {
  const user = userEvent.setup();
  const studio = installFakeStudio();
  const request = storedRequest();
  studio.exports = [job({ id: "e9", title: "Broken sale", status: "failed", error: "bad", url: null, request })];
  render(<ExportsPanel open onOpenChange={vi.fn()} />);

  await user.click(await screen.findByRole("button", { name: "Try again" }));
  await waitFor(() => expect(studio.calls.some((call) => call.method === "POST" && call.path === "/api/studio/exports")).toBe(true));
  expect(studio.calls.find((call) => call.method === "POST" && call.path === "/api/studio/exports")?.body).toEqual(request);
  expect(await screen.findByText(/Waiting to start…/)).toBeInTheDocument();
  expect(screen.getByRole("progressbar", { name: "Timer progress" })).toBeInTheDocument();
});

it("hides Try again when an old record has no request", () => {
  renderPage([job({ id: "e2", title: "Broken sale", status: "failed", error: "bad", url: null })]);
  expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
});

it("gives cancelled rows a menu that removes them from the list", async () => {
  const user = userEvent.setup();
  const requests: Array<{ input: RequestInfo | URL; init?: RequestInit }> = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    requests.push({ input, init });
    return { ok: true, status: 200, headers: new Headers(), json: async () => ({}) } as unknown as Response;
  }));
  try {
    const { retry } = renderPage([job({ id: "e3", title: "Stopped sale", status: "cancelled", url: null })]);
    await user.click(screen.getByRole("button", { name: "Options for Stopped sale" }));
    await user.click(screen.getByRole("menuitem", { name: "Remove from list" }));

    await waitFor(() => expect(requests).toHaveLength(1));
    expect(String(requests[0].input)).toBe("/api/studio/exports/e3?remove=true");
    expect(requests[0].init?.method).toBe("DELETE");
    await waitFor(() => expect(screen.queryByText("Stopped sale")).not.toBeInTheDocument());
    expect(retry).toHaveBeenCalled();
  } finally {
    vi.unstubAllGlobals();
  }
});

it("offers Make again on a finished file with a stored request", async () => {
  const user = userEvent.setup();
  const studio = installFakeStudio();
  const request = storedRequest();
  studio.exports = [job({ id: "e9", request })];
  render(<ExportsPanel open onOpenChange={vi.fn()} />);

  await user.click(await screen.findByRole("button", { name: "Options for Weekend sale" }));
  await user.click(screen.getByRole("menuitem", { name: "Make again" }));
  await waitFor(() => expect(studio.calls.some((call) => call.method === "POST" && call.path === "/api/studio/exports")).toBe(true));
  expect(studio.calls.find((call) => call.method === "POST" && call.path === "/api/studio/exports")?.body).toEqual(request);
});
