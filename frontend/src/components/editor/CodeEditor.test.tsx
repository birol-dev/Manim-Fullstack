// The real CodeEditor's mount wiring, with Monaco itself stubbed out.
import { render } from "@testing-library/react";
import { useEffect } from "react";
import { describe, expect, it, vi } from "vitest";

const fakeEditor = {
  focus: vi.fn(),
  getModel: () => null,
  addAction: vi.fn(),
  onDidChangeCursorPosition: vi.fn(),
  onDidChangeModel: vi.fn(),
  onDidFocusEditorText: vi.fn(),
  onDidBlurEditorText: vi.fn(),
  onDidChangeConfiguration: vi.fn(),
  onDidDispose: vi.fn(),
  getOption: () => false,
  getContainerDomNode: () => document.body,
};

const tabFocus = vi.hoisted(() => {
  let mode = false;
  const listeners: Array<(value: boolean) => void> = [];
  return {
    getTabFocusMode: () => mode,
    setTabFocusMode(value: boolean) {
      mode = value;
      listeners.forEach((listener) => listener(value));
    },
    onDidChangeTabFocus(listener: (value: boolean) => void) {
      listeners.push(listener);
      return { dispose: () => listeners.splice(listeners.indexOf(listener), 1) };
    },
  };
});

vi.mock("@monaco-editor/react", () => ({
  default: function Editor({ onMount }: { onMount: (editor: unknown, monaco: unknown) => void }) {
    useEffect(() => onMount(fakeEditor, {}), [onMount]);
    return <div data-testid="monaco" />;
  },
}));

vi.mock("@/lib/monaco", () => ({
  EDITOR_THEME: "test",
  monaco: {
    KeyMod: { CtrlCmd: 0 },
    KeyCode: { KeyS: 0, Enter: 0, Escape: 0 },
    editor: { EditorOption: { tabFocusMode: 0 }, setModelMarkers: vi.fn(), getModels: () => [] },
    MarkerSeverity: { Error: 8 },
  },
  TabFocus: tabFocus,
}));

import { act, screen } from "@testing-library/react";

import CodeEditor from "./CodeEditor";

describe("CodeEditor", () => {
  it("doesn't take focus on load, so the first Tab reaches the skip link", () => {
    render(<CodeEditor path="example.py" value="" onChange={() => {}} />);
    expect(fakeEditor.addAction).toHaveBeenCalled();
    expect(fakeEditor.focus).not.toHaveBeenCalled();
  });

  it("updates the hint chip when Ctrl+M toggles Tab focus mode (Monaco's global TabFocus)", () => {
    render(<CodeEditor path="example.py" value="" onChange={() => {}} />);
    const onFocus = fakeEditor.onDidFocusEditorText.mock.calls.at(-1)?.[0] as () => void;
    act(() => onFocus());
    expect(screen.getByTestId("editor-focus-hint")).toHaveTextContent("Esc leaves the editor · Ctrl+M: Tab moves focus");
    act(() => tabFocus.setTabFocusMode(true));
    expect(screen.getByTestId("editor-focus-hint")).toHaveTextContent("Tab moves focus · Ctrl+M to indent");
    act(() => tabFocus.setTabFocusMode(false));
    expect(screen.getByTestId("editor-focus-hint")).toHaveTextContent("Esc leaves the editor");
  });
});
