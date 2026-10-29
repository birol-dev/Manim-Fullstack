# Studio desktop shell (Windows x64)

Gallery posters are shipped under `backend/studio/assets/posters/`. Before packaging,
run `python -m backend.studio.bake_posters` at the repository root. `scripts/package.py`
rejects missing/stale bakes and copies the entire backend, including this folder.

This directory owns the desktop host only. The static React build is served by the existing FastAPI backend at a loopback origin remembered for each data folder. Development build output, embedded Python, and portable output stay inside `desktop/`. No root package, frontend source/config, backend source, or requirements are modified by these scripts.

## Host choice

Tauri 2 was investigated first. On this workstation Rust 1.98.1 defaults to `x86_64-pc-windows-gnu`; an MSVC toolchain is installed but compiling a minimal program with `rustc +stable-x86_64-pc-windows-msvc` fails with `link.exe not found`. Visual Studio Installer's `vswhere -all` returns `[]`, and the Windows SDK installation has no libraries. Tauri's supported Windows path needs the Microsoft C++ tools and SDK. No global tools were installed or switched. See [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/).

The working fallback is pinned PyWebView 6.2.1, forced to WebView2 (`edgechromium`, no legacy IE fallback), with app-local CPython and wheels. The service's loopback/handshake/session protocol is independent of the window toolkit, so a future Tauri host can reuse it. See [PyWebView Windows dependencies](https://pywebview.flowrl.com/guide/installation.html).

## Development

Build host: Windows x64, Python 3.12 x64 with pip, Node/npm with the existing `frontend/node_modules`. Runtime host: Windows 10/11 x64, .NET Framework 4.8 and Microsoft Edge WebView2 Evergreen Runtime. Users of a prepared portable folder need neither Python nor Node. This bounded shell does not install OS prerequisites.

From the repository root:

```powershell
./desktop/dev.ps1
./desktop/dev.ps1 -Smoke
./desktop/dev.ps1 -UiSmoke
./desktop/dev.ps1 -SkipFrontendBuild
```

`dev.ps1` verifies/downloads CPython into `.runtime/`, installs packages into that directory only, builds Vite into `desktop/build/frontend/`, and opens the native window. It never calls `npm install`. `-SkipFrontendBuild` reuses an existing build. `-RefreshDependencies` reinstalls the local dependency tree. Use `-DataDir C:\some\test-folder` for an isolated session; otherwise data lives in `%LOCALAPPDATA%\ManimStudio`.

The embedded CPython archive is versioned and SHA-256 pinned in `runtime.json`; its digest was checked against python.org's published Sigstore bundle. The script verifies the pinned digest, not the Sigstore signature itself. Native dependencies require binary wheels; small pure-Python dependencies may be built locally. `constraints.txt` pins the validated dependency versions, and resolved packages are recorded in `.runtime/requirements-resolved.txt`. No user-site packages are loaded: `site` is disabled, pywin32 paths are explicit, and its runtime DLLs are copied beside Python. The `._pth` explicitly includes the backend so preview and Manim subprocesses work in isolated mode, too.

## Local service and data

