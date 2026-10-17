// Switching Workspace <-> Browser storage closes the open buffer, so unsaved edits
// (including text kept after a file vanished and Recreate was cancelled) are asked about.
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/editor/CodeEditor", async () => {
  const { FakeCodeEditor } = await import("@/test/fakeEditor");
  return { default: FakeCodeEditor };
});

import App from "./App";
import { installFakeServer } from "@/test/fakeServer";
import { STORAGE_KEYS, deleteBrowserFile, readBrowserFile, writeBrowserFile } from "@/lib/storage";

type Overrides = Parameters<typeof installFakeServer>[0];

async function renderApp(overrides?: Overrides) {
  const server = installFakeServer(overrides);
  const user = userEvent.setup();
  render(<App />);
  await screen.findByLabelText("Code editor");
  await waitFor(() => expect(screen.getByText("Connected")).toBeInTheDocument());
  return { server, user };
}

const codeEditor = () => screen.getByLabelText("Code editor") as HTMLTextAreaElement;
const editorSection = () => screen.getByRole("region", { name: "Editor" });
const radio = (name: "Browser" | "Workspace") => screen.getByRole("radio", { name: name === "Browser" ? "Browser" : /Workspace/ });

async function openSettings(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Settings" }));
}

async function diskWithEdit() {
  const ctx = await renderApp({ scripts: { "a.py": "# disk a\n" } });
  await waitFor(() => expect(codeEditor()).toHaveAttribute("data-path", "disk/a.py"));
  fireEvent.change(codeEditor(), { target: { value: "# disk a, edited\n" } });
  await openSettings(ctx.user);
  await ctx.user.click(radio("Browser"));
  const dialog = await screen.findByRole("dialog");
  expect(dialog).toHaveTextContent("Save changes to a.py?");
  return { ...ctx, dialog };
}

describe("storage switch guard", () => {
  it("switches at once when nothing is unsaved", async () => {
    const { user } = await renderApp({ scripts: { "a.py": "# disk a\n" } });
    await waitFor(() => expect(codeEditor()).toHaveAttribute("data-path", "disk/a.py"));
    await openSettings(user);
    await user.click(radio("Browser"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() => expect(radio("Browser")).toHaveAttribute("aria-checked", "true"));
  });

  it("Cancel keeps the mode, the edits, and puts focus back on the storage control", async () => {
    const { user, server, dialog } = await diskWithEdit();
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(radio("Workspace")).toHaveAttribute("aria-checked", "true");
    expect(radio("Browser")).toHaveAttribute("aria-checked", "false");
    expect(JSON.parse(localStorage.getItem(STORAGE_KEYS.storageMode) ?? '"disk"')).toBe("disk");
    expect(codeEditor()).toHaveValue("# disk a, edited\n");
    expect(server.scripts["a.py"]).toBe("# disk a\n");
    await waitFor(() => expect(document.activeElement?.closest('[aria-label="Where scripts are stored"]')).not.toBeNull());
  });

  it("Save writes the file, then switches", async () => {
    const { user, server, dialog } = await diskWithEdit();
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(server.scripts["a.py"]).toBe("# disk a, edited\n"));
    await waitFor(() => expect(radio("Browser")).toHaveAttribute("aria-checked", "true"));
  });

  it("Discard drops the edits, then switches (coming back shows the saved file, no prompt)", async () => {
    const { user, server, dialog } = await diskWithEdit();
    await user.click(within(dialog).getByRole("button", { name: "Discard" }));
    await waitFor(() => expect(radio("Browser")).toHaveAttribute("aria-checked", "true"));
    expect(server.scripts["a.py"]).toBe("# disk a\n");
    await user.click(radio("Workspace"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() => expect(codeEditor()).toHaveAttribute("data-path", "disk/a.py"));
    expect(codeEditor()).toHaveValue("# disk a\n");
  });

  it("asks about a buffer kept after Recreate was cancelled, and Save recreates it before switching", async () => {
    localStorage.setItem(STORAGE_KEYS.storageMode, JSON.stringify("browser"));
    writeBrowserFile("a.py", "# a\n");
    writeBrowserFile("b.py", "# b\n");
    const { user } = await renderApp();
    await waitFor(() => expect(codeEditor()).toHaveAttribute("data-path", "browser/a.py"));
    fireEvent.change(codeEditor(), { target: { value: "# a, kept\n" } });
    deleteBrowserFile("a.py"); // another tab deleted it
    await user.click(within(editorSection()).getByRole("button", { name: "Save" }));
    const missing = await screen.findByRole("dialog");
    expect(missing).toHaveTextContent("a.py no longer exists");
    await user.click(within(missing).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(codeEditor()).toHaveValue("# a, kept\n");

    await openSettings(user);
    await user.click(radio("Workspace"));
    const guard = await screen.findByRole("dialog");
    expect(guard).toHaveTextContent("Save changes to a.py?");
    await user.click(within(guard).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(readBrowserFile("a.py")).toBe("# a, kept\n"));
    await waitFor(() => expect(radio("Workspace")).toHaveAttribute("aria-checked", "true"));
  });
});
