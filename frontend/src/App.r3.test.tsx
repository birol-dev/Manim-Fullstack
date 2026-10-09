// Fix round 3: files whose names the filename rule now forbids say "rename this file"
// on save and render instead of failing quietly.
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/editor/CodeEditor", async () => {
  const { FakeCodeEditor } = await import("@/test/fakeEditor");
  return { default: FakeCodeEditor };
});

import App from "./App";
import { EXAMPLE_CODE, installFakeServer } from "@/test/fakeServer";
import { FakeWebSocket } from "@/test/fakeSocket";

const LEGACY = "-legacy.py";
const RENAME = "Rename this file to save or render it: Filename cannot start with a dash.";

async function renderLegacyApp() {
  const server = installFakeServer({ scripts: { [LEGACY]: EXAMPLE_CODE } });
  const user = userEvent.setup();
  render(<App />);
  const editor = (await screen.findByLabelText("Code editor")) as HTMLTextAreaElement;
  await waitFor(() => expect(screen.getByText("Connected")).toBeInTheDocument());
  await waitFor(() => expect(editor.value).toBe(EXAMPLE_CODE));
  return { server, user, editor };
}

afterEach(() => {
  vi.useRealTimers();
});

describe("existing files with a now-forbidden name", () => {
  it("opens the file, and a refused render explains that it must be renamed", async () => {
    const { user } = await renderLegacyApp();
    await user.click(screen.getAllByRole("button", { name: "Render" })[0]);
    const socket = FakeWebSocket.latest();
    await waitFor(() => expect(socket.sent.some((message) => message.type === "start")).toBe(true));
    const id = socket.lastSent("start").id as string;
    act(() => {
      socket.emit({ type: "error", render_id: id, message: RENAME });
      socket.emit({ type: "result", render_id: id, success: false, status: "rejected" });
    });
    // In the toast (not just "see the console") and in the console.
    await waitFor(() => {
      const toast = [...document.querySelectorAll("[data-sonner-toast]")].find((node) =>
        node.textContent?.includes("didn't render"),
      );
      expect(toast?.textContent).toContain(RENAME);
    });
    await waitFor(() => expect(screen.getByRole("log")).toHaveTextContent(RENAME));
  });

  it("shows the server's rename message when saving fails", async () => {
    const { server, editor } = await renderLegacyApp();
    server.failures["/api/save"] = RENAME;
    fireEvent.change(editor, { target: { value: "# edited" } });
    fireEvent.keyDown(window, { key: "s", ctrlKey: true });
    expect(await screen.findByText(RENAME)).toBeInTheDocument();
  });
});
