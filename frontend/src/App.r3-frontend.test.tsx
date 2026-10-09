// Fix round 3: render state bound to its job, render blocking (size / syntax),
// focus return and default focus, status bar, queue events, live file-name
// checks, typed scene persistence, and browser-storage conflicts.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/editor/CodeEditor", async () => {
  const { FakeCodeEditor } = await import("@/test/fakeEditor");
  return { default: FakeCodeEditor };
});

import App from "./App";
import { editorCalls } from "@/test/fakeEditor";
import { installFakeServer, type FakeServer } from "@/test/fakeServer";
import { FakeWebSocket } from "@/test/fakeSocket";
import { QUEUED_CANCEL_FALLBACK_MS } from "@/hooks/useRenderSession";
import { browserFileKey, deleteBrowserFile, loadBrowserFiles, STORAGE_KEYS, writeBrowserFile } from "@/lib/storage";
import { MAX_CODE_BYTES, setMaxCodeBytes } from "@/lib/constants";

type Overrides = Parameters<typeof installFakeServer>[0];

async function renderApp(overrides?: Overrides) {
  const server = installFakeServer(overrides);
  const user = userEvent.setup();
  const view = render(<App />);
  const editor = await screen.findByLabelText("Code editor");
  await waitFor(() => expect(screen.getByText("Connected")).toBeInTheDocument());
  return { server, user, view, editor: editor as HTMLTextAreaElement };
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

async function openScript(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.click(within(screen.getByRole("list", { name: "Scripts" })).getByRole("button", { name }));
  await waitFor(() => expect(screen.getByLabelText("Code editor")).toHaveAttribute("data-path", `disk/${name}`));
}

function starts() {
  return FakeWebSocket.instances.flatMap((socket) => socket.sent.filter((message) => message.type === "start"));
}

async function nextFrame() {
  await act(() => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())));
}

afterEach(() => {
  vi.useRealTimers();
  // The limit from /api/diagnostics is module state; don't leak a test's small limit.
  setMaxCodeBytes(MAX_CODE_BYTES);
});

beforeEach(() => {
  editorCalls.length = 0;
});

// Two files, both defining `class Same(Scene)`, with different steps.
const SAME_A = "from manim import *\n\n\nclass Same(Scene):\n    def construct(self):\n        self.play(Create(Circle()))\n        self.play(FadeOut(Circle()))\n        self.wait(1)\n";
const SAME_B = "from manim import *\n\n\nclass Same(Scene):\n    def construct(self):\n        self.wait(1)\n";

