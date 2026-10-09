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
  getOption: () => false,
  getContainerDomNode: () => document.body,
};

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
}));

import CodeEditor from "./CodeEditor";

describe("CodeEditor", () => {
  it("doesn't take focus on load, so the first Tab reaches the skip link", () => {
    render(<CodeEditor path="example.py" value="" onChange={() => {}} />);
    expect(fakeEditor.addAction).toHaveBeenCalled();
    expect(fakeEditor.focus).not.toHaveBeenCalled();
  });
});
