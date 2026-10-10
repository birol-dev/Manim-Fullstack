// Fixes for gaps found by the browser verification of PR #19 (R4): the scene picker on a
// browser file switch, disk renders leaking into browser-storage files (banner, console,
// preview), focus after New script from the empty Scripts list, and the Renders label
// after a rename mid-render.
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/editor/CodeEditor", async () => {
  const { FakeCodeEditor } = await import("@/test/fakeEditor");
  return { default: FakeCodeEditor };
});

import App from "./App";
import { installFakeServer, media } from "@/test/fakeServer";
import { FakeWebSocket } from "@/test/fakeSocket";
import { BROWSER_STARTER, STORAGE_KEYS, writeBrowserFile } from "@/lib/storage";

type Overrides = Parameters<typeof installFakeServer>[0];

async function renderApp(overrides?: Overrides, { waitForEditor = true } = {}) {
  const server = installFakeServer(overrides);
  const user = userEvent.setup();
  const view = render(<App />);
  if (waitForEditor) await screen.findByLabelText("Code editor");
  await waitFor(() => expect(screen.getByText("Connected")).toBeInTheDocument());
  return { server, user, view };
}

const editorSection = () => screen.getByRole("region", { name: "Editor" });
const codeEditor = () => screen.getByLabelText("Code editor") as HTMLTextAreaElement;

async function startRender(user: ReturnType<typeof userEvent.setup>) {
  await user.click(within(editorSection()).getByRole("button", { name: "Render" }));
  const socket = FakeWebSocket.latest();
  await waitFor(() => expect(socket.sent.some((message) => message.type === "start")).toBe(true));
  return { socket, id: socket.lastSent("start").id as string };
}

function finishWithVideo(socket: FakeWebSocket, id: string, stem: string, scene: string) {
  act(() => {
    socket.emit({
      type: "file_ready",
      render_id: id,
      url: `/media/videos/${stem}/720p30/${scene}.mp4`,
      rel_path: `media/videos/${stem}/720p30/${scene}.mp4`,
      filename: `${scene}.mp4`,
      kind: "video",
    });
    socket.emit({ type: "result", render_id: id, success: true, status: "success" });
  });
}

async function switchStorage(user: ReturnType<typeof userEvent.setup>, mode: "Browser" | "Workspace folder") {
  await user.click(screen.getByRole("button", { name: "Settings" }));
  await user.click(screen.getByRole("radio", { name: mode === "Browser" ? "Browser" : /Workspace/ }));
  await user.click(screen.getByRole("button", { name: "Files" }));
}

const myScene = (path = "videos/my_scene/720p30/MyScene.mp4") =>
  media("MyScene", { path, url: `/media/${path}`, script: "my_scene" });

describe("gap 1: the scene picker switches with the file", () => {
  it("never shows one browser file's scene while another file is open", async () => {
    localStorage.setItem(STORAGE_KEYS.storageMode, JSON.stringify("browser"));
    const code = (scene: string) => `from manim import *\n\nclass ${scene}(Scene):\n    def construct(self):\n        self.wait()\n`;
    writeBrowserFile("fa.py", code("Fa"));
    writeBrowserFile("fb.py", code("Fb"));
    localStorage.setItem("mc.browserSeeded", "true");
    const { user } = await renderApp();
    await waitFor(() => expect(screen.getByRole("combobox", { name: "Scene" })).toHaveTextContent(/^F[ab]$/));

    // Every DOM state on the way: the picker names only the open file's scene (or nothing yet).
    const seen: string[] = [];
    const check = () => {
      const file = document.querySelector('[aria-label="Code editor"]')?.getAttribute("data-path") ?? "";
      const scene = document.querySelector('[aria-label="Scene"]')?.textContent ?? "";
      seen.push(`${file}|${scene}`);
    };
    const observer = new MutationObserver(check);
    observer.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true });
    for (const target of ["fb.py", "fa.py", "fb.py", "fa.py"]) {
      if (codeEditor().getAttribute("data-path") === `browser/${target}`) continue;
      await user.click(within(screen.getByRole("list", { name: "Scripts" })).getByRole("button", { name: target }));
      await waitFor(() => expect(codeEditor()).toHaveAttribute("data-path", `browser/${target}`));
      await waitFor(() => expect(screen.getByRole("combobox", { name: "Scene" })).toHaveTextContent(target === "fa.py" ? "Fa" : "Fb"));
    }
    observer.disconnect();
    const mismatched = seen.filter((state) => /fa\.py\|Fb|fb\.py\|Fa/.test(state));
    expect(mismatched).toEqual([]);
  });
});