describe("render state belongs to its job (file + scene + render id)", () => {
  it("doesn't show one file's overlay, progress, or timeline highlight on another file with the same scene name", async () => {
    const { user } = await renderApp({ scripts: { "same_a.py": SAME_A, "same_b.py": SAME_B } });
    await openScript(user, "same_a.py");
    const { socket, id } = await startRender(user);
    act(() => socket.emit({ type: "progress", render_id: id, percent: 50, animation: 1 }));

    // Own file: overlay with the right total (3 steps from same_a.py), highlight on step 2.
    const overlay = screen.getByRole("group", { name: "Render in progress" });
    expect(within(overlay).getByText("Rendering Same")).toBeInTheDocument();
    expect(within(overlay).getByText(/Animation 2 of 3/)).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByRole("tab", { name: /Timeline/ }), { button: 0 });
    const timeline = () => screen.getByRole("tabpanel");
    expect(within(timeline()).getAllByRole("option")[1]).toHaveAttribute("aria-current", "step");
    expect(screen.getByLabelText("Render progress")).toBeInTheDocument();

    // Another file with a scene of the same name: no overlay, highlight, or bottom progress.
    await openScript(user, "same_b.py");
    expect(screen.queryByText("Rendering Same", { selector: "p" })).not.toBeInTheDocument();
    expect(within(timeline()).queryAllByRole("option").filter((button) => button.getAttribute("aria-current"))).toHaveLength(0);
    expect(screen.queryByLabelText("Render progress")).not.toBeInTheDocument();
    // Instead a slim banner names the job, and the status bar says which file it is.
    const banner = screen.getByTestId("other-render");
    expect(banner).toHaveTextContent("Rendering Same from same_a.py");
    expect(screen.getByText("(same_a.py)")).toBeInTheDocument();
    // Progress keeps using the rendering file's steps: animation 2 of 3 is 50%, not "of 1".
    act(() => socket.emit({ type: "progress", render_id: id, percent: 0, animation: 2 }));
    expect(document.title).toMatch(/^\d+% · /);

    // Back to the rendering file: overlay and highlight return.
    await user.click(within(banner).getByRole("button", { name: "Open" }));
    await waitFor(() => expect(screen.getByLabelText("Code editor")).toHaveAttribute("data-path", "disk/same_a.py"));
    expect(screen.getByText("Rendering Same", { selector: "p" })).toBeInTheDocument();
    expect(within(timeline()).getAllByRole("option")[2]).toHaveAttribute("aria-current", "step");
  });

  it("stops highlighting when the open code no longer matches what is rendering", async () => {
    const { user, editor } = await renderApp({ scripts: { "same_a.py": SAME_A } });
    const { socket, id } = await startRender(user);
    act(() => socket.emit({ type: "progress", render_id: id, percent: 10, animation: 0 }));
    fireEvent.mouseDown(screen.getByRole("tab", { name: /Timeline/ }), { button: 0 });
    expect(within(screen.getByRole("tabpanel")).getAllByRole("option")[0]).toHaveAttribute("aria-current", "step");
    fireEvent.change(editor, { target: { value: SAME_A.replace("        self.wait(1)\n", "        self.wait(1)\n        self.wait(2)\n") } });
    await waitFor(() => expect(within(screen.getByRole("tabpanel")).getAllByRole("option")).toHaveLength(4));
    expect(within(screen.getByRole("tabpanel")).getAllByRole("option").filter((button) => button.getAttribute("aria-current"))).toHaveLength(0);
    // The overlay still counts the steps of the code being rendered.
    act(() => socket.emit({ type: "progress", render_id: id, percent: 10, animation: 1 }));
    expect(within(screen.getByRole("group", { name: "Render in progress" })).getByText(/Animation 2 of 3/)).toBeInTheDocument();
  });
});

