import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/editor/CodeEditor", async () => {
  const { FakeCodeEditor } = await import("@/test/fakeEditor");
  return { default: FakeCodeEditor };
});

import App from "./App";
import { BROWSER_STARTER, STORAGE_KEYS } from "@/lib/storage";
import { editorCalls } from "@/test/fakeEditor";
import { DIAGNOSTICS, EXAMPLE_CODE, installFakeServer, media, type FakeServer } from "@/test/fakeServer";
import { FakeWebSocket } from "@/test/fakeSocket";

type Overrides = Parameters<typeof installFakeServer>[0];

async function renderApp(overrides?: Overrides) {
  const server = installFakeServer(overrides);
  const user = userEvent.setup();
  render(<App />);
  const editor = await screen.findByLabelText("Code editor");
  await waitFor(() => expect(screen.getByText("Connected")).toBeInTheDocument());
  return { server, user, editor: editor as HTMLTextAreaElement };
}

function renderButton() {
  return screen.getAllByRole("button", { name: "Render" })[0];
}

async function startRender(user: ReturnType<typeof userEvent.setup>) {
  await user.click(renderButton());
  const socket = FakeWebSocket.latest();
  await waitFor(() => expect(socket.sent.some((message) => message.type === "start")).toBe(true));
  const start = socket.lastSent("start");
  return { socket, start, id: start.id as string };
}

function calls(server: FakeServer, method: string, path: string) {
  return server.calls.filter((call) => call.method === method && call.path === path);
}

beforeEach(() => {
  editorCalls.length = 0;
});

