// Fix round 1: save conflicts, preview binding, cancel states, still images,
// toasts, console links, and keyboard navigation.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { vi } from "vitest";

vi.mock("@/components/editor/CodeEditor", async () => {
  const { FakeCodeEditor } = await import("@/test/fakeEditor");
  return { default: FakeCodeEditor };
});

import App from "./App";
import { editorCalls } from "@/test/fakeEditor";
import { EXAMPLE_CODE, installFakeServer, media, type FakeServer } from "@/test/fakeServer";
import { FakeWebSocket } from "@/test/fakeSocket";
import { validateScriptName } from "@/lib/format";
import { QUEUED_CANCEL_FALLBACK_MS } from "@/hooks/useRenderSession";
import { STOPPING_MIN_DISPLAY_MS } from "@/hooks/useMinimumStopping";

type Overrides = Parameters<typeof installFakeServer>[0];

async function renderApp(overrides?: Overrides) {
  const server = installFakeServer(overrides);
  const user = userEvent.setup();
  render(<App />);
  const editor = await screen.findByLabelText("Code editor");
  await waitFor(() => expect(screen.getByText("Connected")).toBeInTheDocument());
  return { server, user, editor: editor as HTMLTextAreaElement };
}

async function startRender(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getAllByRole("button", { name: "Render" })[0]);
  const socket = FakeWebSocket.latest();
  await waitFor(() => expect(socket.sent.some((message) => message.type === "start")).toBe(true));
  const start = socket.lastSent("start");
  return { socket, start, id: start.id as string };
}

function calls(server: FakeServer, method: string, path: string) {
  return server.calls.filter((call) => call.method === method && call.path === path);
}

/**
 * Console lines are batched and rendered on the next animation frame (useLogs),
 * a frame after the state that ends a render. Wait for the line, then let one
 * more frame flush so a duplicate queued behind it would be caught too.
 */
async function expectLogLineOnce(text: string) {
  await waitFor(() => expect(within(screen.getByRole("log")).getAllByText(text)).toHaveLength(1));
  await act(() => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())));
  expect(within(screen.getByRole("log")).getAllByText(text)).toHaveLength(1);
}

function previewVideo() {
  return document.querySelector("section[aria-label='Preview'] video");
}

const notesRender = media("Notes", { script: "notes", path: "videos/notes/720p30/Notes.mp4", url: "/media/videos/notes/720p30/Notes.mp4" });

afterEach(() => {
  // A test that fails while timers are faked must not leak them into the next one.
  vi.useRealTimers();
});

beforeEach(() => {
  editorCalls.length = 0;
});