describe("Render is blocked, with the reason, for oversized scripts and syntax errors", () => {
  it("disables Render and Ctrl+Enter for a buffer over the server's max_code_bytes", async () => {
    const server = installFakeServer();
    server.diagnostics.max_code_bytes = 200;
    const user = userEvent.setup();
    render(<App />);
    const editor = await screen.findByLabelText("Code editor");
    await waitFor(() => expect(screen.getByText("Connected")).toBeInTheDocument());

    fireEvent.change(editor, { target: { value: `from manim import *\nclass A(Scene):\n    def construct(self):\n        pass\n# ${"x".repeat(300)}\n` } });
    const button = renderButton();
    await waitFor(() => expect(button).toHaveAttribute("aria-disabled", "true"));
    expect(button).not.toBeDisabled(); // still focusable, so the reason is reachable
    const reason = document.getElementById(button.getAttribute("aria-describedby")!);
    expect(reason).toHaveTextContent(/over the 200 bytes limit, so it can't be saved or rendered/);
    expect(screen.getByRole("note")).toHaveTextContent(/over the 200 bytes limit/);

    fireEvent.keyDown(window, { key: "Enter", ctrlKey: true });
    expect(await screen.findByText("Can't render this script")).toBeInTheDocument();
    await user.click(button);
    expect(starts()).toHaveLength(0);
    expect(server.calls.some((call) => call.path === "/api/save")).toBe(false);
  });

  it("doesn't render the copy on disk of a file that is already over the limit (R2 p2/28)", async () => {
    const big = `from manim import *\nclass Big(Scene):\n    def construct(self):\n        pass\n# ${"y".repeat(400)}\n`;
    const server = installFakeServer({ scripts: { "big.py": big } });
    server.diagnostics.max_code_bytes = 200;
    render(<App />);
    await screen.findByLabelText("Code editor");
    await waitFor(() => expect(screen.getByText("Connected")).toBeInTheDocument());
    await waitFor(() => expect(renderButton()).toHaveAttribute("aria-disabled", "true"));
    // Not dirty and already parsed (the server sent its scenes with the file): nothing else measures it.
    fireEvent.keyDown(window, { key: "Enter", ctrlKey: true });
    expect(await screen.findByText("Can't render this script")).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(starts()).toHaveLength(0);
  });

  it("disables Render with the syntax error as the reason; Ctrl+Enter shows it with Go to line", async () => {
    const { editor, user } = await renderApp();
    fireEvent.change(editor, { target: { value: "from manim import *\n\nclass A(Scene):\n    def construct(self)\n        pass\n" } });
    await waitFor(() => expect(renderButton()).toHaveAttribute("aria-disabled", "true"));
    expect(document.getElementById(renderButton().getAttribute("aria-describedby")!)).toHaveTextContent(
      "Fix the syntax error on line 4 first: expected ':'",
    );
    fireEvent.keyDown(window, { key: "Enter", ctrlKey: true });
    expect(await screen.findByText("This file has a syntax error")).toBeInTheDocument();
    expect(starts()).toHaveLength(0);

    fireEvent.change(editor, { target: { value: "from manim import *\n\nclass A(Scene):\n    def construct(self):\n        pass\n" } });
    await waitFor(() => expect(renderButton()).not.toHaveAttribute("aria-disabled"));
    await startRender(user);
  });
});

describe("focus", () => {
  it("Delete confirm focuses Cancel, Escape returns focus to the row, and deleting moves it to the next row", async () => {
    const { user } = await renderApp();
    const list = screen.getByRole("list", { name: "Scripts" });
    const row = within(list).getByRole("button", { name: "example.py" });
    row.focus();
    await user.keyboard("{Delete}");
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Cancel" })).toHaveFocus());
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(row).toHaveFocus());

    await user.keyboard("{Delete}");
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(within(list).getByRole("button", { name: "notes.py" })).toHaveFocus());
  });

  it("returns focus to the row after Escape or Enter in F2 rename", async () => {
    const { user, server } = await renderApp();
    const list = screen.getByRole("list", { name: "Scripts" });
    within(list).getByRole("button", { name: "notes.py" }).focus();
    await user.keyboard("{F2}");
    expect(screen.getByLabelText("New file name")).toHaveFocus();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(within(list).getByRole("button", { name: "notes.py" })).toHaveFocus());

    await user.keyboard("{F2}");
    await user.keyboard("jottings{Enter}");
    await waitFor(() => expect(server.scripts).toHaveProperty("jottings.py"));
    await waitFor(() => expect(within(list).getByRole("button", { name: "jottings.py" })).toHaveFocus());
  });

  it("returns focus to the Scene picker after Enter or Escape in the Other scene… box", async () => {
    const { user } = await renderApp();
    const trigger = screen.getByRole("combobox", { name: "Scene" });
    trigger.focus();
    await user.keyboard("{Enter}");
    fireEvent.click(await screen.findByRole("option", { name: "Other scene…" }));
    const input = await screen.findByLabelText("Scene class name");
    await user.type(input, "Typed{Escape}", { skipClick: true });
    await waitFor(() => expect(screen.getByRole("combobox", { name: "Scene" })).toHaveFocus());
  });

  it("the save-conflict dialog focuses Cancel and replaces the outside-change toast", async () => {
    const { server, editor } = await renderApp();
    fireEvent.change(editor, { target: { value: "# mine" } });
    server.scripts["example.py"] = "# theirs\n";
    act(() => void window.dispatchEvent(new Event("focus")));
    expect(await screen.findByText("example.py changed outside this tab")).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "s", ctrlKey: true });
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Cancel" })).toHaveFocus());
    // The toast with its competing "Reload theirs" action is gone, and focus checks wait.
    await waitFor(() => expect(screen.queryAllByText("example.py changed outside this tab")).toHaveLength(1));
    expect(within(dialog).getByText("example.py changed outside this tab")).toBeInTheDocument();
    server.scripts["example.py"] = "# theirs again\n";
    act(() => void window.dispatchEvent(new Event("focus")));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryAllByText("example.py changed outside this tab")).toHaveLength(1);
  });
});

