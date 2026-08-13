# Bugfix log

Scope: entire repo (`backend/`, `frontend/`, `website/`)  
Cap: 10 iterations  
Stopped: full pass with zero new confirmed bugs (lint clean, unit tests passing, frontend build passing)

---

## [Iteration 1] Workspace path traversal on file APIs
- File(s): `backend/workspace_paths.py`, `backend/main.py`, `tests/test_workspace_paths.py`
- Severity: blocker
- Root cause: `filename` / upload names were joined onto workspace paths with no sanitization, so `../` (and Windows `..\\`) could read or write outside `workspace/`.
- Fix: Added `safe_basename` / `safe_join` / `is_within_directory` and applied them to save, rename, file-content, upload, and download-temp.
- Test added/updated: `tests/test_workspace_paths.py`
- Verified: `python -m unittest discover -s tests -t . -v` (OK)

## [Iteration 1] Download-temp `startswith` prefix bypass
- File(s): `backend/main.py`, `backend/workspace_paths.py`
- Severity: blocker
- Root cause: `abs_path.startswith(MEDIA_DIR)` treats sibling dirs such as `media_backup` as inside `media`.
- Fix: Resolve paths with `Path.is_relative_to` via `safe_join`.
- Test added/updated: `tests/test_workspace_paths.py` (`test_rejects_sibling_prefix_directory`)
- Verified: unittest OK

## [Iteration 1] Blocking `time.sleep` in async renderer
- File(s): `backend/executor.py`
- Severity: major
- Root cause: Fallback “file ready” scan used `time.sleep(1.0)` inside an async FastAPI handler, freezing the event loop.
- Fix: `await asyncio.sleep(1.0)`.
- Test added/updated: none needed (behavior-preserving timing change)
- Verified: `python -m compileall backend`

## [Iteration 1] Orphaned Manim process on executor errors
- File(s): `backend/executor.py`
- Severity: major
- Root cause: On exception, `current_process` was left running; the next `execute()` nulled the handle without killing the child.
- Fix: Cancel any live process at start of `execute()` and in the exception path.
- Test added/updated: none needed, existing execute flow covers it
- Verified: compileall OK

## [Iteration 1] Unix cancel left ffmpeg children alive
- File(s): `backend/executor.py`
- Severity: major
- Root cause: Cancel only called `terminate()` on the parent; Manim’s ffmpeg children could survive.
- Fix: `start_new_session=True` plus `os.killpg` (SIGTERM, then SIGKILL).
- Test added/updated: none needed
- Verified: compileall OK

## [Iteration 1] Latest-render fallback matched scene name prefixes
- File(s): `backend/executor.py`, `tests/test_executor.py`
- Severity: major
- Root cause: `filename.startswith(scene_name)` treated `SceneExtra.mp4` as `Scene`.
- Fix: Compare the file stem exactly to the scene name; ignore non-video “File ready at” lines.
- Test added/updated: `tests/test_executor.py`
- Verified: unittest OK

## [Iteration 1] WebSocket JSON / render validation / installer status codes
- File(s): `backend/main.py`
- Severity: major
- Root cause: `json.loads` had no guard (one bad frame dropped the socket loop). Missing winget raised `HTTPException` that was caught and re-wrapped as 500. Render start accepted empty/unsafe names.
- Fix: Catch `JSONDecodeError`; re-raise `HTTPException`; require a `.py` basename and a Python identifier scene name; URL-quote download-temp paths.
- Test added/updated: none needed, existing test covers path helpers used here
- Verified: compileall OK

## [Iteration 2] React StrictMode WebSocket race
- File(s): `frontend/src/App.tsx`
- Severity: blocker
- Root cause: `onclose` always set `wsRef.current = null`, so the first socket’s close (StrictMode remount or retry) cleared a newer live connection.
- Fix: Close any previous socket before connecting; only clear the ref if it still points at that socket.
- Test added/updated: none needed (no frontend test runner)
- Verified: `npm --prefix frontend run lint` and `npm --prefix frontend run build`

## [Iteration 2] Snippet insert replaced the whole buffer
- File(s): `frontend/src/App.tsx`
- Severity: major
- Root cause: `window.monaco` was assigned in a mount effect that never re-ran after the editor mounted, so inserts fell through. `getSelection()` can also be null.
- Fix: Store monaco from `onMount`; insert at selection or cursor; append instead of replacing if the editor is not ready.
- Test added/updated: none needed
- Verified: frontend lint + build

## [Iteration 2] Empty editor contents reloaded from disk
- File(s): `frontend/src/App.tsx`
- Severity: major
- Root cause: Auto-loader treated `code === ""` as “not loaded yet”, so clearing a file re-fetched it.
- Fix: Track the last loaded filename in a ref and only auto-load on a real file switch.
- Test added/updated: none needed
- Verified: frontend lint + build

