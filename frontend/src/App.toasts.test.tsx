// Toasts about the open file don't outlive it, and a too-large buffer gets one message, not two.
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/editor/CodeEditor", async () => {
  const { FakeCodeEditor } = await import("@/test/fakeEditor");
  return { default: FakeCodeEditor };
});

import App from "./App";
import { installFakeServer } from "@/test/fakeServer";

const BIG = `from manim import *\nclass Big(Scene):\n    def construct(self):\n        pass\n# ${"y".repeat(400)}\n`;

async function renderBigFile() {
  const server = installFakeServer({ scripts: { "big.py": BIG, "notes.py": "class Notes(Scene):\n    pass\n" } });
  server.diagnostics.max_code_bytes = 200;
  const user = userEvent.setup();
  render(<App />);
  await screen.findByLabelText("Code editor");
  await waitFor(() => expect(screen.getByText("Connected")).toBeInTheDocument());
  await waitFor(() => expect(screen.getByLabelText("Code editor")).toHaveAttribute("data-path", "disk/big.py"));
  return { server, user };
}

const toasts = () => document.querySelectorAll("[data-sonner-toast]");

describe("toasts about the open file", () => {
  it("shows one size message however often Render is tried, and drops it on a file switch", async () => {
    const { user } = await renderBigFile();
    fireEvent.change(screen.getByLabelText("Code editor"), { target: { value: `${BIG}# more\n` } });
    // Typing over the limit: the editor's banner says so, no toast.
    await new Promise((resolve) => setTimeout(resolve, 600));
    expect(toasts()).toHaveLength(0);
    fireEvent.keyDown(window, { key: "Enter", ctrlKey: true });
    expect(await screen.findByText("Can't render this script")).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Enter", ctrlKey: true });
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(toasts()).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: /^notes\.py/ }));
    await waitFor(() => expect(screen.getByLabelText("Code editor")).toHaveAttribute("data-path", "disk/notes.py"));
    await waitFor(() => expect(screen.queryByText("Can't render this script")).not.toBeInTheDocument());
  });
});
