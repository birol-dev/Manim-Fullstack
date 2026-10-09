export type InsertMode = "inline" | "block";

export interface CodeEditorHandle {
  /**
   * Insert *text* at the cursor ("inline"), or as whole lines below the cursor
   * indented to fit the surrounding code ("block"). Returns false if the editor
   * is not ready, or `{ refused }` with the reason when the code can't go
   * there (e.g. the cursor is inside a string that never ends).
   */
  insertText(text: string, mode: InsertMode): boolean | { refused: string };
  revealLine(lineNumber: number): void;
  setErrorMarker(lineNumber: number, message: string): void;
  clearMarkers(): void;
  focus(): void;
}

export interface CodeEditorProps {
  /** Model path; each file keeps its own undo history. */
  path: string;
  value: string;
  onChange: (value: string) => void;
  onCursorChange?: (position: { line: number; column: number }) => void;
  onSave?: () => void;
  onRender?: () => void;
  fontSize?: number;
  /** Live Python syntax error, shown as a squiggle independent of render errors. */
  syntaxError?: { line: number; message: string } | null;
}