describe("status bar and queue", () => {
  it("doesn't keep another file's 'Render failed' after switching files", async () => {
    const { user } = await renderApp();
    const { socket, id } = await startRender(user);
    act(() => socket.emit({ type: "result", render_id: id, success: false, status: "error" }));
    expect(await screen.findByText("Render failed — show console")).toBeInTheDocument();
    await openScript(user, "notes.py");
    expect(screen.queryByText("Render failed — show console")).not.toBeInTheDocument();
    await openScript(user, "example.py");
    expect(screen.getByText("Render failed — show console")).toBeInTheDocument();
  });

  it("updates the queue position from repeated events (and a queue_position event)", async () => {
    const { user } = await renderApp();
    const { socket, id } = await startRender(user);
    act(() => socket.emit({ type: "queued", render_id: id, position: 3, message: "Waiting… (position 3 in queue)" }));
    expect(within(screen.getByRole("group", { name: "Render in progress" })).getByText("Queued Intro · position 3")).toBeInTheDocument();
    expect(screen.getByText("· position 3")).toBeInTheDocument(); // status bar
    act(() => socket.emit({ type: "queued", render_id: id, position: 2, message: "Waiting… (position 2 in queue)" }));
    expect(within(screen.getByRole("group", { name: "Render in progress" })).getByText("Queued Intro · position 2")).toBeInTheDocument();
    act(() => socket.emit({ type: "queue_position", render_id: id, position: 1 }));
    expect(within(screen.getByRole("group", { name: "Render in progress" })).getByText("Queued Intro · position 1")).toBeInTheDocument();
    act(() => socket.emit({ type: "started", render_id: id, waited: true }));
    expect(within(screen.getByRole("group", { name: "Render in progress" })).getByText("Rendering Intro")).toBeInTheDocument();
    // A late position update can't put a started render back in the queue.
    act(() => socket.emit({ type: "queued", render_id: id, position: 1 }));
    expect(within(screen.getByRole("group", { name: "Render in progress" })).getByText("Rendering Intro")).toBeInTheDocument();
  });

  it("says 'Cancelled before it started.' only for a render that never started", async () => {
    const { user } = await renderApp();
    const { socket, id } = await startRender(user);
    act(() => socket.emit({ type: "queued", render_id: id, position: 1 }));
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    fireEvent.click(within(screen.getByRole("group", { name: "Render in progress" })).getByRole("button", { name: "Cancel" }));
    // The cancel raced the start: Manim did start and is being stopped.
    act(() => socket.emit({ type: "started", render_id: id, waited: true }));
    act(() => vi.advanceTimersByTime(QUEUED_CANCEL_FALLBACK_MS + 10));
    vi.useRealTimers();
    expect(within(screen.getByRole("group", { name: "Render in progress" })).getByRole("button", { name: "Stopping…" })).toBeDisabled();
    act(() => socket.emit({ type: "result", render_id: id, success: false, status: "cancelled" }));
    expect(await screen.findByText("Render cancelled")).toBeInTheDocument();
    await nextFrame();
    await nextFrame();
    expect(screen.queryByText("Cancelled before it started.")).not.toBeInTheDocument();
  });
});

