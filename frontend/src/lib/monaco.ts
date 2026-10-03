/**
 * Bundle Monaco with the app instead of loading it from a CDN, so the editor
 * works offline and behind firewalls. Only the Python tokenizer and the base
 * editor worker are needed.
 */
import { loader } from "@monaco-editor/react";
import EditorWorker from "monaco-editor-esm/editor/editor.worker.start.js?worker";
import { monaco } from "./monacoCore";

self.MonacoEnvironment = {
  getWorker: () => new EditorWorker(),
};

export const EDITOR_THEME = "manim-dark";

monaco.editor.defineTheme(EDITOR_THEME, {
  base: "vs-dark",
  inherit: true,
  rules: [
    { token: "", foreground: "ECECF1" },
    { token: "comment", foreground: "7C7C87", fontStyle: "italic" },
    { token: "keyword", foreground: "58C4DD" },
    { token: "string", foreground: "83C167" },
    { token: "string.escape", foreground: "5CD0B3" },
    { token: "number", foreground: "F0AC5F" },
    { token: "delimiter", foreground: "A1A1AB" },
    { token: "type", foreground: "F7D96F" },
    { token: "tag", foreground: "D147BD" },
  ],
  colors: {
    "editor.background": "#0F0F12",
    "editor.foreground": "#ECECF1",
    "editor.lineHighlightBackground": "#16161A",
    "editor.lineHighlightBorder": "#00000000",
    "editor.selectionBackground": "#58C4DD40",
    "editor.inactiveSelectionBackground": "#58C4DD22",
    "editor.selectionHighlightBackground": "#58C4DD1A",
    "editor.wordHighlightBackground": "#FFFFFF10",
    "editorCursor.foreground": "#58C4DD",
    "editorLineNumber.foreground": "#4A4A54",
    "editorLineNumber.activeForeground": "#A1A1AB",
    "editorIndentGuide.background1": "#1F1F25",
    "editorIndentGuide.activeBackground1": "#33333C",
    "editorWhitespace.foreground": "#2A2A31",
    "editorGutter.background": "#0F0F12",
    "editorWidget.background": "#1D1D22",
    "editorWidget.border": "#33333C",
    "editorSuggestWidget.background": "#1D1D22",
    "editorSuggestWidget.border": "#33333C",
    "editorSuggestWidget.selectedBackground": "#2A2A31",
    "editorHoverWidget.background": "#1D1D22",
    "editorHoverWidget.border": "#33333C",
    "editorStickyScroll.background": "#0F0F12",
    "editorStickyScrollHover.background": "#16161A",
    "editorError.foreground": "#FC6255",
    "editorWarning.foreground": "#F0AC5F",
    "scrollbarSlider.background": "#FFFFFF14",
    "scrollbarSlider.hoverBackground": "#FFFFFF24",
    "scrollbarSlider.activeBackground": "#FFFFFF30",
    "focusBorder": "#58C4DD80",
  },
});

loader.config({ monaco });

// Monaco measures glyphs once; re-measure after the web font has loaded.
if (typeof document !== "undefined" && document.fonts) {
  void document.fonts.ready.then(() => monaco.editor.remeasureFonts());
}

export { monaco };
