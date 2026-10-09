// Fix round 4: render state keyed by storage + file (and following a rename), the size
// banner, conflict wording, focus after New script / Cancel, the New script hint,
// milestone-only announcements, rename-on-blur of legacy names, and browser storage
// (rename of a deleted script, empty list after deleting the last one).
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/editor/CodeEditor", async () => {
  const { FakeCodeEditor } = await import("@/test/fakeEditor");
  return { default: FakeCodeEditor };
});

import App from "./App";
import { DIAGNOSTICS, EXAMPLE_CODE, installFakeServer } from "@/test/fakeServer";
import { FakeWebSocket } from "@/test/fakeSocket";
import { BROWSER_STARTER, browserFileKey, deleteBrowserFile, loadBrowserFiles, readBrowserFile, STORAGE_KEYS, writeBrowserFile } from "@/lib/storage";
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

const editorSection = () => screen.getByRole("region", { name: "Editor" });
const overlay = () => screen.queryByRole("group", { name: "Render in progress" });

async function startRender(user: ReturnType<typeof userEvent.setup>) {
  await user.click(within(editorSection()).getByRole("button", { name: "Render" }));
  const socket = FakeWebSocket.latest();
  await waitFor(() => expect(socket.sent.some((message) => message.type === "start")).toBe(true));
  const start = socket.lastSent("start");
  return { socket, start, id: start.id as string };
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

afterEach(() => {
  vi.useRealTimers();
  setMaxCodeBytes(MAX_CODE_BYTES);
});

describe("R4 #2: render state is keyed by storage mode as well as file name", () => {
  it("a disk my_scene.py render doesn't show on the browser-storage my_scene.py", async () => {
    const { user } = await renderApp({ scripts: { "my_scene.py": EXAMPLE_CODE } });
    const { socket, id } = await startRender(user);
    act(() => socket.emit({ type: "progress", render_id: id, percent: 40 }));
    expect(overlay()).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Settings" }));
    await user.click(screen.getByRole("radio", { name: "Browser" }));
    await waitFor(() => expect(screen.getByLabelText("Code editor")).toHaveValue(BROWSER_STARTER));
    expect(screen.getByLabelText("Code editor")).toHaveAttribute("data-path", "browser/my_scene.py");

    // Not this file's job: no overlay, Render stays Render (blocked, with the reason), a banner names it.
    expect(overlay()).not.toBeInTheDocument();
    expect(within(editorSection()).queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
    const render = within(editorSection()).getByRole("button", { name: "Render" });
    expect(render).toHaveAttribute("aria-disabled", "true");
    expect(document.getElementById("render-blocked-reason")).toHaveTextContent("from my_scene.py (in the workspace folder)");
    const banner = screen.getByTestId("other-render");
    expect(banner).toHaveTextContent("Rendering Intro from my_scene.py");
    // Opening it by name would open the browser file of the same name.
    expect(within(banner).queryByRole("button", { name: "Open" })).not.toBeInTheDocument();

    // Its result doesn't land in this file's preview or status either.
    finishWithVideo(socket, id, "my_scene", "Intro");
    expect(await screen.findByText("Intro rendered")).toBeInTheDocument();
    expect(document.querySelector("video")).toBeNull();
    expect(screen.queryByText(/Rendered Intro in/)).not.toBeInTheDocument();
  });
});

describe("R4 #3: renaming a file mid-render keeps the render attached to it", () => {
  it("progress, Cancel, and the result follow the new name, and Render isn't blocked by its own job", async () => {
    const { user, server } = await renderApp();
    const { socket, id } = await startRender(user);
    act(() => socket.emit({ type: "progress", render_id: id, percent: 50, animation: 0 }));

    await user.click(screen.getByRole("button", { name: "Rename example.py" }));
    await user.keyboard("{Control>}a{/Control}renamed{Enter}");
    await waitFor(() => expect(server.scripts).toHaveProperty("renamed.py"));
    await waitFor(() => expect(screen.getByLabelText("Code editor")).toHaveAttribute("data-path", "disk/renamed.py"));

    expect(overlay()).toBeInTheDocument();
    expect(within(overlay()!).getByText("Rendering Intro")).toBeInTheDocument();
    expect(within(editorSection()).getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    expect(screen.queryByTestId("other-render")).not.toBeInTheDocument();

    finishWithVideo(socket, id, "example", "Intro");
    const video = await waitFor(() => {
      const element = document.querySelector("video");
      expect(element).not.toBeNull();
      return element!;
    });
    expect(video.getAttribute("src")).toMatch(/Intro\.mp4/);
    expect(await screen.findByText(/Rendered Intro in/)).toBeInTheDocument();
    expect(within(editorSection()).getByRole("button", { name: "Render" })).not.toHaveAttribute("aria-disabled");
    // Open in new tab works on the landed result.
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    await user.click(screen.getByRole("button", { name: "Open in new tab" }));
    expect(open).toHaveBeenCalledWith(expect.stringMatching(/Intro\.mp4/), "_blank", "noopener,noreferrer");
  });
});

describe("R4 #5: the size banner wins over 'another file is rendering'", () => {
  it("shows the size limit, not the other job, on an oversized file", async () => {
    const diagnostics = { ...structuredClone(DIAGNOSTICS), max_code_bytes: 4000 };
    const { user } = await renderApp({ diagnostics });
    const { socket, id } = await startRender(user);
    act(() => socket.emit({ type: "progress", render_id: id, percent: 10 }));
    await user.click(within(screen.getByRole("list", { name: "Scripts" })).getByRole("button", { name: "notes.py" }));
    await waitFor(() => expect(screen.getByLabelText("Code editor")).toHaveAttribute("data-path", "disk/notes.py"));
    fireEvent.change(screen.getByLabelText("Code editor"), { target: { value: `class Notes(Scene):\n    pass\n${"# pad\n".repeat(1000)}` } });

    await waitFor(() => expect(screen.getAllByRole("note").some((note) => /over the .* limit/.test(note.textContent ?? ""))).toBe(true));
    expect(screen.getAllByRole("note").filter((note) => note.textContent?.includes("Rendering Intro"))).toEqual([]);
    expect(document.getElementById("render-blocked-reason")).toHaveTextContent(/over the .* limit/);
  });
});

describe("R4 #7: the conflict dialog covers changes made outside the app", () => {
  it("says the file may have changed in another program, not only another tab", async () => {
    const { server, editor } = await renderApp();
    server.scripts["example.py"] = `${EXAMPLE_CODE}# edited in vim\n`;
    fireEvent.change(editor, { target: { value: `${EXAMPLE_CODE}# mine\n` } });
    fireEvent.keyDown(window, { key: "s", ctrlKey: true });
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("example.py changed outside this tab");
    expect(dialog).toHaveTextContent(/another program/);
  });
});

describe("R4 #11: focus and announcements", () => {
  it("puts focus in the editor after New script, and its hint doesn't come back", async () => {
    const { user } = await renderApp();
    const newButton = screen.getByRole("button", { name: "New script" });
    await user.hover(newButton);
    await user.click(newButton);
    const input = await screen.findByLabelText("File name");
    await user.clear(input);
    await user.type(input, "fresh");
    await user.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => expect(screen.getByLabelText("Code editor")).toHaveAttribute("data-path", "disk/fresh.py"));
    await waitFor(() => expect(screen.getByLabelText("Code editor")).toHaveFocus());
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("doesn't re-show the New script hint when focus returns after the dialog is cancelled", async () => {
    const { user } = await renderApp();
    // (Keyboard: in jsdom a click lands focus on a resize handle, since every element sits at 0,0.)
    const newButton = screen.getByRole("button", { name: "New script" });
    await user.hover(newButton);
    act(() => newButton.focus());
    await user.keyboard("{Enter}");
    await screen.findByLabelText("File name");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(document.activeElement?.getAttribute("aria-label")).toBe("New script"));
    await act(() => new Promise((resolve) => setTimeout(resolve, 50)));
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("moves focus to Render when Cancel (toolbar or overlay) disappears", async () => {
    const { user } = await renderApp();
    // (Keyboard: in jsdom a click lands focus on a resize handle, since every element sits at 0,0.)
    let { socket, id } = await startRender(user);
    act(() => within(editorSection()).getByRole("button", { name: "Cancel" }).focus());
    await user.keyboard("{Enter}");
    act(() => socket.emit({ type: "result", render_id: id, success: false, status: "cancelled" }));
    await waitFor(() => expect(within(editorSection()).getByRole("button", { name: "Render" })).toHaveFocus());

    ({ socket, id } = await startRender(user));
    act(() => within(overlay()!).getByRole("button", { name: "Cancel" }).focus());
    await user.keyboard("{Enter}");
    act(() => socket.emit({ type: "result", render_id: id, success: false, status: "cancelled" }));
    await waitFor(() => expect(within(editorSection()).getByRole("button", { name: "Render" })).toHaveFocus());
  });

  it("announces milestones only, not every progress tick", async () => {
    const { user } = await renderApp();
    const { socket, id } = await startRender(user);
    const region = screen.getByTestId("render-announcement");
    expect(region).toHaveAttribute("aria-live", "polite");
    expect(overlay()).not.toHaveAttribute("aria-live");
    const heard: string[] = [];
    const listen = () => {
      const text = region.textContent ?? "";
      if (text && heard[heard.length - 1] !== text) heard.push(text);
    };
    listen();
    for (let percent = 1; percent <= 99; percent += 2) {
      act(() => socket.emit({ type: "progress", render_id: id, percent }));
      listen();
    }
    // A dip doesn't announce 50% again.
    act(() => socket.emit({ type: "progress", render_id: id, percent: 40 }));
    listen();
    finishWithVideo(socket, id, "example", "Intro");
    await waitFor(() => expect(region).toHaveTextContent("Intro rendered"));
    listen();
    expect(heard).toEqual(["Rendering Intro", "Rendering Intro: 25%", "Rendering Intro: 50%", "Rendering Intro: 75%", "Intro rendered"]);
  });
});

describe("R4 #13: rename-on-blur leaves legacy names alone", () => {
  for (const [label, name] of [
    ["NFD accents", "cafe\u0301.py"],
    ["a leading NBSP", "\u00a0lead.py"],
    ["an ideographic space", "\u3000wide.py"],
  ] as const) {
    it(`doesn't rename a file with ${label} just because the box lost focus`, async () => {
      const { user, server } = await renderApp({ scripts: { "example.py": EXAMPLE_CODE, [name]: "# legacy\n" } });
      // (By attribute: the accessible-name matcher trims the leading NBSP / U+3000.)
      const rename = screen.getAllByRole("button").find((button) => button.getAttribute("aria-label") === `Rename ${name}`)!;
      await user.click(rename);
      expect(screen.getByLabelText("New file name")).toHaveValue(name);
      await user.click(screen.getByLabelText("Code editor"));
      await waitFor(() => expect(screen.queryByLabelText("New file name")).not.toBeInTheDocument());
      expect(server.calls.filter((call) => call.path === "/api/rename")).toEqual([]);
      expect(server.scripts).toHaveProperty([name]);
    });
  }
});

describe("R4 browser storage in the app", () => {
  async function renderBrowserMode(files: Record<string, string>) {
    localStorage.setItem(STORAGE_KEYS.storageMode, JSON.stringify("browser"));
    for (const [name, content] of Object.entries(files)) writeBrowserFile(name, content);
    return renderApp();
  }

  it("(a) renaming a script another tab deleted offers Recreate and keeps the text", async () => {
    const { user } = await renderBrowserMode({ "a.py": "# a\n", "b.py": "# b\n" });
    await waitFor(() => expect(screen.getByLabelText("Code editor")).toHaveAttribute("data-path", "browser/a.py"));
    fireEvent.change(screen.getByLabelText("Code editor"), { target: { value: "# a, unsaved\n" } });
    // The other tab deletes a.py (no storage event yet: this tab still lists it).
    deleteBrowserFile("a.py");

    await user.click(screen.getByRole("button", { name: "Rename a.py" }));
    await user.keyboard("{Control>}a{/Control}renamed{Enter}");
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("a.py no longer exists");
    expect(readBrowserFile("renamed.py")).toBeUndefined();
    expect(screen.getByLabelText("Code editor")).toHaveValue("# a, unsaved\n");

    await user.click(within(dialog).getByRole("button", { name: "Recreate file" }));
    await waitFor(() => expect(readBrowserFile("a.py")).toBe("# a, unsaved\n"));
  });

  it("(b) refuses a script name that differs only by case from another tab's new script", async () => {
    const { user } = await renderBrowserMode({ "a.py": "# a\n" });
    // Another tab just created Fresh.py; this tab's list doesn't have it yet.
    writeBrowserFile("Fresh.py", "# theirs\n");
    await user.click(screen.getByRole("button", { name: "New script" }));
    const input = await screen.findByLabelText("File name");
    await user.clear(input);
    await user.type(input, "fresh{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("'Fresh.py' already exists. File names that differ only by case are not allowed.");
    expect(Object.keys(loadBrowserFiles()).sort()).toEqual(["Fresh.py", "a.py"]);
  });

  it("(c) deleting the last script shows an empty list instead of the starter, also after a reload", async () => {
    localStorage.setItem(STORAGE_KEYS.storageMode, JSON.stringify("browser"));
    const { user, view } = await renderApp();
    await waitFor(() => expect(screen.getByLabelText("Code editor")).toHaveValue(BROWSER_STARTER));
    await user.click(screen.getByRole("button", { name: "Delete my_scene.py" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete" }));
    expect(await screen.findByText("No scripts in this browser")).toBeInTheDocument();
    expect(screen.getByText("No script open")).toBeInTheDocument();
    expect(localStorage.getItem(browserFileKey("my_scene.py"))).toBeNull();

    view.unmount();
    render(<App />);
    expect(await screen.findByText("No scripts in this browser")).toBeInTheDocument();
    expect(screen.queryByLabelText("Code editor")).not.toBeInTheDocument();
  });
});