* `launcher.py` generates a fresh 256-bit session token and instance identifier. Secrets go through the child environment, never its command line or readiness output.
* `sidecar.py` waits on a private startup pipe until assigned to a Windows Job Object, then binds loopback with exclusive address use and passes that exact socket to uvicorn. It reuses the port saved in `desktop-port` in the data folder; a missing or invalid file defaults to `127.0.0.1:47817`. If the preferred port is unavailable, it binds port `0` for a free port and saves the result. If saving fails, startup continues with a warning in the log. It reports protocol/port/instance/PID on private stdout only after startup. The shell verifies a bearer-authenticated ping and rejects backends that ignore desktop auth.
* The WebView opens `/api/desktop/session?token=...`. Backend integration must validate it, set an HttpOnly `SameSite=Strict` cookie, and 303 redirect to `/`. Frontend HTTP, WebSocket, upload, and media URLs remain same-origin. Uvicorn access logging is disabled; shell logs redact the per-launch token.
* Top-level WebView navigation is restricted to this run's server origin. File URLs and external popup navigation are blocked. Native downloads use the WebView2 Save dialog. No custom Python API is exposed to the frontend.
* Required backend environment contract: `MANIM_WORKSPACE`, `MANIM_FRONTEND_DIR`, `MANIM_API_TOKEN`. No backend monkey-patching. Desktop disables LAN access, extra dev origins, and package installation endpoints.
* Workspace, templates' projects, renders and uploads live under `workspace/`; logs rotate under `logs/`; temporary files, cache, and WebView data have dedicated app-data folders. A file lock prevents two windows from concurrently using the same data folder. Another `-DataDir` can run independently on a different port.
* `/mcp` remains backend-owned and requires its independent persisted bearer token (`workspace/studio/mcp-token`). The desktop session token is not an MCP credential. No token-bearing discovery file is written by the desktop host.
* Saved AI connections to `http://127.0.0.1:<port>/mcp/` survive restarts using the same data folder while its remembered port remains available. If another process takes that port, Studio starts on a new saved port; update the AI client's MCP address from Connect to AI.
* Close requests an authenticated shutdown, closes the lifetime pipe, waits up to ten seconds, then closes the Job handle. Windows kills all remaining descendants, including orphaned workers/render processes. An abrupt shell crash also closes the Job handle. No broad process-name kills. The packaged native starter owns an outer Job so its failure also tears down the shell and service.

## Portable packaging

```powershell
./desktop/package.ps1
```

This creates an **unsigned portable folder**, not an installer:

```text
desktop/dist/ManimStudio/
  Manim Studio.exe         # small Windows GUI starter, compiled with Framework csc
  runtime/                # embedded CPython, isolated ._pth, site-packages and DLLs
  backend/                # snapshot of backend including Studio templates/assets
  frontend/dist/          # built static React application
  shell/                  # lifecycle host, sidecar, Windows Job wrapper
  manifest.sha256.json    # hashes of the assembled payload
  backend-snapshot.sha256.json # copied backend resources, checked against source after smoke
  LICENSE
  DESKTOP-README.md
```

Keep the entire folder together. The starter resolves the bundled interpreter relative to itself and does not search `PATH`. Packaging copies backend resources and dependency license files without stripping them, rewrites runtime paths to relative packaged paths, and runs an isolated relocated service smoke plus a real Studio PNG preview and MP4 export before reporting success. PyAV decodes every MP4 frame to verify the actual encoder output. The smoke uses bundled tools with a restricted backend `PATH`. It uses the .NET Framework C# compiler on the build host. No signing, installer generation, publishing, update service, or file associations are implemented.

The runtime includes Manim/Pango/Cairo/PyAV wheels for template previews and MP4 encoding. External LaTeX is not bundled. Templates that require LaTeX or external media tools remain outside this bounded packaging target. A clean Windows VM acceptance test, runtime/dependency security and redistribution review, installer prerequisite handling, and unsigned executable reputation handling are release work.

## Validation

```powershell
./desktop/.runtime/python.exe -m unittest discover -s desktop/tests -v
python -B -m unittest discover -s desktop/tests -p test_desktop.py -k PortTests -v
./desktop/dist/ManimStudio/runtime/python.exe -B ./desktop/scripts/smoke.py --app-root ./desktop/dist/ManimStudio --data-dir ./desktop/build/manual-render-smoke
```

Tests exercise port reuse across launches, occupied-port fallback, real loopback authentication/session bootstrap, static frontend/catalog serving, host/origin rejection, WebSocket cookie auth, independent instances, single-workspace locking, graceful shutdown, owner crash, and killing an orphaned grandchild. The `PortTests` subset also runs with system Python on Windows with `psutil`, without the embedded backend dependencies. `-UiSmoke` additionally opens WebView2 and verifies React mounts and makes an authenticated catalog request, then closes. Validation outcomes and limits are recorded in `VALIDATION.md` after execution.

The renderer smoke writes `render-smoke.json` and its workspace under the specified test data folder. During a quick close with requests still running, uvicorn can log a graceful-timeout cancellation before the host completes bounded cleanup. The process-tree checks verify termination rather than requiring an empty log.
