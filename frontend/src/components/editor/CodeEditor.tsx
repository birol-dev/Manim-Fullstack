import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import Editor, { type OnMount } from "@monaco-editor/react";

import { EDITOR_THEME, monaco } from "@/lib/monaco";
import type { CodeEditorHandle, CodeEditorProps } from "./types";

type StandaloneEditor = Parameters<OnMount>[0];

const MARKER_OWNER = "manim-render";

function leadingWhitespace(line: string): string {
  return line.match(/^\s*/)?.[0] ?? "";
}

/** Indentation for a block inserted on (blank) line *lineNumber*, from the code above it. */
function contextIndent(model: monaco.editor.ITextModel, lineNumber: number): string {
  for (let line = lineNumber - 1; line >= 1; line -= 1) {
    const text = model.getLineContent(line);
    if (!text.trim()) continue;
    const indent = leadingWhitespace(text);
    return text.trimEnd().endsWith(":") ? `${indent}    ` : indent;
  }
  return "";
}

function indentBlock(block: string, indent: string): string {
  return block
    .split("\n")
    .map((line) => (line ? indent + line : line))
    .join("\n");
}

const CodeEditor = forwardRef<CodeEditorHandle, CodeEditorProps>(function CodeEditor(
  { path, value, onChange, onCursorChange, onSave, onRender, fontSize = 13 },
  ref,
) {
  const editorRef = useRef<StandaloneEditor | null>(null);
  // Keyboard actions are registered once; read the latest callbacks through refs.
  const saveRef = useRef(onSave);
  const renderRef = useRef(onRender);
  const cursorRef = useRef(onCursorChange);
  useEffect(() => {
    saveRef.current = onSave;
    renderRef.current = onRender;
    cursorRef.current = onCursorChange;
  });

  useImperativeHandle(ref, () => ({
    insertText(text, mode) {
      const editor = editorRef.current;
      const model = editor?.getModel();
      const selection = editor?.getSelection();
      if (!editor || !model || !selection) return false;

      if (mode === "inline") {
        editor.executeEdits("insert", [{ range: selection, text, forceMoveMarkers: true }]);
      } else {
        const lineNumber = selection.positionLineNumber;
        const lineText = model.getLineContent(lineNumber);
        const endColumn = model.getLineMaxColumn(lineNumber);
        if (lineText.trim()) {
          // Below the current line, matching its indentation (one level deeper after a colon).
          const indent = leadingWhitespace(lineText) + (lineText.trimEnd().endsWith(":") ? "    " : "");
          const range = new monaco.Range(lineNumber, endColumn, lineNumber, endColumn);
          editor.executeEdits("insert", [{ range, text: `\n${indentBlock(text, indent)}`, forceMoveMarkers: true }]);
        } else {
          const range = new monaco.Range(lineNumber, 1, lineNumber, endColumn);
          editor.executeEdits("insert", [
            { range, text: indentBlock(text, contextIndent(model, lineNumber)), forceMoveMarkers: true },
          ]);
        }
      }
      editor.pushUndoStop();
      editor.revealPositionInCenterIfOutsideViewport(editor.getPosition() ?? selection.getPosition());
      editor.focus();
      return true;
    },
    revealLine(lineNumber) {
      const editor = editorRef.current;
      if (!editor) return;
      editor.setPosition({ lineNumber, column: 1 });
      editor.revealLineInCenter(lineNumber);
      editor.focus();
    },
    setErrorMarker(lineNumber, message) {
      const model = editorRef.current?.getModel();
      if (!model || lineNumber < 1 || lineNumber > model.getLineCount()) return;
      monaco.editor.setModelMarkers(model, MARKER_OWNER, [
        {
          severity: monaco.MarkerSeverity.Error,
          message,
          startLineNumber: lineNumber,
          endLineNumber: lineNumber,
          startColumn: model.getLineFirstNonWhitespaceColumn(lineNumber) || 1,
          endColumn: model.getLineMaxColumn(lineNumber),
        },
      ]);
    },
    clearMarkers() {
      for (const model of monaco.editor.getModels()) monaco.editor.setModelMarkers(model, MARKER_OWNER, []);
    },
    focus() {
      editorRef.current?.focus();
    },
  }));

  const handleMount: OnMount = (editor) => {
    editorRef.current = editor;
    editor.addAction({
      id: "manim.save",
      label: "Save File",
      keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS],
      run: () => saveRef.current?.(),
    });
    editor.addAction({
      id: "manim.render",
      label: "Render Scene",
      keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter],
      contextMenuGroupId: "navigation",
      run: () => renderRef.current?.(),
    });
    editor.onDidChangeCursorPosition((event) =>
      cursorRef.current?.({ line: event.position.lineNumber, column: event.position.column }),
    );
    editor.focus();
  };

  return (
    <Editor
      path={path}
      value={value}
      language="python"
      theme={EDITOR_THEME}
      onChange={(next) => onChange(next ?? "")}
      onMount={handleMount}
      loading={<div className="h-full w-full bg-surface" />}
      options={{
        fontFamily: "'JetBrains Mono Variable', ui-monospace, Menlo, Consolas, monospace",
        fontSize,
        lineHeight: Math.round(fontSize * 1.6),
        fontLigatures: false,
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        automaticLayout: true,
        tabSize: 4,
        insertSpaces: true,
        wordWrap: "on",
        wrappingIndent: "indent",
        padding: { top: 12, bottom: 12 },
        renderLineHighlight: "line",
        cursorBlinking: "smooth",
        cursorSmoothCaretAnimation: "on",
        smoothScrolling: true,
        stickyScroll: { enabled: true, maxLineCount: 3 },
        guides: { indentation: true, bracketPairs: false },
        bracketPairColorization: { enabled: false },
        overviewRulerBorder: false,
        hideCursorInOverviewRuler: true,
        scrollbar: { verticalScrollbarSize: 10, horizontalScrollbarSize: 10, useShadows: false },
        fixedOverflowWidgets: true,
        "semanticHighlighting.enabled": false,
      }}
    />
  );
});

export default CodeEditor;