describe("file names while typing", () => {
  it("shows the problem live and disables Create in the New script dialog", async () => {
    const { user } = await renderApp();
    await user.click(screen.getByRole("button", { name: "New script" }));
    const input = await screen.findByLabelText("File name");
    await user.clear(input);
    await user.type(input, "CON");
    expect(screen.getByRole("alert")).toHaveTextContent("Filename 'CON.py' is a reserved device name.");
    expect(screen.getByRole("button", { name: "Create" })).toBeDisabled();
    await user.clear(input);
    await user.type(input, "fine_name");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("Will be saved as fine_name.py")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create" })).toBeEnabled();
  });

  it("uses the shared rule for .PY: Foo.PY is fine and is created as Foo.py (never Foo.PY.py)", async () => {
    const { user, server } = await renderApp();
    await user.click(screen.getByRole("button", { name: "New script" }));
    const input = await screen.findByLabelText("File name");
    await user.clear(input);
    await user.type(input, "Foo.PY");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("Will be saved as Foo.py")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => expect(server.scripts).toHaveProperty(["Foo.py"]));
    expect(Object.keys(server.scripts)).not.toContain("Foo.PY.py");
    // Renaming to Foo.PY: no error while typing either (same rule, same wording).
    await user.click(screen.getByRole("button", { name: "Rename notes.py" }));
    await user.keyboard("{Control>}a{/Control}Bar.PY");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByLabelText("New file name")).not.toHaveAttribute("aria-invalid");
  });

  it("shows the same message live while renaming, and Enter does nothing while it's invalid", async () => {
    const { user, server } = await renderApp();
    await user.click(screen.getByRole("button", { name: "Rename notes.py" }));
    await user.keyboard("{Control>}a{/Control}CON");
    expect(screen.getByRole("alert")).toHaveTextContent("Filename 'CON.py' is a reserved device name.");
    expect(screen.getByLabelText("New file name")).toHaveAttribute("aria-invalid", "true");
    await user.keyboard("{Enter}");
    expect(screen.getByLabelText("New file name")).toBeInTheDocument();
    expect(server.scripts).toHaveProperty("notes.py");
  });

  it("opens the file under the name the server created", async () => {
    const { user, server } = await renderApp();
    const original = server.fetch.getMockImplementation() as (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
    // A server whose name rule normalises the extension (Fixer's shared rule: Foo.PY -> Foo.py).
    server.fetch.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).endsWith("/api/save") && typeof init?.body === "string") {
        const body = JSON.parse(init.body);
        body.filename = body.filename.replace(/\.py$/i, "").replace(/\.PY$/, "") + "_srv.py";
        return original(input, { ...init, body: JSON.stringify(body) });
      }
      return original(input, init);
    });
    await user.click(screen.getByRole("button", { name: "New script" }));
    const input = await screen.findByLabelText("File name");
    await user.clear(input);
    await user.type(input, "orbit{Enter}");
    await waitFor(() => expect(screen.getByLabelText("Code editor")).toHaveAttribute("data-path", "disk/orbit_srv.py"));
    expect(screen.queryByText(/must end with \.py/)).not.toBeInTheDocument();
  });
});

