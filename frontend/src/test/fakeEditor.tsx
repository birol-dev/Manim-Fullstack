// Test helper, never hot-reloaded.
/* eslint-disable react-refresh/only-export-components */
import { forwardRef, useImperativeHandle, useRef } from "react";

import type { CodeEditorHandle, CodeEditorProps } from "@/components/editor/types";

/** Calls made on the editor handle, for assertions. */
export const editorCalls: Array<[string, ...unknown[]]> = [];

/** A textarea standing in for Monaco (which can't run in jsdom). */
export const FakeCodeEditor = forwardRef<CodeEditorHandle, CodeEditorProps>(function FakeCodeEditor(props, ref) {
  const textarea = useRef<HTMLTextAreaElement>(null);
  const latest = useRef(props);
  latest.current = props;

  useImperativeHandle(ref, () => ({
    insertText(text, mode) {
      editorCalls.push(["insert", text, mode]);
      const current = latest.current.value;
      latest.current.onChange(mode === "block" ? `${current.replace(/\n*$/, "")}\n${text}\n` : current + text);
      return true;
    },
    revealLine(line) {
      editorCalls.push(["reveal", line]);
    },
    setErrorMarker(line, message) {
      editorCalls.push(["marker", line, message]);
    },
    clearMarkers() {
      editorCalls.push(["clearMarkers"]);
    },
    focus() {
      textarea.current?.focus();
    },
  }));

  return (
    <textarea
      ref={textarea}
      aria-label="Code editor"
      data-path={props.path}
      value={props.value}
      onChange={(event) => props.onChange(event.target.value)}
      onKeyDown={(event) => {
        if ((event.ctrlKey || event.metaKey) && event.key === "Enter") props.onRender?.();
      }}
    />
  );
});
