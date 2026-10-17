// Settings changed in another tab apply here without a reload; a storage switch there is
// followed only when it closes nothing unsaved here.
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/editor/CodeEditor", async () => {
  const { FakeCodeEditor } = await import("@/test/fakeEditor");
  return { default: FakeCodeEditor };
});

import App from "./App";
import { installFakeServer } from "@/test/fakeServer";
import { STORAGE_KEYS, writeBrowserFile } from "@/lib/storage";

async function renderApp() {
  installFakeServer({ scripts: { "a.py": "# disk a\n" } });
  writeBrowserFile("b.py", "# browser b\n");
  const user = userEvent.setup();
  render(<App />);
  await screen.findByLabelText("Code editor");
  await waitFor(() => expect(screen.getByText("Connected")).toBeInTheDocument());
  await waitFor(() => expect(codeEditor()).toHaveAttribute("data-path", "disk/a.py"));
  return { user };
}

const codeEditor = () => screen.getByLabelText("Code editor") as HTMLTextAreaElement;

/** What the browser does in this tab when another tab stores *value* under *key*. */
function otherTabStores(key: string, value: unknown) {
  const newValue = JSON.stringify(value);
  const oldValue = localStorage.getItem(key);
  localStorage.setItem(key, newValue);
  act(() => {
    window.dispatchEvent(new StorageEvent("storage", { key, oldValue, newValue, storageArea: localStorage }));
  });
}

describe("another tab", () => {
  it("switching storage switches this tab too when nothing is unsaved", async () => {
    await renderApp();
    otherTabStores(STORAGE_KEYS.storageMode, "browser");
    await waitFor(() => expect(codeEditor()).toHaveAttribute("data-path", "browser/b.py"));
    expect(await screen.findByText("Switched to browser storage")).toBeInTheDocument();
  });

  it("switching storage leaves unsaved edits here open, and Switch asks about them", async () => {
    const { user } = await renderApp();
    fireEvent.change(codeEditor(), { target: { value: "# disk a, edited\n" } });
    otherTabStores(STORAGE_KEYS.storageMode, "browser");
    expect(await screen.findByText("Another tab switched to browser storage")).toBeInTheDocument();
    expect(codeEditor()).toHaveAttribute("data-path", "disk/a.py");
    expect(codeEditor()).toHaveValue("# disk a, edited\n");

    await user.click(screen.getByRole("button", { name: "Switch" }));
    expect(await screen.findByRole("dialog")).toHaveTextContent("Save changes to a.py?");
  });

  it("changing the quality changes it here", async () => {
    await renderApp();
    expect(screen.getByRole("combobox", { name: /Quality/ })).toHaveTextContent("720p");
    otherTabStores(STORAGE_KEYS.quality, "h");
    await waitFor(() => expect(screen.getByRole("combobox", { name: /Quality/ })).toHaveTextContent("1080p"));
  });

  it("an unrelated or removed key changes nothing", async () => {
    await renderApp();
    const info = vi.spyOn(toast, "info");
    const warning = vi.spyOn(toast, "warning");
    localStorage.removeItem(STORAGE_KEYS.storageMode);
    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key: STORAGE_KEYS.storageMode, newValue: null, storageArea: localStorage }));
      window.dispatchEvent(new StorageEvent("storage", { key: null, storageArea: localStorage }));
    });
    expect(codeEditor()).toHaveAttribute("data-path", "disk/a.py");
    expect(info).not.toHaveBeenCalled();
    expect(warning).not.toHaveBeenCalled();
  });
});