describe("typed scene names and browser storage", () => {
  const FACTORY = "from manim import *\n\nBase = Scene\n\n\nclass Fancy(Base):\n    def construct(self):\n        self.wait()\n";

  it("keeps a scene typed with Other scene… after a reload", async () => {
    const { user, view, server } = await renderApp({ scripts: { "factory.py": FACTORY } });
    const trigger = screen.getByRole("combobox", { name: "Scene" });
    trigger.focus();
    await user.keyboard("{Enter}");
    fireEvent.click(await screen.findByRole("option", { name: "Other scene…" }));
    await user.type(await screen.findByLabelText("Scene class name"), "Fancy{Enter}", { skipClick: true });
    expect(screen.getByRole("combobox", { name: "Scene" })).toHaveTextContent("Fancy");

    view.unmount();
    FakeWebSocket.reset();
    installFakeServer({ scripts: server.scripts });
    render(<App />);
    await screen.findByLabelText("Code editor");
    await waitFor(() => expect(screen.getByRole("combobox", { name: "Scene" })).toHaveTextContent("Fancy"));
  });

  async function renderBrowserMode(files: Record<string, string>) {
    localStorage.setItem(STORAGE_KEYS.storageMode, JSON.stringify("browser"));
    localStorage.setItem(STORAGE_KEYS.browserFiles, JSON.stringify(files));
    return renderApp();
  }

  /** Another tab's writes: one key per script, one "storage" event per changed key (like a browser). */
  function writeFromOtherTab(files: Record<string, string>) {
    const before = loadBrowserFiles();
    const changed: [string, string | null][] = [];
    for (const name of Object.keys(before)) {
      if (!(name in files)) {
        deleteBrowserFile(name);
        changed.push([browserFileKey(name), null]);
      }
    }
    for (const [name, content] of Object.entries(files)) {
      if (before[name] === content) continue;
      writeBrowserFile(name, content);
      changed.push([browserFileKey(name), content]);
    }
    for (const [key, newValue] of changed) act(() => void window.dispatchEvent(new StorageEvent("storage", { key, newValue })));
  }

  it("asks before overwriting a script another tab saved in browser storage", async () => {
    const { editor, user } = await renderBrowserMode({ "a.py": "# v1\n" });
    fireEvent.change(editor, { target: { value: "# mine\n" } });
    writeFromOtherTab({ "a.py": "# theirs\n" });
    expect(await screen.findByText("a.py changed in another tab")).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "s", ctrlKey: true });
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("a.py changed in another tab")).toBeInTheDocument();
    expect(loadBrowserFiles()["a.py"]).toBe("# theirs\n");
    await user.click(within(dialog).getByRole("button", { name: "Reload theirs" }));
    await waitFor(() => expect(screen.getByLabelText("Code editor")).toHaveValue("# theirs\n"));

    fireEvent.change(screen.getByLabelText("Code editor"), { target: { value: "# mine again\n" } });
    fireEvent.keyDown(window, { key: "s", ctrlKey: true });
    await waitFor(() => expect(loadBrowserFiles()["a.py"]).toBe("# mine again\n"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("reloads a clean buffer quietly and won't recreate a script deleted in another tab", async () => {
    const { user } = await renderBrowserMode({ "a.py": "# v1\n", "b.py": "# b\n" });
    writeFromOtherTab({ "a.py": "# v2\n", "b.py": "# b\n" });
    await waitFor(() => expect(screen.getByLabelText("Code editor")).toHaveValue("# v2\n"));
    expect(await screen.findByText("Reloaded a.py")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Code editor"), { target: { value: "# keep\n" } });
    writeFromOtherTab({ "b.py": "# b\n" });
    expect(await screen.findByText("a.py was renamed or deleted in another tab")).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "s", ctrlKey: true });
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("a.py no longer exists")).toBeInTheDocument();
    expect(loadBrowserFiles()).not.toHaveProperty("a.py");
    await user.click(within(dialog).getByRole("button", { name: "Recreate file" }));
    await waitFor(() => expect(loadBrowserFiles()["a.py"]).toBe("# keep\n"));
  });
});

// Keep the fake server type referenced for editors.
export type { FakeServer };