describe("App", () => {
  it("loads the workspace and opens the first script", async () => {
    const { editor } = await renderApp({ media: [media("Intro")] });

    expect(editor.value).toBe(EXAMPLE_CODE);
    expect(document.title).toBe("example.py — Manim Composer");
    expect(screen.getByRole("combobox", { name: "Scene" })).toHaveTextContent("Intro");
    expect(screen.getByRole("button", { name: "notes.py" })).toBeInTheDocument();
    expect(screen.getByText("Renders · 1")).toBeInTheDocument();
    expect(screen.getByText("Balanced profile · 720p30")).toBeInTheDocument();
  });

  it("renders over the WebSocket, shows progress, and previews the result", async () => {
    const { user, server } = await renderApp();
    const { socket, start, id } = await startRender(user);

    expect(start).toMatchObject({ filename: "example.py", scene: "Intro", quality: "m", download_only: false, use_opengl: false });
    expect(start.code).toBeUndefined();
    expect(calls(server, "POST", "/api/save")).toHaveLength(0);

    act(() => socket.emit({ type: "progress", render_id: id, percent: 50, animation: 0, label: "Create(Circle())" }));
    expect(await screen.findByText("Animation 1 of 2 · Create(Circle())")).toBeInTheDocument();
    expect(document.title).toBe("25% · example.py — Manim Composer");
    expect(within(screen.getByRole("status")).getByText("25%")).toBeInTheDocument();

    act(() => {
      socket.emit({
        type: "file_ready",
        render_id: id,
        url: "/media/videos/example/720p30/Intro.mp4",
        rel_path: "media/videos/example/720p30/Intro.mp4",
        filename: "Intro.mp4",
        kind: "video",
      });
      socket.emit({ type: "result", render_id: id, success: true, status: "success" });
    });

    const video = await waitFor(() => {
      const element = document.querySelector("video");
      expect(element).not.toBeNull();
      return element!;
    });
    expect(video.getAttribute("src")).toMatch(/^\/media\/videos\/example\/720p30\/Intro\.mp4\?v=\d+$/);
    // The footer splits folder and file name (the folder truncates first); the full path is the title.
    expect(screen.getByTitle("workspace/media/videos/example/720p30/Intro.mp4")).toHaveTextContent("workspace/media/videos/example/720p30/Intro.mp4");
    expect(await screen.findByText(/Rendered Intro in/)).toBeInTheDocument();
  });

  it("saves a dirty buffer before rendering by default", async () => {
    const { user, server, editor } = await renderApp();
    fireEvent.change(editor, { target: { value: `${EXAMPLE_CODE}\n# tweak\n` } });

    const { start } = await startRender(user);
    expect(start.code).toBeUndefined();
    expect(calls(server, "POST", "/api/save")).toHaveLength(1);
    expect(server.scripts["example.py"]).toContain("# tweak");
  });

  it("renders the unsaved buffer without touching the file when saving first is off", async () => {
    localStorage.setItem(STORAGE_KEYS.autoSave, "false");
    const { user, server, editor } = await renderApp();
    fireEvent.change(editor, { target: { value: `${EXAMPLE_CODE}\n# draft\n` } });

    const { start } = await startRender(user);
    expect(start.code).toContain("# draft");
    expect(calls(server, "POST", "/api/save")).toHaveLength(0);
    expect(server.scripts["example.py"]).toBe(EXAMPLE_CODE);
  });

  it("marks the failing line, explains the error, and links it from the console", async () => {
    const { user } = await renderApp();
    const { socket, id } = await startRender(user);

    act(() => {
      socket.emit({ type: "log", render_id: id, stream: "stderr", message: "│ /work/example.py:7 in construct │" });
      socket.emit({ type: "log", render_id: id, stream: "stderr", message: "NameError: name 'x' is not defined" });
      socket.emit({ type: "status", render_id: id, status: "failed", message: "Manim exited with code 1." });
      socket.emit({ type: "result", render_id: id, success: false, status: "failed" });
    });

    expect(await screen.findByText("Intro didn't render")).toBeInTheDocument();
    expect(screen.getByText("NameError: name 'x' is not defined (line 7)")).toBeInTheDocument();
    expect(editorCalls).toContainEqual(["marker", 7, "NameError: name 'x' is not defined"]);
    expect(screen.getByText("Render failed")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Go to line 7" }));
    expect(editorCalls).toContainEqual(["reveal", 7]);
  });

  it("cancels a running render", async () => {
    const { user } = await renderApp();
    const { socket, id } = await startRender(user);

    await user.click(screen.getAllByRole("button", { name: "Cancel" })[0]);
    expect(socket.lastSent().type).toBe("cancel");

    act(() => socket.emit({ type: "result", render_id: id, success: false, status: "cancelled" }));
    expect(await screen.findByText("Render cancelled")).toBeInTheDocument();
    expect(renderButton()).toBeEnabled();
  });

  it("ignores events from a render it already abandoned", async () => {
    const { user } = await renderApp();
    const { socket, id } = await startRender(user);

    act(() => socket.emit({ type: "result", render_id: "older-render", success: false, status: "cancelled" }));
    expect(screen.getAllByRole("button", { name: "Cancel" })[0]).toBeInTheDocument();

    act(() => socket.emit({ type: "result", render_id: id, success: true, status: "success" }));
    expect(await screen.findByText(/Manim finished but produced no output file/)).toBeInTheDocument();
  });

  it("keeps unsaved edits as a draft when switching files", async () => {
    const { user, editor, server } = await renderApp();
    fireEvent.change(editor, { target: { value: "# my edits" } });

    await user.click(screen.getByRole("button", { name: "notes.py" }));
    await waitFor(() => expect(screen.getByLabelText("Code editor")).toHaveValue(server.scripts["notes.py"]));
    expect(screen.getByRole("button", { name: "example.py" }).parentElement).toContainElement(
      screen.getAllByLabelText("Unsaved changes")[0],
    );

    await user.click(screen.getByRole("button", { name: "example.py" }));
    await waitFor(() => expect(screen.getByLabelText("Code editor")).toHaveValue("# my edits"));
    expect(server.scripts["example.py"]).toBe(EXAMPLE_CODE);
  });

  it("finishes a save correctly when another file is opened while it is in flight", async () => {
    const { user, editor, server } = await renderApp();
    let release = () => {};
    server.gates["/api/save"] = new Promise<void>((resolve) => (release = resolve));

    fireEvent.change(editor, { target: { value: "# saved while switching" } });
    fireEvent.keyDown(window, { key: "s", ctrlKey: true });
    await user.click(screen.getByRole("button", { name: "notes.py" }));
    await waitFor(() => expect(screen.getByLabelText("Code editor")).toHaveValue(server.scripts["notes.py"]));

    await act(async () => release());
    await waitFor(() => expect(server.scripts["example.py"]).toBe("# saved while switching"));
    // notes.py is not dirty, keeps its own scenes, and example.py has no stale draft.
    await waitFor(() => expect(screen.queryAllByLabelText("Unsaved changes")).toHaveLength(0));
    expect(screen.getByRole("combobox", { name: "Scene" })).toHaveTextContent("Notes");

    await user.click(screen.getByRole("button", { name: "example.py" }));
    await waitFor(() => expect(screen.getByLabelText("Code editor")).toHaveValue("# saved while switching"));
    expect(screen.queryAllByLabelText("Unsaved changes")).toHaveLength(0);
  });

  it("creates a script from the New script dialog with inline validation", async () => {
    const { user, server } = await renderApp();
    await user.click(screen.getByRole("button", { name: "New script" }));

    const input = await screen.findByLabelText("File name");
    await user.clear(input);
    await user.type(input, "notes");
    await user.click(screen.getByRole("button", { name: "Create" }));
    expect(await screen.findByText("notes.py already exists.")).toBeInTheDocument();

    await user.clear(input);
    await user.type(input, "orbit");
    expect(screen.getByText("Will be saved as orbit.py")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => expect(server.scripts["orbit.py"]).toContain("class Orbit(Scene):"));
    await waitFor(() => expect(screen.getByLabelText("Code editor")).toHaveValue(server.scripts["orbit.py"]));
  });

  it("renames a script inline and keeps the open buffer", async () => {
    const { user, editor, server } = await renderApp();
    fireEvent.change(editor, { target: { value: "# unsaved" } });

    await user.click(screen.getByRole("button", { name: "Rename example.py" }));
    // The name stem is preselected, so typing replaces it.
    expect(screen.getByLabelText("New file name")).toHaveFocus();
    await user.keyboard("intro{Enter}");

    await waitFor(() => expect(server.scripts["intro.py"]).toBe(EXAMPLE_CODE));
    expect(screen.getByLabelText("Code editor")).toHaveValue("# unsaved");
    expect(screen.getByRole("button", { name: "intro.py" })).toBeInTheDocument();
  });

  it("deletes a script after confirmation", async () => {
    const { user, server } = await renderApp();
    await user.click(screen.getByRole("button", { name: "Delete notes.py" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Delete notes.py?")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(server.scripts).not.toHaveProperty("notes.py"));
    await waitFor(() => expect(screen.queryByRole("button", { name: "notes.py" })).not.toBeInTheDocument());
  });

  it("deletes a render after confirmation and lets you preview renders", async () => {
    const { user, server } = await renderApp({ media: [media("Intro"), media("Outro")] });

    await user.click(screen.getByRole("button", { name: /^Intro/ }));
    expect(document.querySelector("video")?.getAttribute("src")).toContain("/media/videos/example/720p30/Intro.mp4");

    await user.click(screen.getByRole("button", { name: "Delete render Intro.mp4" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(server.media.map((item) => item.scene)).toEqual(["Outro"]));
    await waitFor(() => expect(document.querySelector("video")).toBeNull());
  });

  it("keeps scripts in the browser in browser storage mode", async () => {
    localStorage.setItem("manim_composer_storage_location", "browser");
    const { user, server, editor } = await renderApp();

    expect(editor.value).toBe(BROWSER_STARTER);
    expect(screen.getByText(/Scripts are saved in this browser only/)).toBeInTheDocument();
    expect(screen.getByText("Browser storage")).toBeInTheDocument();

    fireEvent.change(editor, { target: { value: `${BROWSER_STARTER}# local\n` } });
    const { start } = await startRender(user);
    expect(start.filename).toBe("my_scene.py");
    expect(start.code).toContain("# local");
    expect(calls(server, "GET", "/api/file-content")).toHaveLength(0);

    fireEvent.keyDown(window, { key: "s", ctrlKey: true });
    await waitFor(() => expect(JSON.parse(localStorage.getItem(STORAGE_KEYS.browserFiles)!)["my_scene.py"]).toContain("# local"));
  });

  it("saves with Ctrl+S", async () => {
    const { server, editor } = await renderApp();
    fireEvent.change(editor, { target: { value: "# saved by shortcut" } });
    expect(document.title).toBe("● example.py — Manim Composer");
    fireEvent.keyDown(window, { key: "s", ctrlKey: true });
    await waitFor(() => expect(server.scripts["example.py"]).toBe("# saved by shortcut"));
  });

  it("downloads renders in download-only mode", async () => {
    localStorage.setItem(STORAGE_KEYS.downloadOnly, "true");
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const { user, server } = await renderApp();
    const { socket, start, id } = await startRender(user);
    expect(start.download_only).toBe(true);

    act(() =>
      socket.emit({
        type: "file_ready",
        render_id: id,
        url: "/api/download-temp?path=videos%2F_temp_run_1%2FIntro.mp4",
        rel_path: "api/download-temp?path=videos%2F_temp_run_1%2FIntro.mp4",
        filename: "Intro.mp4",
        kind: "video",
        is_temp_download: true,
      }),
    );

    expect(await screen.findByText("Downloaded · not kept on the server")).toBeInTheDocument();
    expect(calls(server, "GET", "/api/download-temp")).toHaveLength(1);
    expect(click).toHaveBeenCalled();
  });

  it("shows the timeline and jumps to a step's line", async () => {
    const { user } = await renderApp();
    // jsdom has no layout, so the resizable panels treat every pointerdown as a
    // separator drag and cancel it; Radix tabs activate on mousedown.
    fireEvent.mouseDown(screen.getByRole("tab", { name: /Timeline/ }), { button: 0 });
    const timeline = screen.getByRole("tabpanel");
    expect(within(timeline).getByText(/2 steps · ≈ 3s/)).toBeInTheDocument();
    const step = within(timeline).getByTitle("Line 6: self.play(Create(Circle()))");
    await user.click(step);
    expect(editorCalls).toContainEqual(["reveal", 6]);
    expect(screen.getByTitle("Line 7: Wait 2s")).toBeInTheDocument();
  });

  it("starts a new file from a template", async () => {
    const { user, server } = await renderApp();
    await user.click(screen.getByRole("button", { name: "Templates" }));
    const card = screen.getByText("Function Plot").closest("li")!;
    await user.click(within(card).getByRole("button", { name: "New file" }));

    expect(await screen.findByLabelText("File name")).toHaveValue("function_plot.py");
    await user.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => expect(server.scripts["function_plot.py"]).toContain("class FunctionPlot(Scene)"));
  });

  it("replaces the buffer with a template after confirming", async () => {
    const { user } = await renderApp();
    await user.click(screen.getByRole("button", { name: "Templates" }));
    const card = screen.getByText("Square to Circle").closest("li")!;
    await user.click(within(card).getByRole("button", { name: "Replace current" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Replace" }));
    await waitFor(() => expect((screen.getByLabelText("Code editor") as HTMLTextAreaElement).value).toContain("class SquareToCircle"));
  });

  it("inserts code from the shape builder", async () => {
    const { user } = await renderApp();
    await user.click(screen.getByRole("button", { name: "Shape builder" }));
    await user.click(screen.getByRole("radio", { name: "PINK" }));
    expect(screen.getByLabelText("Generated code")).toHaveTextContent("Circle(radius=1, color=PINK)");
    await user.click(screen.getByRole("button", { name: "Insert into scene" }));
    expect(editorCalls).toContainEqual(["insert", expect.stringContaining("color=PINK"), "block"]);
  });

  it("previews LaTeX and inserts MathTex", async () => {
    const { user } = await renderApp();
    await user.click(screen.getByRole("button", { name: "LaTeX" }));
    const input = await screen.findByLabelText("LaTeX formula");
    fireEvent.change(input, { target: { value: "\\frac{1}{2}" } });
    expect(screen.getByLabelText("Formula preview").querySelector(".katex")).not.toBeNull();

    fireEvent.change(input, { target: { value: "\\frac{1" } });
    expect(screen.getByLabelText("Formula preview")).toHaveTextContent(/missing closing brace/i);

    fireEvent.change(input, { target: { value: "a^2" } });
    // KaTeX's MathML output trips jsdom's accessible-name computation, so avoid role queries here.
    await user.click(screen.getByText("Insert MathTex"));
    expect(editorCalls).toContainEqual(["insert", 'tex = MathTex(r"a^2")\nself.play(Write(tex))', "block"]);
  });

  it("uploads assets, rejects unsupported types, and inserts usage code", async () => {
    const { user, server } = await renderApp();
    await user.click(screen.getByRole("button", { name: "Assets" }));
    const input = screen.getByLabelText("Upload assets");

    // The file picker filters by type; drag-and-drop does not, so the app validates too.
    await userEvent.setup({ applyAccept: false }).upload(input, new File(["x"], "virus.exe"));
    expect(await screen.findByText(/virus\.exe: unsupported type/)).toBeInTheDocument();

    await user.upload(input, new File(["<svg/>"], "logo.svg", { type: "image/svg+xml" }));
    await waitFor(() => expect(server.assets.map((asset) => asset.name)).toEqual(["logo.svg"]));
    await user.click(await screen.findByRole("button", { name: "Insert logo.svg" }));
    expect(editorCalls).toContainEqual(["insert", 'logo = SVGMobject("assets/logo.svg")\nself.play(FadeIn(logo))', "block"]);
  });

  it("opens setup when Manim is missing and starts installers", async () => {
    const diagnostics = structuredClone(DIAGNOSTICS);
    diagnostics.platform = "Windows";
    diagnostics.dependencies.manim = "Not Found";
    diagnostics.dependencies.latex_available = false;
    diagnostics.dependencies.latex = "Not Found";
    const { user, server } = await renderApp({ diagnostics });

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Set up your machine")).toBeInTheDocument();
    expect(within(dialog).getByText("winget install MiKTeX.MiKTeX")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Install with pip" }));
    expect(calls(server, "POST", "/api/install-manim")).toHaveLength(1);
    expect(await screen.findByText("Installer started.")).toBeInTheDocument();
    expect(within(dialog).getByText("Installing…")).toBeInTheDocument();
    expect(screen.getByText("LaTeX not installed")).toBeInTheDocument();
  });

  it("shows platform-specific install commands outside Windows", async () => {
    const { user } = await renderApp();
    await user.click(screen.getByRole("button", { name: "Setup" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getAllByText("Installed")).toHaveLength(3);

    await user.click(within(dialog).getByRole("button", { name: "Done" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("reports an offline backend and recovers when it comes back", async () => {
    const server = installFakeServer();
    server.offline = true;
    FakeWebSocket.autoOpen = false;
    render(<App />);

    expect(await screen.findByText("Server offline — retrying")).toBeInTheDocument();
    expect(await screen.findByText("Couldn't load scripts")).toBeInTheDocument();
    expect(renderButton()).toBeDisabled();

    server.offline = false;
    FakeWebSocket.autoOpen = true;
    act(() => FakeWebSocket.instances.forEach((socket) => socket.open()));
    await waitFor(() => expect(screen.getByText("Connected")).toBeInTheDocument(), { timeout: 6000 });
    expect(await screen.findByLabelText("Code editor")).toHaveValue(EXAMPLE_CODE);
  });

  it("re-renders automatically after typing pauses when auto-render is on", async () => {
    const { user, editor } = await renderApp();
    await user.click(screen.getByRole("button", { name: "Auto-render" }));
    expect(screen.getByRole("button", { name: "Auto-render" })).toHaveAttribute("aria-pressed", "true");

    fireEvent.change(editor, { target: { value: `${EXAMPLE_CODE}\n# changed\n` } });
    const socket = FakeWebSocket.latest();
    await waitFor(() => expect(socket.sent.some((message) => message.type === "start")).toBe(true), { timeout: 4000 });
  });

  it("changes settings and remembers them", async () => {
    const { user } = await renderApp();
    await user.click(screen.getByRole("button", { name: "Settings" }));
    await user.click(screen.getByRole("switch", { name: "Download-only mode" }));
    expect(localStorage.getItem(STORAGE_KEYS.downloadOnly)).toBe("true");

    await user.click(screen.getByRole("radio", { name: "Browser" }));
    expect(localStorage.getItem(STORAGE_KEYS.storageMode)).toBe('"browser"');
    await waitFor(() => expect(screen.getByLabelText("Code editor")).toHaveValue(BROWSER_STARTER));
  });

  it("shows hardware and dependency details in the System view", async () => {
    const { user } = await renderApp();
    await user.click(screen.getByRole("button", { name: "System" }));
    expect(screen.getByText("Test CPU 9000")).toBeInTheDocument();
    expect(screen.getByText("4 cores · 8 threads")).toBeInTheDocument();
    expect(screen.getByText("Linux · Python 3.12.1")).toBeInTheDocument();
    expect(screen.getByText("/usr/bin/manim")).toBeInTheDocument();
  });
});