## [Iteration 2] Diagnostics poll reset render quality
- File(s): `frontend/src/App.tsx`
- Severity: major
- Root cause: Every diagnostics fetch (including 3s installer polling) overwrote the quality dropdown from the hardware profile.
- Fix: Apply the profile default only on the first successful diagnostics load.
- Test added/updated: none needed
- Verified: frontend lint + build

## [Iteration 2] Blob URL leaks, unencoded filenames, empty Radix Select
- File(s): `frontend/src/App.tsx`
- Severity: minor
- Root cause: Download-only object URLs were never revoked; `filename` query params were not encoded; `value=""` is illegal for Radix Select.
- Fix: Revoke previous blob URLs; `encodeURIComponent` / path-segment encoding; `value={selectedScene || undefined}`; console auto-scroll; keep compare videos in sync during playback.
- Test added/updated: none needed
- Verified: frontend lint + build

## [Iteration 2] Marketing-site canvas animation stacked on resize
- File(s): `website/script.js`
- Severity: major
- Root cause: Each resize called `drawEquationField()` without cancelling the previous `requestAnimationFrame` loop.
- Fix: `startEquationField()` cancels the prior frame before seeding and drawing.
- Test added/updated: none needed
- Verified: manual review of the resize path

## [Iteration 3] Storage toggle used a stale file list
- File(s): `frontend/src/App.tsx`
- Severity: major
- Root cause: After `await fetchFiles()`, the effect still read `files.scripts` from the previous render, so switching back to backend storage could keep browser script names.
- Fix: `fetchFiles()` returns the new list; the effect uses that result and `activeFileRef`.
- Test added/updated: none needed
- Verified: `npm --prefix frontend run lint` (clean)

## [Iteration 3] nvidia-smi flashed a console window
- File(s): `backend/diagnostics.py`
- Severity: cosmetic
- Root cause: GPU probe used `shell=True` with no `CREATE_NO_WINDOW`.
- Fix: Argument-vector `nvidia-smi` plus Windows creation flags.
- Test added/updated: none needed
- Verified: compileall OK

---

## [Iteration 4] Scene Select flipped from uncontrolled to controlled
- File(s): `frontend/src/App.tsx`
- Severity: minor
- Root cause: Using `value={selectedScene || undefined}` made Radix Select uncontrolled until a scene loaded, then controlled.
- Fix: Keep it controlled with a `__none__` sentinel item when no scenes exist.
- Test added/updated: none needed
- Verified: `npm --prefix frontend run lint` + `npm --prefix frontend run build`; Vite HMR updated `/src/App.tsx` with no error


| | Count |
|---|---|
| Found (confirmed) | 16 |
| Fixed | 16 |
| Deferred | 4 |
| False positives dropped | 1 (`recommended_threads` unused in `manim.cfg` — profile metadata, not a functional bug) |

### Deferred (needs human review or product decision)
- **Shared `ManimExecutor` instance** across WebSocket connections: two clients can cancel each other’s renders. Fine for local single-user; a per-session executor would be an architectural change.
- **`GET /api/download-temp` deletes the file after send**: intentional for download-only mode, but GET-with-side-effect is surprising if the API is exposed beyond localhost.
- **AST scene detection**: any class with base classes is treated as a Scene. Helper classes can appear in the dropdown. Heuristic is documented in code; tightening it could hide valid `ThreeDScene` subclasses.
- **Temp render directories** (`media/videos/_temp_run_*`) may remain when `partial_movie_files/` is non-empty after download-only cleanup.

### User-visible behavior changes
- Traversal-style filenames now return **400** instead of reading/writing outside `workspace/`.
- Missing `winget` correctly returns **400** instead of **500**.
- Invalid WebSocket JSON or scene names return an error frame instead of dropping the render socket.
- Leftover `_temp_run_*.py` temp scripts no longer appear in the sidebar.
- Clearing the editor no longer silently reloads the file from disk.
- Quality is no longer reset while dependency installers are polling.

### Verification
- `python -m unittest discover -s tests -t . -v` — 11 tests OK
- `python -m compileall backend tests` — OK
- `npm --prefix frontend run lint` — clean
- `npm --prefix frontend run build` (`tsc -b && vite build`) — OK
- No existing app test suite / Manim integration tests were present; live render was not executed in this pass.

### Confidence the codebase is clean
**Medium-high** for the application logic we can statically and unit-test. **Medium** for end-to-end rendering: there is still no automated Manim subprocess test, so a live `manim` CLI / LaTeX / FFmpeg failure path was not exercised here.
