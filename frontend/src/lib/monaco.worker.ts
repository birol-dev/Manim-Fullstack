// Monaco's base editor worker. Imported via `?worker` from a local file so Vite's
// dependency optimizer doesn't pre-bundle it in dev (which breaks the worker import).
import "monaco-editor-esm/editor/editor.worker.start.js";
