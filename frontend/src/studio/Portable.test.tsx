/** Save a video as one file, and open one from Your videos (picker and drop). */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Toaster } from "sonner";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";

import { EditorPage } from "./Editor";
import { Gallery } from "./Gallery";
import { posterQueue } from "./hooks";
import { resetPreferencesForTests } from "./preferences";
import { installFakeStudio, type FakeStudio } from "./test/fakeStudio";
import type { Project } from "./types";

let studio: FakeStudio;

const PROJECT: Project = {
  id: "p1",
  title: "School video",
  template: "countdown",
  params: { seconds: 300, title: "Quiet reading time", style: "ring" },
  settings: { aspect: "16:9", theme: "clean" },
  revision: 1,
  created: 1,
  updated: 1,
};

beforeEach(() => {
  posterQueue.clear();
  resetPreferencesForTests();
  localStorage.clear();
  window.history.replaceState(null, "", "/");
  studio = installFakeStudio();
  studio.projects = [structuredClone(PROJECT)];
});

function editor() {
  return render(
    <TooltipProvider>
      <EditorPage catalog={studio.catalog} route={{ kind: "project", id: PROJECT.id }} onProjectCreated={() => {}} />
      <Toaster />
    </TooltipProvider>,
  );
}

function videos() {
  return render(<>
    <Gallery catalog={studio.catalog} route={{ kind: "videos" }}
      library={{ projects: [], error: null, retry: vi.fn(), revision: 0, remove: vi.fn(), rename: vi.fn(), duplicate: vi.fn() } as never}
      exports={{ jobs: [], error: null, cancel: vi.fn(), retry: vi.fn() } as never} />
    <Toaster />
  </>);
}

function portableFile(name = "trip.manimstudio", bytes = [80, 75, 3, 4]) {
  return new File([new Uint8Array(bytes)], name, { type: "application/zip" });
}

async function openThroughPicker(file: File) {
  fireEvent.change(screen.getByLabelText("Open a Manim Studio file"), { target: { files: [file] } });
}

function opened(notes: string[] = []) {
  return { status: 201, body: { project: { ...PROJECT, id: "p9", title: "School video" }, notes } };
}

describe("save as a file", () => {
  it("saves the current editor state, then uses the export download link and shows a quiet note", async () => {
    studio.reply = (call) => call.method === "GET" && call.path === `/api/studio/projects/${PROJECT.id}/file/info`
      ? { status: 200, body: { filename: "school-video.manimstudio", notes: ["Saved, but this file wasn't on this computer: photo.png."] } }
      : null;
    const user = userEvent.setup();
    editor();
    await screen.findByRole("textbox", { name: "Video title" });

    let href = "";
    let filename = "";
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      href = this.getAttribute("href") ?? "";
      filename = this.download;
    });
    await user.click(screen.getByRole("button", { name: "Options for School video" }));
    await user.click(screen.getByRole("menuitem", { name: "Save as a file" }));

    await waitFor(() => expect(click).toHaveBeenCalled());
    expect(href).toBe(`/api/studio/projects/${PROJECT.id}/file`);
    expect(filename).toBe("school-video.manimstudio");
    expect(studio.calls.some((call) => call.method === "PUT" && call.path === `/api/studio/projects/${PROJECT.id}`)).toBe(true);
    expect(await screen.findByText(/photo\.png/)).toBeInTheDocument();
  });

  it("keeps a save failure in a plain sentence", async () => {
    studio.reply = (call) => call.method === "GET" && call.path === `/api/studio/projects/${PROJECT.id}/file/info`
      ? { status: 500, body: { detail: "Couldn't make that file. Try again." } }
      : null;
    const user = userEvent.setup();
    editor();
    await screen.findByRole("textbox", { name: "Video title" });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    await user.click(screen.getByRole("button", { name: "Options for School video" }));
    await user.click(screen.getByRole("menuitem", { name: "Save as a file" }));

    expect(await screen.findByText("Couldn't make that file. Try again.")).toBeInTheDocument();
    expect(click).not.toHaveBeenCalled();
  });
});

describe("open a file", () => {
  it("opens from the pill, shows the replaced-asset note once and goes to the new video", async () => {
    studio.reply = (call) => call.method === "POST" && call.path === "/api/studio/projects/open"
      ? opened(["One file couldn't be used, so the design's default is in its place: photo.png."])
      : null;
    videos();
    await openThroughPicker(portableFile());

    await waitFor(() => expect(window.location.hash).toBe("#/project/p9"));
    const post = studio.calls.find((call) => call.method === "POST" && call.path === "/api/studio/projects/open");
    expect(post?.body).toMatchObject({ filename: "trip.manimstudio" });
    expect((post?.body as { data?: string }).data?.length).toBeGreaterThan(0);
    expect(await screen.findByText(/photo\.png/)).toBeInTheDocument();
  });

  it("opens a file dropped on Your videos", async () => {
    studio.reply = (call) => call.method === "POST" && call.path === "/api/studio/projects/open" ? opened() : null;
    videos();
    const page = screen.getByRole("region", { name: "Video library" });
    fireEvent.dragOver(page, { dataTransfer: { types: ["Files"] } });
    expect(screen.getByText("Drop the file to open it")).toBeInTheDocument();
    fireEvent.drop(page, { dataTransfer: { files: [portableFile("dropped.manimstudio")] } });

    await waitFor(() => expect(window.location.hash).toBe("#/project/p9"));
    expect(studio.calls.some((call) => call.method === "POST" && call.path === "/api/studio/projects/open")).toBe(true);
  });

  it("keeps a refusal on the page, in plain words", async () => {
    studio.reply = (call) => call.method === "POST" && call.path === "/api/studio/projects/open"
      ? { status: 422, body: { detail: "This video uses a design this app doesn't have yet. Update the app, then open it again." } }
      : null;
    videos();
    await openThroughPicker(portableFile());

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This video uses a design this app doesn't have yet. Update the app, then open it again.",
    );
    expect(window.location.hash).toBe("");
  });

  it("refuses a file that is not a Manim Studio file before sending anything", async () => {
    videos();
    await openThroughPicker(portableFile("holiday.png"));

    expect(await screen.findByRole("alert")).toHaveTextContent("Choose a Manim Studio file");
    expect(studio.calls.some((call) => call.path === "/api/studio/projects/open")).toBe(false);
  });
});
