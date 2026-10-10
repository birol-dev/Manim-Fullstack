// R4 #11 follow-up: focus() asked for before Monaco has mounted (the first file of a session,
// e.g. New script from the empty Scripts list) lands once the editor is ready.
import { act, render } from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";

const mounted: { mount: (() => void) | null; focus: ReturnType<typeof vi.fn> } = { mount: null, focus: vi.fn() };

vi.mock("@/lib/monaco", () => ({
  EDITOR_THEME: "test",
  TabFocus: { getTabFocusMode: () => false, onDidChangeTabFocus: () => ({ dispose() {} }) },
  monaco: {
    KeyMod: { CtrlCmd: 1 },
    KeyCode: { KeyS: 1, Enter: 2, Escape: 3 },
    MarkerSeverity: { Error: 8 },
    editor: { EditorOption: { tabFocusMode: 1 }, setModelMarkers: () => {}, getModels: () => [] },
  },
}));

vi.mock("@monaco-editor/react", () => ({
  // Like Monaco: the editor instance arrives (onMount) some time after the component renders.
  default: ({ onMount }: { onMount: (editor: unknown) => void }) => {
    const editor = {
      getModel: () => null,
      addAction: () => {},
      onDidChangeCursorPosition: () => {},
      onDidChangeModel: () => {},
      onDidFocusEditorText: () => {},
      onDidBlurEditorText: () => {},
      onDidChangeConfiguration: () => {},
      onDidDispose: () => {},
      getOption: () => false,
      getContainerDomNode: () => document.body,
      focus: mounted.focus,
    };
    mounted.mount = () => onMount(editor);
    return <div data-testid="monaco" />;
  },
}));

import CodeEditor from "./CodeEditor";
import type { CodeEditorHandle } from "./types";

describe("CodeEditor focus before mount", () => {
  it("focuses the editor once Monaco mounts when focus() came first", () => {
    const ref = createRef<CodeEditorHandle>();
    render(<CodeEditor ref={ref} path="a.py" value="" onChange={() => {}} />);
    act(() => ref.current!.focus());
    expect(mounted.focus).not.toHaveBeenCalled();
    act(() => mounted.mount!());
    expect(mounted.focus).toHaveBeenCalledTimes(1);
  });

  it("doesn't steal focus that moved elsewhere on purpose while it loaded", () => {
    mounted.focus.mockClear();
    const ref = createRef<CodeEditorHandle>();
    render(
      <>
        <button>elsewhere</button>
        <CodeEditor ref={ref} path="b.py" value="" onChange={() => {}} />
      </>,
    );
    act(() => ref.current!.focus());
    act(() => (document.querySelector("button") as HTMLButtonElement).focus());
    act(() => mounted.mount!());
    expect(mounted.focus).not.toHaveBeenCalled();
  });
});