describe("save conflicts between tabs", () => {
  it("sends the loaded version and asks before overwriting a file changed elsewhere", async () => {
    const { server, editor, user } = await renderApp();
    server.scripts["example.py"] = "# saved in another tab\n";
    fireEvent.change(editor, { target: { value: "# mine" } });
    fireEvent.keyDown(window, { key: "s", ctrlKey: true });

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("example.py changed in another tab")).toBeInTheDocument();
    expect(server.scripts["example.py"]).toBe("# saved in another tab\n");
    expect(calls(server, "POST", "/api/save")[0].body).toMatchObject({ base_version: expect.any(String) });

    await user.click(within(dialog).getByRole("button", { name: "Overwrite" }));
    await waitFor(() => expect(server.scripts["example.py"]).toBe("# mine"));
    await waitFor(() => expect(screen.queryAllByLabelText("Unsaved changes")).toHaveLength(0));

    // The next save is based on the version just written: no prompt.
    fireEvent.change(screen.getByLabelText("Code editor"), { target: { value: "# mine again" } });
    fireEvent.keyDown(window, { key: "s", ctrlKey: true });
    await waitFor(() => expect(server.scripts["example.py"]).toBe("# mine again"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("reloads the other tab's version on request, and Cancel writes nothing", async () => {
    const { server, editor, user } = await renderApp();
    server.scripts["example.py"] = "# theirs\n";
    fireEvent.change(editor, { target: { value: "# mine" } });

    fireEvent.keyDown(window, { key: "s", ctrlKey: true });
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(server.scripts["example.py"]).toBe("# theirs\n");
    expect(screen.getByLabelText("Code editor")).toHaveValue("# mine");

    fireEvent.keyDown(window, { key: "s", ctrlKey: true });
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Reload theirs" }));
    await waitFor(() => expect(screen.getByLabelText("Code editor")).toHaveValue("# theirs\n"));
    expect(server.scripts["example.py"]).toBe("# theirs\n");
    await waitFor(() => expect(screen.queryAllByLabelText("Unsaved changes")).toHaveLength(0));
  });

  it("doesn't recreate a file deleted or renamed elsewhere unless asked", async () => {
    const { server, editor, user } = await renderApp();
    delete server.scripts["example.py"];
    fireEvent.change(editor, { target: { value: "# keep me" } });
    fireEvent.keyDown(window, { key: "s", ctrlKey: true });

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("example.py no longer exists")).toBeInTheDocument();
    expect(server.scripts).not.toHaveProperty("example.py");

    await user.click(within(dialog).getByRole("button", { name: "Recreate file" }));
    await waitFor(() => expect(server.scripts["example.py"]).toBe("# keep me"));
  });

  it("asks instead of rendering when saving before a render hits a conflict", async () => {
    const { server, editor, user } = await renderApp();
    server.scripts["example.py"] = "# theirs\n";
    fireEvent.change(editor, { target: { value: `${EXAMPLE_CODE}# mine\n` } });
    await user.click(screen.getAllByRole("button", { name: "Render" })[0]);
    expect(await screen.findByText("example.py changed in another tab")).toBeInTheDocument();
    expect(FakeWebSocket.latest().sent.some((message) => message.type === "start")).toBe(false);
  });

  it("reloads a clean buffer when the tab regains focus, and warns when there are edits", async () => {
    const { server, editor } = await renderApp();
    server.scripts["example.py"] = "# changed elsewhere\n";
    act(() => void window.dispatchEvent(new Event("focus")));
    await waitFor(() => expect(screen.getByLabelText("Code editor")).toHaveValue("# changed elsewhere\n"));
    expect(await screen.findByText("Reloaded example.py")).toBeInTheDocument();

    fireEvent.change(editor, { target: { value: "# my edit" } });
    server.scripts["example.py"] = "# changed again\n";
    act(() => void window.dispatchEvent(new Event("focus")));
    expect(await screen.findByText("example.py changed in another tab")).toBeInTheDocument();
    expect(screen.getByLabelText("Code editor")).toHaveValue("# my edit");

    delete server.scripts["example.py"];
    act(() => void window.dispatchEvent(new Event("focus")));
    expect(await screen.findByText("example.py was renamed or deleted elsewhere")).toBeInTheDocument();
    expect(screen.getByLabelText("Code editor")).toHaveValue("# my edit");
  });
});

describe("preview follows the open file and job", () => {
  it("restores the open scene's last render after a reload and follows file switches", async () => {
    const { user } = await renderApp({ media: [media("Intro"), notesRender] });
    await waitFor(() => expect(previewVideo()?.getAttribute("src")).toContain("/example/720p30/Intro.mp4"));
    expect(screen.queryByText("Nothing rendered yet")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "notes.py" }));
    await waitFor(() => expect(previewVideo()?.getAttribute("src")).toContain("/notes/720p30/Notes.mp4"));
  });

  it("shows the running job in the header and hides Download/Open for the old clip", async () => {
    const { user } = await renderApp({ media: [media("Intro")] });
    await waitFor(() => expect(previewVideo()).not.toBeNull());
    const header = () => within(screen.getByRole("region", { name: "Preview" }));
    expect(header().getByRole("button", { name: "Download" })).toBeInTheDocument();

    const { socket, id } = await startRender(user);
    expect(header().getByText("Intro · rendering")).toBeInTheDocument();
    expect(header().queryByRole("button", { name: "Download" })).not.toBeInTheDocument();
    expect(header().queryByRole("button", { name: "Open in new tab" })).not.toBeInTheDocument();

    act(() => socket.emit({ type: "result", render_id: id, success: false, status: "cancelled" }));
    await waitFor(() => expect(header().getByRole("button", { name: "Download" })).toBeInTheDocument());
  });

  it("falls back to the rendered scene's last good clip after a cancel, not an unrelated one", async () => {
    const { user } = await renderApp({ media: [media("Intro"), notesRender] });
    await user.click(screen.getByRole("button", { name: /^Notes/ }));
    expect(previewVideo()?.getAttribute("src")).toContain("Notes.mp4");

    const { socket, id } = await startRender(user);
    act(() => socket.emit({ type: "result", render_id: id, success: false, status: "cancelled" }));
    await waitFor(() => expect(previewVideo()?.getAttribute("src")).toContain("/example/720p30/Intro.mp4"));
    expect(screen.queryByText(/Out of date/)).not.toBeInTheDocument();
  });

  it("marks only the failed scene's clip as out of date", async () => {
    const { user } = await renderApp({ media: [notesRender] });
    // example.py has no renders; a Notes clip from notes.py is showing.
    await user.click(screen.getByRole("button", { name: /^Notes/ }));
    const { socket, id } = await startRender(user);
    act(() => socket.emit({ type: "result", render_id: id, success: false, status: "failed" }));

    expect(await screen.findByText("Render failed")).toBeInTheDocument();
    expect(previewVideo()).toBeNull();
    expect(screen.queryByText(/Out of date/)).not.toBeInTheDocument();
  });

  it("keeps a failed scene's own clip with the out-of-date banner", async () => {
    const { user } = await renderApp({ media: [media("Intro")] });
    await waitFor(() => expect(previewVideo()).not.toBeNull());
    const { socket, id } = await startRender(user);
    act(() => socket.emit({ type: "result", render_id: id, success: false, status: "failed" }));
    expect(await screen.findByText("Out of date — the last render didn't replace this preview")).toBeInTheDocument();
  });

  it("doesn't put another file's finished render in the preview", async () => {
    const { user } = await renderApp();
    const { socket, id } = await startRender(user);
    await user.click(screen.getByRole("button", { name: "notes.py" }));
    await waitFor(() => expect(screen.getByLabelText("Code editor")).toHaveValue("class Notes(Scene):\n    pass\n"));

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
    expect(await screen.findByText("Intro rendered")).toBeInTheDocument();
    expect(previewVideo()).toBeNull();
  });

  it("clears the failure state when the open file is deleted", async () => {
    const { user } = await renderApp();
    const { socket, id } = await startRender(user);
    act(() => socket.emit({ type: "result", render_id: id, success: false, status: "failed" }));
    expect(await screen.findByText("Render failed — show console")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Delete example.py" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(screen.getByLabelText("Code editor")).toHaveValue("class Notes(Scene):\n    pass\n"));
    expect(screen.queryByText("Render failed — show console")).not.toBeInTheDocument();
    expect(screen.queryByText("Render failed")).not.toBeInTheDocument();
    expect(screen.getByText("Nothing rendered yet")).toBeInTheDocument();
  });
});

describe("cancel and queue states", () => {
  it("shows the queue position from the server and ends on its one cancelled result", async () => {
    const { user } = await renderApp();
    const { socket, id } = await startRender(user);
    const message = "Waiting for another render to finish… (position 2 in queue)";
    act(() => {
      socket.emit({ type: "queued", render_id: id, position: 2, message });
      socket.emit({ type: "info", render_id: id, message });
    });

    const overlay = screen.getByRole("status");
    expect(within(overlay).getByText("Queued Intro · position 2")).toBeInTheDocument();
    expect(within(overlay).getByText("Waiting for another render to finish…")).toBeInTheDocument();
    expect(screen.getByText("Intro · queued")).toBeInTheDocument();
    act(() => socket.emit({ type: "queued", render_id: id, position: 1, message }));
    expect(within(overlay).getByText("Queued Intro · position 1")).toBeInTheDocument();

    await user.click(within(overlay).getByRole("button", { name: "Cancel" }));
    expect(socket.lastSent()).toMatchObject({ type: "cancel", id });
    // Waits for the server instead of guessing.
    expect(within(overlay).getByRole("button", { name: "Stopping…" })).toBeDisabled();
    expect(within(overlay).getByText("Leaving the queue…")).toBeInTheDocument();
    act(() => socket.emit({ type: "info", render_id: id, message: "Stopping render..." }));
    expect(within(screen.getByRole("status")).getByText("Queued Intro · position 1")).toBeInTheDocument();

    act(() => socket.emit({ type: "result", render_id: id, success: false, status: "cancelled" }));
    expect(await screen.findByText("Render cancelled")).toBeInTheDocument();
    // "Leaving the queue…" stays up for at least STOPPING_MIN_DISPLAY_MS (display only), then goes.
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
    await expectLogLineOnce("Cancelled before it started.");
    expect(screen.getAllByRole("button", { name: "Render" })[0]).toBeEnabled();
  });

  it("switches from queued to rendering on the server's started event", async () => {
    const { user } = await renderApp();
    const { socket, id } = await startRender(user);
    act(() => socket.emit({ type: "queued", render_id: id, position: 1, message: "Waiting for another render to finish… (position 1 in queue)" }));
    // With typed events, other lines don't end the wait.
    act(() => socket.emit({ type: "info", render_id: id, message: "Some notice" }));
    expect(within(screen.getByRole("status")).getByText("Queued Intro · position 1")).toBeInTheDocument();

    act(() => socket.emit({ type: "started", render_id: id, waited: true }));
    expect(within(screen.getByRole("status")).getByText("Rendering Intro")).toBeInTheDocument();
    expect(screen.getByText("Intro · rendering")).toBeInTheDocument();
    act(() => socket.emit({ type: "progress", render_id: id, percent: 40, animation: 0 }));
    expect(within(screen.getByRole("status")).getByText(/Animation 1 of/)).toBeInTheDocument();
  });

  it("falls back to finishing a queued cancel locally when an older server never answers", async () => {
    const { user } = await renderApp();
    const { socket, id } = await startRender(user);
    act(() => socket.emit({ type: "info", render_id: id, message: "Waiting for another render to finish…" }));
    expect(within(screen.getByRole("status")).getByText("Queued Intro")).toBeInTheDocument();

    // Drive the fallback timer explicitly instead of waiting 3 real seconds.
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    fireEvent.click(within(screen.getByRole("status")).getByRole("button", { name: "Cancel" }));
    expect(socket.lastSent().type).toBe("cancel");
    act(() => vi.advanceTimersByTime(QUEUED_CANCEL_FALLBACK_MS - 1));
    expect(within(screen.getByRole("status")).getByRole("button", { name: "Stopping…" })).toBeDisabled();
    act(() => vi.advanceTimersByTime(1));
    // The overlay's minimum "Leaving the queue…" display (r3) runs on the faked clock too.
    act(() => vi.advanceTimersByTime(STOPPING_MIN_DISPLAY_MS));
    vi.useRealTimers();
    expect(await screen.findByText("Render cancelled")).toBeInTheDocument();

    // A late result for it is ignored: no second log line or toast.
    act(() => socket.emit({ type: "result", render_id: id, success: false, status: "cancelled" }));
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
    await expectLogLineOnce("Cancelled before it started.");
  });

  it("leaves the queue when Manim starts, and toolbar and overlay agree while stopping", async () => {
    const { user } = await renderApp();
    const { socket, id } = await startRender(user);
    act(() => socket.emit({ type: "info", render_id: id, message: "Waiting for another render to finish…" }));
    act(() => socket.emit({ type: "info", render_id: id, message: "$ manim example.py Intro -qm" }));
    expect(within(screen.getByRole("status")).getByText("Rendering Intro")).toBeInTheDocument();

    await user.click(within(screen.getByRole("status")).getByRole("button", { name: "Cancel" }));
    expect(socket.lastSent().type).toBe("cancel");
    expect(within(screen.getByRole("status")).getByRole("button", { name: "Stopping…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Stopping" })).toBeDisabled();
    expect(within(screen.getByRole("status")).getByText("Stopping Manim…")).toBeInTheDocument();

    act(() => socket.emit({ type: "result", render_id: id, success: false, status: "cancelled" }));
    expect(await screen.findByText("Render cancelled")).toBeInTheDocument();
  });
});

describe("empty scenes", () => {
  it("labels a still image instead of passing it off as a normal render", async () => {
    const { user } = await renderApp();
    const { socket, id } = await startRender(user);
    act(() => {
      socket.emit({
        type: "file_ready",
        render_id: id,
        url: "/media/images/example/Intro_ManimCE_v0.19.0.png",
        rel_path: "media/images/example/Intro_ManimCE_v0.19.0.png",
        filename: "Intro_ManimCE_v0.19.0.png",
        kind: "image",
      });
      socket.emit({ type: "result", render_id: id, success: true, status: "success" });
    });
    expect(await screen.findByText("Intro has no animations, so Manim saved a still image")).toBeInTheDocument();
    expect(screen.getByText("Still image")).toBeInTheDocument();
    expect(document.querySelector("section[aria-label='Preview'] img")).not.toBeNull();
  });
});

describe("toasts", () => {
  it("shows one syntax-error toast per error, replaces it on save, and clears it once fixed", async () => {
    const { editor, server } = await renderApp();
    const broken = EXAMPLE_CODE.replace("def construct(self):", "def construct(self)");
    fireEvent.change(editor, { target: { value: broken } });

    fireEvent.keyDown(editor, { key: "Enter", ctrlKey: true });
    fireEvent.keyDown(window, { key: "Enter", ctrlKey: true });
    fireEvent.keyDown(window, { key: "Enter", ctrlKey: true });
    await screen.findByText("This file has a syntax error");
    await waitFor(() => expect(screen.getAllByText("This file has a syntax error")).toHaveLength(1));
    // A render refused for a syntax error doesn't write the broken buffer to disk.
    expect(calls(server, "POST", "/api/save")).toHaveLength(0);
    expect(server.scripts["example.py"]).toBe(EXAMPLE_CODE);
    expect(FakeWebSocket.latest().sent.some((message) => message.type === "start")).toBe(false);

    fireEvent.change(editor, { target: { value: `${broken}# more\n` } });
    fireEvent.keyDown(window, { key: "s", ctrlKey: true });
    expect(await screen.findByText("Saved, but this file has a syntax error")).toBeInTheDocument();
    // An explicit save still writes it.
    expect(server.scripts["example.py"]).toBe(`${broken}# more\n`);
    await waitFor(() => expect(screen.queryByText("This file has a syntax error")).not.toBeInTheDocument());

    fireEvent.change(editor, { target: { value: EXAMPLE_CODE } });
    await waitFor(() => expect(screen.queryByText("Saved, but this file has a syntax error")).not.toBeInTheDocument(), {
      timeout: 3000,
    });
  });
});

describe("console and keyboard", () => {
  it("links only the file:line part of a console line and keeps the text selectable", async () => {
    const { user } = await renderApp();
    const { socket, id } = await startRender(user);
    act(() => socket.emit({ type: "log", render_id: id, stream: "stderr", message: '  File "/work/example.py", line 7, in construct' }));

    const log = await screen.findByRole("log");
    const link = log.querySelector("[data-line-link]")!;
    expect(link).toHaveTextContent('example.py", line 7');
    expect(within(log).queryByRole("button", { name: /File "/ })).not.toBeInTheDocument();
    const button = within(log).getByRole("button", { name: "Go to line 7" });
    expect(button).toHaveTextContent("Line 7");

    await user.click(link);
    expect(editorCalls).toContainEqual(["reveal", 7]);
  });

  it("makes each file list a single Tab stop with arrow-key navigation", async () => {
    const scripts: Record<string, string> = {};
    for (let index = 1; index <= 6; index += 1) scripts[`s${index}.py`] = `class S${index}(Scene):\n    pass\n`;
    const { user } = await renderApp({ scripts });
    const list = screen.getByRole("list", { name: "Scripts" });
    const rows = within(list).getAllByRole("button", { name: /^s\d\.py$/ });
    expect(rows.filter((row) => row.tabIndex === 0)).toEqual([rows[0]]);
    // Row actions are never Tab stops, so one Tab leaves the list.
    expect(within(list).getAllByRole("button", { name: /^(Rename|Delete) / }).every((button) => button.tabIndex === -1)).toBe(true);

    rows[0].focus();
    await user.keyboard("{ArrowDown}{ArrowDown}");
    expect(rows[2]).toHaveFocus();
    expect(rows[2].tabIndex).toBe(0);
    expect(rows[0].tabIndex).toBe(-1);
    await user.keyboard("{End}");
    expect(rows[5]).toHaveFocus();
    await user.keyboard("{Home}");
    expect(rows[0]).toHaveFocus();
  });

  it("offers a skip link and returns focus to the button that opened a dialog", async () => {
    const { user } = await renderApp();
    expect(screen.getByRole("button", { name: "Skip to editor" })).toBeInTheDocument();

    const setup = screen.getByRole("button", { name: "Setup" });
    // Keyboard only: in jsdom every pointerdown also starts a (focusing) panel-separator drag.
    setup.focus();
    await user.keyboard("{Enter}");
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(setup).not.toHaveFocus());
    expect(dialog).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(setup).toHaveFocus());
  });
});

describe("file names (server rules from #7)", () => {
  it("shows the server's case-only clash in the New script dialog and never overwrites", async () => {
    const { user, server } = await renderApp();
    // Created in another tab after this one loaded its file list.
    server.scripts["Orbit.py"] = "# theirs\n";
    server.scripts["taken.py"] = "# theirs too\n";
    await user.click(screen.getByRole("button", { name: "New script" }));
    const input = await screen.findByLabelText("File name");

    await user.clear(input);
    await user.type(input, "orbit");
    await user.click(screen.getByRole("button", { name: "Create" }));
    expect(await screen.findByText("'Orbit.py' already exists. File names that differ only by case are not allowed.")).toBeInTheDocument();

    await user.clear(input);
    await user.type(input, "taken");
    await user.click(screen.getByRole("button", { name: "Create" }));
    expect(await screen.findByText("taken.py already exists.")).toBeInTheDocument();
    expect(server.scripts["taken.py"]).toBe("# theirs too\n");
    expect(server.scripts).not.toHaveProperty("orbit.py");
  });

  it("validates names locally with the server's messages", async () => {
    const { user } = await renderApp();
    await user.click(screen.getByRole("button", { name: "New script" }));
    const input = await screen.findByLabelText("File name");
    await user.clear(input);
    await user.type(input, "_temp_run_x");
    await user.click(screen.getByRole("button", { name: "Create" }));
    expect(await screen.findByText("Filenames starting with '_temp_run_' are reserved for scratch renders.")).toBeInTheDocument();
  });

  it("shows a case-only clash from the server when renaming", async () => {
    const { user, server } = await renderApp();
    server.scripts["Intro.py"] = "# made elsewhere\n";
    await user.click(screen.getByRole("button", { name: "Rename example.py" }));
    await user.keyboard("intro{Enter}");
    expect(await screen.findByText("'Intro.py' already exists. File names that differ only by case are not allowed.")).toBeInTheDocument();
    expect(server.scripts["example.py"]).toBe(EXAMPLE_CODE);
  });
});

describe("Other scene…", () => {
  const FACTORY = "from manim import *\n\nBase = Scene\n\n\nclass Fancy(Base):\n    def construct(self):\n        self.wait()\n";

  async function chooseOther(user: ReturnType<typeof userEvent.setup>) {
    const trigger = screen.getByRole("combobox", { name: "Scene" });
    trigger.focus();
    await user.keyboard("{Enter}");
    fireEvent.click(await screen.findByRole("option", { name: "Other scene…" }));
    return screen.findByLabelText("Scene class name");
  }

  it("renders a scene the parser can't prove by typing its class name", async () => {
    const { user } = await renderApp({ scripts: { "factory.py": FACTORY } });
    expect(screen.getByRole("combobox", { name: "Scene" })).toHaveTextContent("No scenes found");
    expect(screen.getByRole("combobox", { name: "Scene" })).toBeEnabled();

    const input = await chooseOther(user);
    await user.type(input, "Fancy{Enter}", { skipClick: true });
    expect(screen.getByRole("combobox", { name: "Scene" })).toHaveTextContent("Fancy");

    // Still selected after the code changes and is parsed again.
    fireEvent.change(screen.getByLabelText("Code editor"), { target: { value: `${FACTORY}# edit\n` } });
    await new Promise((resolve) => setTimeout(resolve, 600));
    expect(screen.getByRole("combobox", { name: "Scene" })).toHaveTextContent("Fancy");

    const { start } = await startRender(user);
    expect(start.scene).toBe("Fancy");
  });

  it("ignores names that aren't Python class names and cancels with Escape", async () => {
    const { user } = await renderApp();
    let input = await chooseOther(user);
    await user.type(input, "not a class{Enter}", { skipClick: true });
    expect(screen.getByRole("combobox", { name: "Scene" })).toHaveTextContent("Intro");

    input = await chooseOther(user);
    await user.type(input, "Other{Escape}", { skipClick: true });
    expect(screen.getByRole("combobox", { name: "Scene" })).toHaveTextContent("Intro");
  });
});

describe("browser verification follow-ups", () => {
  it("B: keeps row actions out of the Tab order but reachable with arrows, F2, and Delete", async () => {
    const { user } = await renderApp();
    const list = screen.getByRole("list", { name: "Scripts" });
    const row = within(list).getByRole("button", { name: "example.py" });
    const rename = within(list).getByRole("button", { name: "Rename example.py" });
    const remove = within(list).getByRole("button", { name: "Delete example.py" });
    expect(row).toHaveAttribute("aria-keyshortcuts", "F2 Delete ArrowRight");

    row.focus();
    await user.tab();
    expect(list.contains(document.activeElement)).toBe(false);

    row.focus();
    await user.keyboard("{ArrowRight}");
    expect(rename).toHaveFocus();
    await user.keyboard("{ArrowRight}");
    expect(remove).toHaveFocus();
    await user.keyboard("{ArrowRight}{ArrowLeft}{ArrowLeft}");
    expect(row).toHaveFocus();

    await user.keyboard("{F2}");
    expect(await screen.findByLabelText("New file name")).toHaveValue("example.py");
    await user.keyboard("{Escape}");

    within(list).getByRole("button", { name: "example.py" }).focus();
    await user.keyboard("{Delete}");
    expect(await screen.findByText("Delete example.py?")).toBeInTheDocument();
  });

  it("D: a pasted or filled name that already ends in .py isn't doubled", async () => {
    const { user } = await renderApp();
    await user.click(screen.getByRole("button", { name: "New script" }));
    const input = (await screen.findByLabelText("File name")) as HTMLInputElement;

    // Focus selects only the stem; pasting a full name over it used to keep the old ".py".
    input.setSelectionRange(0, input.value.replace(/\.py$/i, "").length);
    await user.paste("pasted.py");
    expect(input).toHaveValue("pasted.py");

    fireEvent.change(input, { target: { value: "Example.py.py" } });
    expect(input).toHaveValue("Example.py");
    await user.click(screen.getByRole("button", { name: "Create" }));
    expect(await screen.findByText("'example.py' already exists. File names that differ only by case are not allowed.")).toBeInTheDocument();

    fireEvent.change(input, { target: { value: ".x.py.py" } });
    expect(input).toHaveValue(".x.py");
    await user.click(screen.getByRole("button", { name: "Create" }));
    expect(await screen.findByText(validateScriptName(".x.py")!)).toBeInTheDocument();
  });

  it("E: Refresh notices that the open file was deleted outside the app", async () => {
    const { server } = await renderApp();
    delete server.scripts["example.py"];
    const refresh = screen.getByRole("button", { name: "Refresh files" });
    refresh.focus();
    fireEvent.click(refresh);

    expect(await screen.findByText("example.py was renamed or deleted elsewhere")).toBeInTheDocument();
    await waitFor(() =>
      expect(within(screen.getByRole("list", { name: "Scripts" })).queryByRole("button", { name: "example.py" })).not.toBeInTheDocument(),
    );
    expect(screen.getByLabelText("Code editor")).toHaveValue(EXAMPLE_CODE);

    fireEvent.click(screen.getByRole("button", { name: "Recreate file" }));
    await waitFor(() => expect(server.scripts["example.py"]).toBe(EXAMPLE_CODE));
  });

  it("F/G: labels another file's output, links only the open file's, and jumps despite a selection elsewhere", async () => {
    const { user } = await renderApp();
    const { socket, id } = await startRender(user);
    act(() => {
      socket.emit({ type: "log", render_id: id, stream: "stderr", message: "│ example.py:7 in construct │" });
      socket.emit({ type: "log", render_id: id, stream: "stderr", message: "NameError: name 'Foo' is not defined" });
    });
    const log = await screen.findByRole("log");
    await waitFor(() => expect(log.querySelector("[data-line-link]")).not.toBeNull());
    const link = log.querySelector("[data-line-link]")!;
    expect(link.parentElement).toHaveTextContent("│ example.py:7 in construct │");

    // G: a selection in another line doesn't swallow the first click.
    const other = within(log).getByText("NameError: name 'Foo' is not defined");
    const range = document.createRange();
    range.selectNodeContents(other);
    window.getSelection()!.removeAllRanges();
    window.getSelection()!.addRange(range);
    fireEvent.click(link);
    await waitFor(() => expect(editorCalls).toContainEqual(["reveal", 7]));

    // Selecting the link itself (to copy it) doesn't jump.
    editorCalls.length = 0;
    range.selectNodeContents(link);
    window.getSelection()!.removeAllRanges();
    window.getSelection()!.addRange(range);
    fireEvent.click(link);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(editorCalls).not.toContainEqual(["reveal", 7]);
    window.getSelection()!.removeAllRanges();

    // F: switching files labels the output instead of linking it into the wrong file.
    act(() => socket.emit({ type: "result", render_id: id, success: false, status: "error" }));
    await user.click(screen.getByRole("button", { name: "notes.py" }));
    // The notice is a chip in the console header (r3), not a row inside the log.
    expect(await screen.findByText(/not the open file/)).toBeInTheDocument();
    expect(log.querySelector("[data-line-link]")).toBeNull();
    expect(within(log).queryByRole("button", { name: "Go to line 7" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Open example.py" }));
    await waitFor(() => expect(log.querySelector("[data-line-link]")).not.toBeNull());
    expect(screen.queryByText(/not the open file/)).not.toBeInTheDocument();
  });
});
