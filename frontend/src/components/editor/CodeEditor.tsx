import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import Editor, { type OnMount } from "@monaco-editor/react";

import { IS_MAC } from "@/lib/constants";
import { focusNextAfter } from "@/lib/focus";
import { planBlockInsert } from "@/lib/insert";
import { EDITOR_THEME, monaco } from "@/lib/monaco";
import type { CodeEditorHandle, CodeEditorProps } from "./types";

type StandaloneEditor = Parameters<OnMount>[0];

const MARKER_OWNER = "manim-render";
const TAB_FOCUS_KEY = IS_MAC ? "⌃⇧M" : "Ctrl+M";
// Escape leaves the editor unless Monaco needs it (closing a widget, a selection, extra cursors...).
const LEAVE_EDITOR_WHEN = [
  "!suggestWidgetVisible",
  "!findWidgetVisible",
  "!parameterHintsVisible",
  "!renameInputVisible",
  "!editorHoverVisible",
  "!editorHasSelection",
  "!editorHasMultipleSelections",
  "!inSnippetMode",
  "!markersNavigationVisible",
  "!referenceSearchVisible",
  "!inlineSuggestionVisible",
].join(" && ");
const SYNTAX_OWNER = "manim-syntax";

function applySyntaxMarker(editor: StandaloneEditor | null, marker: { line: number; message: string } | null) {
  const model = editor?.getModel();
  if (!model) return;
  if (!marker || marker.line < 1 || marker.line > model.getLineCount()) {
    monaco.editor.setModelMarkers(model, SYNTAX_OWNER, []);
    return;
  }
  monaco.editor.setModelMarkers(model, SYNTAX_OWNER, [
    {
      severity: monaco.MarkerSeverity.Error,
      message: marker.message,
      startLineNumber: marker.line,
      endLineNumber: marker.line,
      startColumn: model.getLineFirstNonWhitespaceColumn(marker.line) || 1,
      endColumn: model.getLineMaxColumn(marker.line),
    },
  ]);
}

const CodeEditor = forwardRef<CodeEditorHandle, CodeEditorProps>(function CodeEditor(
  { path, value, onChange, onCursorChange, onSave, onRender, fontSize = 13, syntaxError = null },
  ref,
) {
  const editorRef = useRef<StandaloneEditor | null>(null);
  const [focused, setFocused] = useState(false);
  const [tabFocusMode, setTabFocusMode] = useState(false);
  // Keyboard actions are registered once; read the latest callbacks through refs.
  const saveRef = useRef(onSave);
  const renderRef = useRef(onRender);
  const cursorRef = useRef(onCursorChange);
  const syntaxRef = useRef(syntaxError);
  useEffect(() => {
    saveRef.current = onSave;
    renderRef.current = onRender;
    cursorRef.current = onCursorChange;
    syntaxRef.current = syntaxError;
  });
  useEffect(() => {
    applySyntaxMarker(editorRef.current, syntaxError);
  }, [syntaxError, path]);

  useImperativeHandle(ref, () => ({
    insertText(text, mode) {
      const editor = editorRef.current;
      const model = editor?.getModel();
      const selection = editor?.getSelection();
      if (!editor || !model || !selection) return false;

      if (mode === "inline") {
        editor.executeEdits("insert", [{ range: selection, text, forceMoveMarkers: true }]);
      } else {
        const plan = planBlockInsert(model.getLinesContent(), selection.positionLineNumber, text);
        const endColumn = model.getLineMaxColumn(plan.line);
        const range = plan.replace
          ? new monaco.Range(plan.line, 1, plan.line, endColumn)
          : new monaco.Range(plan.line, endColumn, plan.line, endColumn);
        // Leave the cursor after the inserted code, wherever it went.
        editor.executeEdits("insert", [{ range, text: plan.replace ? plan.text : `\n${plan.text}`, forceMoveMarkers: true }], (inverse) => {
          const end = inverse[0]?.range;
          return end ? [new monaco.Selection(end.endLineNumber, end.endColumn, end.endLineNumber, end.endColumn)] : null;
        });
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
    applySyntaxMarker(editor, syntaxRef.current);
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
    editor.addAction({
      id: "manim.leaveEditor",
      label: "Move Focus Out of the Editor",
      keybindings: [monaco.KeyCode.Escape],
      precondition: LEAVE_EDITOR_WHEN,
      run: () => {
        focusNextAfter(editor.getContainerDomNode());
      },
    });
    editor.onDidChangeCursorPosition((event) =>
      cursorRef.current?.({ line: event.position.lineNumber, column: event.position.column }),
    );
    // Another file's model: report where its cursor is instead of keeping the old position.
    editor.onDidChangeModel(() => {
      const position = editor.getPosition();
      if (position) cursorRef.current?.({ line: position.lineNumber, column: position.column });
    });
    editor.onDidFocusEditorText(() => setFocused(true));
    editor.onDidBlurEditorText(() => setFocused(false));
    editor.onDidChangeConfiguration((event) => {
      if (event.hasChanged(monaco.editor.EditorOption.tabFocusMode)) {
        setTabFocusMode(editor.getOption(monaco.editor.EditorOption.tabFocusMode));
      }
    });
    setTabFocusMode(editor.getOption(monaco.editor.EditorOption.tabFocusMode));
    editor.focus();
  };

  return (
    <div className="relative h-full">
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
          ariaLabel: `Python code editor. Press Escape to move focus out of the editor, or ${TAB_FOCUS_KEY} to make Tab move focus.`,
        }}
      />
      {focused && (
        <div
          aria-hidden="true"
          data-testid="editor-focus-hint"
          className="pointer-events-none absolute bottom-1.5 right-4 z-10 rounded border border-line bg-raised/90 px-1.5 py-0.5 font-sans text-2xs text-fg-subtle"
        >
          {tabFocusMode ? `Tab moves focus · ${TAB_FOCUS_KEY} to indent with Tab` : `Esc leaves the editor · ${TAB_FOCUS_KEY}: Tab moves focus`}
        </div>
      )}
    </div>
  );
});

export default CodeEditor;