describe("R3 browser verification follow-ups", () => {
  function previewRender() {
    return within(screen.getByRole("region", { name: "Preview" })).getByRole("button", { name: "Render" });
  }

  it("C: the preview's Render is blocked too, with the same reason in plain sight (size and syntax)", async () => {
    const server = installFakeServer();
    server.diagnostics.max_code_bytes = 200;
    render(<App />);
    const editor = await screen.findByLabelText("Code editor");
    await waitFor(() => expect(screen.getByText("Connected")).toBeInTheDocument());
    fireEvent.change(editor, { target: { value: `from manim import *\nclass A(Scene):\n    def construct(self):\n        pass\n# ${"x".repeat(300)}\n` } });
    await waitFor(() => expect(previewRender()).toHaveAttribute("aria-disabled", "true"));
    const reason = document.getElementById(previewRender().getAttribute("aria-describedby")!);
    expect(reason).toBeVisible();
    expect(reason).toHaveTextContent(/over the 200 bytes limit/);
    fireEvent.click(previewRender());
    expect(await screen.findByText("Can't render this script")).toBeInTheDocument();
    expect(starts()).toHaveLength(0);

    fireEvent.change(editor, { target: { value: "from manim import *\n\nclass A(Scene):\n    def construct(self)\n        pass\n" } });
    await waitFor(() =>
      expect(document.getElementById(previewRender().getAttribute("aria-describedby")!)).toHaveTextContent("Fix the syntax error on line 4 first"),
    );
    expect(previewRender()).toHaveAttribute("aria-disabled", "true");
  });

  it("D: another file's job doesn't turn this file's toolbar Render into Cancel", async () => {
    const { user } = await renderApp({ scripts: { "same_a.py": SAME_A, "same_b.py": SAME_B } });
    await openScript(user, "same_a.py");
    await startRender(user);
    const toolbar = () => screen.getByRole("region", { name: "Editor" });
    expect(within(toolbar()).getByRole("button", { name: "Cancel" })).toBeInTheDocument();

    await openScript(user, "same_b.py");
    expect(within(toolbar()).queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
    const render_ = within(toolbar()).getByRole("button", { name: "Render" });
    expect(render_).toHaveAttribute("aria-disabled", "true");
    expect(document.getElementById(render_.getAttribute("aria-describedby")!)).toHaveTextContent(
      "Rendering Same from same_a.py. Wait for it or cancel it, then render this file.",
    );
    // Ctrl+Enter says why instead of doing nothing; nothing else is started.
    fireEvent.keyDown(window, { key: "Enter", ctrlKey: true });
    expect(await screen.findByText("Can't render this script")).toBeInTheDocument();
    expect(starts()).toHaveLength(1);
    // The other job is still cancellable from the banner.
    expect(within(screen.getByTestId("other-render")).getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  });
});

describe("412 current_version (#15)", () => {
  it("Overwrite replaces exactly the version the conflict reported, without an extra fetch", async () => {
    const { server, editor, user } = await renderApp();
    fireEvent.change(editor, { target: { value: "# mine\n" } });
    server.scripts["example.py"] = "# theirs\n";
    fireEvent.keyDown(window, { key: "s", ctrlKey: true });
    const dialog = await screen.findByRole("dialog");
    const before = server.calls.length;
    await user.click(within(dialog).getByRole("button", { name: "Overwrite" }));
    await waitFor(() => expect(server.scripts["example.py"]).toBe("# mine\n"));
    const calls = server.calls.slice(before);
    expect(calls.some((call) => call.path.startsWith("/api/file-content"))).toBe(false);
    const saveCall = calls.find((call) => call.path === "/api/save")!;
    const { versionOf } = await import("@/test/fakeServer");
    expect((saveCall.body as { base_version?: string }).base_version).toBe(versionOf("# theirs\n"));
  });

  it("asks again when the file changed once more before Overwrite landed", async () => {
    const { server, editor, user } = await renderApp();
    fireEvent.change(editor, { target: { value: "# mine\n" } });
    server.scripts["example.py"] = "# theirs\n";
    fireEvent.keyDown(window, { key: "s", ctrlKey: true });
    const dialog = await screen.findByRole("dialog");
    server.scripts["example.py"] = "# theirs, again\n";
    await user.click(within(dialog).getByRole("button", { name: "Overwrite" }));
    expect(await screen.findByRole("dialog")).toHaveTextContent("example.py changed outside this tab");
    expect(server.scripts["example.py"]).toBe("# theirs, again\n");
  });
});

describe("conflictVersion", () => {
  it("reads current_version from the body, else the ETag", async () => {
    const { conflictVersion } = await import("@/hooks/useWorkspace");
    const { ApiError } = await import("@/lib/api");
    expect(conflictVersion(new ApiError("x", 412, { current_version: "v9" }, '"v8"'))).toBe("v9");
    expect(conflictVersion(new ApiError("x", 412, { detail: "x" }, 'W/"v8"'))).toBe("v8");
    expect(conflictVersion(new ApiError("x", 412, null, null))).toBeNull();
  });
});
