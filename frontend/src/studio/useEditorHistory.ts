import { useCallback, useState } from "react";
import { EditorHistory, isTextEditor } from "./editorHistory";

export function useEditorHistory<T>(initial: T) {
  const [history] = useState(() => new EditorHistory(initial));
  const [snapshot, setSnapshot] = useState(initial);
  const change = useCallback((patch: Partial<T>, remote = false) => {
    const focused = document.activeElement;
    const group = !remote && (isTextEditor(focused) || focused?.matches('input[type="range"], [role="slider"]')) ? focused : null;
    if (!history.change({ ...history.current, ...patch }, group)) return false;
    setSnapshot(history.current);
    return true;
  }, [history]);
  const travel = useCallback((direction: "undo" | "redo") => {
    if (!history[direction]()) return false;
    setSnapshot(history.current);
    return true;
  }, [history]);
  const reset = useCallback((next: T) => {
    history.reset(next);
    setSnapshot(next);
  }, [history]);
  return { snapshot, change, travel, reset, history, canUndo: history.canUndo, canRedo: history.canRedo };
}