describe("gap 2: a workspace render stays out of the browser-storage file of the same name", () => {
  it("shows none of its banner, Cancel, console, or video on browser my_scene.py, even with no script left", async () => {
    const { user, server } = await renderApp({ scripts: { "my_scene.py": BROWSER_STARTER } });
    const { socket, id } = await startRender(user);
    act(() => {
      socket.emit({ type: "log", render_id: id, stream: "stdout", message: "DISK RENDER LOG LINE" });
      socket.emit({ type: "progress", render_id: id, percent: 40 });
    });
    expect(await screen.findByText("DISK RENDER LOG LINE")).toBeInTheDocument();

    await switchStorage(user, "Browser");
    await waitFor(() => expect(codeEditor()).toHaveAttribute("data-path", "browser/my_scene.py"));
    // No Cancel strip (toolbar, overlay, or banner) and none of its console output here.
    expect(screen.queryAllByRole("button", { name: "Cancel" })).toEqual([]);
    expect(screen.queryByTestId("other-render")).not.toBeInTheDocument();
    expect(screen.queryByText("DISK RENDER LOG LINE")).not.toBeInTheDocument();
    // Render still says why it can't run.
    expect(document.getElementById("render-blocked-reason")).toHaveTextContent("(in the workspace folder)");

    // Its output lands in the shared media/videos/my_scene folder: still not this file's preview.
    server.media = [myScene()];
    finishWithVideo(socket, id, "my_scene", "MyScene");
    expect(await screen.findByText("MyScene rendered")).toBeInTheDocument();
    await waitFor(() => expect(within(screen.getByRole("list", { name: "Renders" })).getByText("MyScene")).toBeInTheDocument());
    expect(document.querySelector("video")).toBeNull();

    // Deleting every browser script leaves nothing behind in the preview.
    await user.click(screen.getByRole("button", { name: "Delete my_scene.py" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete" }));
    expect(await screen.findByText("No scripts in this browser")).toBeInTheDocument();
    expect(document.querySelector("video")).toBeNull();

    // Back in the workspace folder, the render and its console are that file's again.
    await switchStorage(user, "Workspace folder");
    await waitFor(() => expect(codeEditor()).toHaveAttribute("data-path", "disk/my_scene.py"));
    await waitFor(() => expect(document.querySelector("video")?.getAttribute("src")).toMatch(/my_scene\/720p30\/MyScene\.mp4/));
    expect(screen.getByText("DISK RENDER LOG LINE")).toBeInTheDocument();
  });

  it("doesn't fall back to an earlier workspace render for a browser file of the same name", async () => {
    localStorage.setItem(STORAGE_KEYS.storageMode, JSON.stringify("browser"));
    await renderApp({ scripts: { "my_scene.py": BROWSER_STARTER }, media: [myScene()] });
    await waitFor(() => expect(codeEditor()).toHaveAttribute("data-path", "browser/my_scene.py"));
    await waitFor(() => expect(within(screen.getByRole("list", { name: "Renders" })).getByText("MyScene")).toBeInTheDocument());
    expect(document.querySelector("video")).toBeNull();
    expect(screen.getByText("Nothing rendered yet")).toBeInTheDocument();
  });

  it("does show a browser file's own render after a reload", async () => {
    localStorage.setItem(STORAGE_KEYS.storageMode, JSON.stringify("browser"));
    const { user, server, view } = await renderApp({ scripts: {} });
    await waitFor(() => expect(codeEditor()).toHaveAttribute("data-path", "browser/my_scene.py"));
    const { socket, id } = await startRender(user);
    server.media = [myScene()];
    finishWithVideo(socket, id, "my_scene", "MyScene");
    await waitFor(() => expect(document.querySelector("video")).not.toBeNull());

    view.unmount();
    render(<App />);
    await waitFor(() => expect(screen.getByLabelText("Code editor")).toHaveAttribute("data-path", "browser/my_scene.py"));
    await waitFor(() => expect(document.querySelector("video")?.getAttribute("src")).toMatch(/MyScene\.mp4/));
  });
});

describe("gap 3: focus reaches the editor after New script from the empty Scripts list", () => {
  it("lands in the editor once it mounts for the first file, so typing goes into the new script", async () => {
    localStorage.setItem(STORAGE_KEYS.storageMode, JSON.stringify("browser"));
    localStorage.setItem("mc.browserSeeded", "true");
    const { user } = await renderApp({}, { waitForEditor: false });
    expect(await screen.findByText("No scripts in this browser")).toBeInTheDocument();
    expect(screen.queryByLabelText("Code editor")).not.toBeInTheDocument();

    // (Keyboard: in jsdom a click lands focus on a resize handle, since every element sits at 0,0.)
    act(() => within(editorSection()).getByRole("button", { name: "New script" }).focus());
    await user.keyboard("{Enter}");
    const input = await screen.findByLabelText("File name");
    await user.clear(input);
    await user.type(input, "fa{Enter}");
    await waitFor(() => expect(screen.getByLabelText("Code editor")).toHaveAttribute("data-path", "browser/fa.py"));
    await waitFor(() => expect(screen.getByLabelText("Code editor")).toHaveFocus());
    await user.keyboard("# typed right away");
    expect(codeEditor().value).toContain("# typed right away");
  });
});

describe("gap 4: the Renders list names the script as it is now called", () => {
  it("labels a render renamed mid-render with the new name", async () => {
    const { user, server } = await renderApp();
    const { socket, id } = await startRender(user);
    await user.click(screen.getByRole("button", { name: "Rename example.py" }));
    await user.keyboard("{Control>}a{/Control}renamed{Enter}");
    await waitFor(() => expect(codeEditor()).toHaveAttribute("data-path", "disk/renamed.py"));

    // The server wrote it under the name the render started with (media/videos/example/...).
    server.media = [media("Intro", { modified: Date.now() / 1000 })];
    finishWithVideo(socket, id, "example", "Intro");
    const renders = await screen.findByRole("list", { name: "Renders" });
    await waitFor(() => expect(within(renders).getByText("renamed.py")).toBeInTheDocument());
    expect(within(renders).queryByText("example.py")).not.toBeInTheDocument();
  });

  it("keeps the preview and relabels the render when the file is renamed right after it rendered", async () => {
    const { user, server } = await renderApp();
    const { socket, id } = await startRender(user);
    server.media = [media("Intro", { modified: Date.now() / 1000 })];
    finishWithVideo(socket, id, "example", "Intro");
    await waitFor(() => expect(document.querySelector("video")?.getAttribute("src")).toMatch(/example\/720p30\/Intro\.mp4/));

    await user.click(screen.getByRole("button", { name: "Rename example.py" }));
    await user.keyboard("{Control>}a{/Control}after{Enter}");
    await waitFor(() => expect(codeEditor()).toHaveAttribute("data-path", "disk/after.py"));
    await waitFor(() => expect(within(screen.getByRole("list", { name: "Renders" })).getByText("after.py")).toBeInTheDocument());
    expect(document.querySelector("video")?.getAttribute("src")).toMatch(/example\/720p30\/Intro\.mp4/);
    expect(screen.queryByText("Nothing rendered yet")).not.toBeInTheDocument();
  });
});
