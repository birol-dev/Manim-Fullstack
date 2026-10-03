export type InsertMode = "inline" | "block";

export interface CodeEditorHandle {
  /**
   * Insert *text* at the cursor ("inline"), or as whole lines below the cursor
   * indented to fit the surrounding code ("block"). Returns false if the editor
   * is not ready.
   */
  insertText(text: string, mode: InsertMode): boolean;
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
}
