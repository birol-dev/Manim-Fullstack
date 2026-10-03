# Technical reference

How Manim Composer is put together: the backend modules, the REST API, the render WebSocket protocol, and the
frontend architecture.

## Architecture

```mermaid
graph LR
    UI[React app] -- REST: files, save, parse, diagnostics --> API[FastAPI]
    UI -- WebSocket /api/render --> WS[Render session]
    WS -- spawns --> M[manim subprocess]
    M -- stdout / stderr --> EX[ManimExecutor]
    EX -- log, progress, file_ready events --> WS
    API -- serves --> Media[workspace/media]
```

One process serves everything: the built frontend (`frontend/dist`), the API under `/api`, rendered output under
`/media`, and uploads under `/assets`. In development, the Vite dev server proxies those paths to the backend.

## Backend (`backend/`)

| Module               | Responsibility |
| -------------------- | -------------- |
| `main.py`            | Routes, the render WebSocket, temp-render bookkeeping, startup (directory creation, stale temp cleanup, `manim.cfg`). |
| `executor.py`        | `ManimExecutor` runs one Manim process, reads stdout/stderr in chunks (splitting on `\n` and `\r` so tqdm progress streams live), and turns lines into events. Cancels the whole process tree (`killpg` / `taskkill /T`). |
| `scene_parser.py`    | AST analysis: module-level `Scene` subclasses (including subclasses of scenes in the same file) and each scene's `self.play()` / `self.wait()` calls. Results are cached. |
| `origins.py`         | Origin policy for HTTP and WebSocket requests (see [Security](#security)). |
| `diagnostics.py`     | CPU/RAM/GPU detection (cached for 5 minutes), dependency lookup (never cached), render profile, and `workspace/manim.cfg`. |
| `workspace_paths.py` | `safe_basename` / `safe_join`: reject traversal, absolute paths, and Windows device names. |

Manim runs with `COLUMNS=400` (so Rich doesn't wrap output paths), `PYTHONIOENCODING=utf-8`, `PYTHONUNBUFFERED=1`, and
`PYTHONDONTWRITEBYTECODE=1`. If `manim` isn't on `PATH` but the package is importable, the server runs
`python -m manim` instead.

### Render profiles

| Profile       | Chosen when                         | Default quality |
| ------------- | ----------------------------------- | --------------- |
| `eco`         | < 4 threads, < 6 GB RAM, or a container | 480p15 |
| `balanced`    | ≤ 8 threads and ≤ 16 GB RAM          | 720p30 |
| `workstation` | anything bigger                      | 1080p60 |

The profile only sets the default quality in the UI; renders always pass an explicit `-q` flag.

## REST API

All endpoints return JSON. Errors use FastAPI's `{"detail": "..."}` shape.

| Method & path | Body / query | Returns |
| ------------- | ------------ | ------- |
| `GET /api/health` (`/api/status`) | — | `{status, service, version}` |
| `GET /api/diagnostics` | — | Profile, hardware, `platform`, `python_version`, and `dependencies` (`manim`, `ffmpeg`, `latex`, `dvisvgm` paths or `"Not Found"`, plus `latex_available`). |
| `GET /api/files` | — | `{scripts, assets, media}`. Seeds `example.py` if the workspace has no scripts. Media items: `name, size, type ("video"\|"image"), url, path, script, scene, quality, modified`, newest first. |
| `GET /api/file-content` | `?filename=` | `{filename, code, scenes, animations}` |
| `POST /api/parse-code` | `{code}` | `{scenes, animations}` without touching disk |
| `POST /api/save` | `{filename, code}` | `{filename, scenes, animations}` (adds `.py` if missing) |
| `POST /api/rename` | `{old_name, new_name}` | `{old_name, new_name}`; handles case-only renames |
| `DELETE /api/scripts` | `?filename=` | Deletes a script |
| `POST /api/upload-asset` | multipart `file` | `{filename, url}`; images, SVG, audio, and fonts up to 50 MB |
| `DELETE /api/assets` | `?filename=` | Deletes an upload |
| `DELETE /api/media` | `?path=` (relative to `workspace/media`) | Deletes a render and its cached chunks |
| `GET /api/download-temp` | `?path=` | Serves a download-only render once, then deletes it |
| `POST /api/install-manim` \| `-latex` \| `-ffmpeg` | — | Starts `pip install manim` or a `winget` install in the background. Refused (403) in containers or with `MANIM_ALLOW_INSTALLS=0`. |

`animations` maps scene names to steps: `{type: "play" | "wait", label, line, duration?}`. `duration` is a number of
seconds when it is a literal, otherwise the expression's source text.

## Render WebSocket: `/api/render`

Each connection has its own executor, so tabs never interfere. All frames are JSON.

### Client → server

```json
{ "type": "start", "id": "c0ffee", "filename": "example.py", "scene": "Intro",
  "quality": "m", "use_opengl": false, "download_only": false, "code": "..." }
```

- `quality` is one of `l`, `m`, `h`, `k`.
- `code` is optional. When present (unsaved buffer or browser storage) the server renders a scratch copy named
  `_temp_run_<hex>.py`, rewrites that name to `filename` in logs and tracebacks, and moves the output into the
  script's own media folder afterwards.
- `download_only` renders to a scratch folder and returns a one-time `/api/download-temp` URL.
- A new `start` while a render is running cancels the old one.

```json
{ "type": "cancel" }
```

### Server → client

Every event produced for a render carries `render_id` (the `id` from `start`). Clients should ignore events whose
`render_id` doesn't match the render they're waiting for.

| `type` | Fields | Meaning |
| ------ | ------ | ------- |
| `info` | `message` | Lifecycle notes. The first is the command line, prefixed with `$ `. |
| `log` | `stream` (`stdout`/`stderr`), `message` | One line of Manim output, with Rich's source-location column removed. |
| `progress` | `percent`, `animation?`, `label?` | Progress of the current animation (`animation` is the zero-based play/wait index). |
| `file_ready` | `url`, `rel_path`, `filename`, `kind` (`video`/`image`), `is_temp_download?` | The output file. |
| `latex_error_warning` | `message` | LaTeX seems missing or broken (sent at most once per render). |
| `status` | `status`, `message` | `success`, `failed`, or `cancelled`. |
| `error` | `message` | A problem. If it carries a `render_id`, a `result` follows. |
| `result` | `success`, `status`, `details` | Always the last event of a render. `status` is `success`, `failed`, `cancelled`, `timeout`, `error`, or `rejected` (invalid request). |

Every `start` receives exactly one `result`.

## Security

The server executes arbitrary Python, so it has to make sure only the user's own pages can drive it:

- HTTP requests and WebSocket handshakes with an `Origin` header are accepted only from loopback origins
  (`localhost`, `127.0.0.1`, `[::1]`, any port), same-origin requests addressed by IP address (LAN use), or origins in
  `MANIM_ALLOWED_ORIGINS`. Same-origin requests by *hostname* are refused unless listed, which blocks DNS rebinding.
- Requests without an `Origin` header (curl, scripts) are allowed; they can't come from another website.
- File names go through `safe_basename` / `safe_join`; media deletion is limited to `videos/` and `images/`.
- Rendered output never includes host absolute paths (`abs_path` is stripped before events are sent).

## Frontend (`frontend/src/`)

| Path | Contents |
| ---- | -------- |
| `App.tsx` | Composes the layout and wires hooks to components; owns render orchestration (save → parse → start), auto-render, shortcuts, and dialogs. |
| `hooks/useWorkspace.ts` | Files, the editor buffer, per-file unsaved drafts, debounced scene parsing, and file operations for both storage modes. |
| `hooks/useRenderSession.ts` | The render WebSocket: reconnect with backoff, queued start while connecting (8 s timeout), `render_id` filtering. |
| `hooks/useDiagnostics.ts` | Server reachability, the hardware profile, and installer polling. |
| `hooks/useLogs.ts` | Console buffer that commits once per animation frame (Manim can print hundreds of lines a second). |
| `components/` | `layout/` (top bar, activity bar, status bar), `editor/`, `preview/`, `console/`, `sidebar/` panels, `dialogs/`, and `ui/` primitives built on Radix. |
| `lib/` | API client, types, templates, shape-builder code generator, formatting, log line references, localStorage helpers, and the trimmed Monaco build (`monacoCore.ts`). |
| `index.css` | Design tokens (`@theme`): surfaces, text, Manim BLUE accent, and Manim GREEN/GOLD/RED for status. |

Monaco and the LaTeX panel (KaTeX) are lazy-loaded, so the initial bundle stays around 170 KB gzipped.

### Preferences (localStorage)

Keys are prefixed `mc.`: storage mode, quality, save-before-render, download-only, OpenGL, auto-render, loop preview,
editor font size, the open sidebar view, the last open file per storage mode, the selected scene per file, and
browser-stored scripts. Pane sizes are remembered by `react-resizable-panels`. Keys from earlier versions are migrated
on first read.

## Tests

- `tests/` — pytest suite for the API, executor, parser, origin policy, paths, and diagnostics.
  `test_e2e_real_render.py` drives real renders through the WebSocket and is skipped when Manim isn't installed.
- `frontend/src/**/*.test.ts(x)` — Vitest + Testing Library. `src/test/` provides a fake backend (`fakeServer.ts`), a
  scriptable WebSocket (`fakeSocket.ts`), and a textarea stand-in for Monaco (`fakeEditor.tsx`).
