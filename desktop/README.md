# Studio desktop shell (Windows x64)

Gallery posters and silent motion peeks are shipped under `backend/studio/assets/posters/`
and `backend/studio/assets/peeks/`. Before packaging,
run `python -m backend.studio.bake_posters` at the repository root. `scripts/package.py`
rejects missing/stale bakes and oversized peeks, and copies the entire backend, including
both folders. The same command bakes both; commit both manifests and their assets.

This directory owns the desktop host only. The static React build is served by the existing FastAPI backend at a loopback origin remembered for each data folder. Development build output, embedded Python, and portable output stay inside `desktop/`. No root package, frontend source/config, backend source, or requirements are modified by these scripts.

## Host choice

Tauri 2 was investigated first. On this workstation Rust 1.98.1 defaults to `x86_64-pc-windows-gnu`; an MSVC toolchain is installed but compiling a minimal program with `rustc +stable-x86_64-pc-windows-msvc` fails with `link.exe not found`. Visual Studio Installer's `vswhere -all` returns `[]`, and the Windows SDK installation has no libraries. Tauri's supported Windows path needs the Microsoft C++ tools and SDK. No global tools were installed or switched. See [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/).

The working fallback is pinned PyWebView 6.2.1, forced to WebView2 (`edgechromium`, no legacy IE fallback), with app-local CPython and wheels. The service's loopback/handshake/session protocol is independent of the window toolkit, so a future Tauri host can reuse it. See [PyWebView Windows dependencies](https://pywebview.flowrl.com/guide/installation.html).

## Development

Build host: Windows x64, Python 3.12 x64 with pip, Node/npm with the existing `frontend/node_modules`. Runtime host: Windows 10/11 x64, .NET Framework 4.8 and Microsoft Edge WebView2 Evergreen Runtime. Users of a prepared portable folder need neither Python nor Node. The portable folder does not install OS prerequisites; the installer below offers to add WebView2 when it is missing.

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

## Agent host: MCP works with the app closed

`desktop/agent_host.py` lets the stdio MCP server work whether or not a Studio window is open. The AI app launches:

```text
<runtime python> -B <app root>/backend/studio/mcp_server.py --desktop-data <data dir>
```

`<data dir>` is the folder that holds `workspace/`, `desktop-port` and `desktop.lock`; `--app-root` defaults to two levels above `backend/studio/`. The command carries no token: the process reads or creates `workspace/studio/mcp-token` with `agent_token()`, then sends it as `Authorization: Bearer` on the same Studio routes the app uses.

* `AgentHost.ensure()` pings `GET /api/studio/catalog` on the port saved in `desktop-port`. A live backend — the app's or another agent host's — is reused, so there is still never a second render queue.
* With nothing listening it starts `Backend` from `launcher.py` headlessly (no window) and returns that URL. If the workspace lock is held but the port is not answering yet (the app, or another host, is still starting), it waits up to 90 s for the other process instead of failing.
* Handover to the app: while an agent host owns the backend it writes `agent-host.json` (with its PID) in the data folder. If a person then opens Manim Studio, `WorkspaceLock` sees the live marker, writes `handover-request` and retries the lock for up to 20 s. The agent host polls every 0.5 s, stops its backend (releasing the lock), deletes the request and keeps bridging; its next call finds the app's backend through `desktop-port`. Without a live marker, a second window is refused immediately as before, so two app windows never share a data folder.
* Handover still stops the agent's backend at once, and the app resumes its queued or running exports from the saved request; a clean stop never marks them failed (a crash still does).
* The owned backend stops when the stdio session ends (stdin EOF, then process exit; the backend's Job object also kills the sidecar if the process dies) and after 10 minutes without an MCP call. It restarts transparently on the next call. The stdio bridge resolves the URL per request, so opening or closing the app mid-session only causes one retry.
* An idle stop first asks `GET /api/studio/exports` (agent token, short timeout): while any export is `queued` or `rendering` it keeps the backend and resets the idle clock; if the request fails it stops as before.
* `GET /api/studio/connection` now also returns `stdio`: `{"command", "args", "background"}`. In the desktop app `background` is `true` and the args are `-B …/backend/studio/mcp_server.py --desktop-data <data>`; in a source checkout they keep `--url` and `--token-file` with `background: false`, because HTTP works only while that server runs.

The stdio entry looks for `agent_host.py` in `<app root>/desktop` and `<app root>/shell`. Packaging must copy it next to `launcher.py` in the packaged `shell/` folder.

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

Keep the entire folder together. The starter resolves the bundled interpreter relative to itself and does not search `PATH`. Packaging copies backend resources and dependency license files without stripping them, rewrites runtime paths to relative packaged paths, and runs an isolated relocated service smoke plus a real Studio PNG preview and MP4 export before reporting success. PyAV decodes every MP4 frame to verify the actual encoder output. The smoke uses bundled tools with a restricted backend `PATH`. It uses the .NET Framework C# compiler on the build host. `package.ps1` then builds the installer described below. Signing is optional through `MANIM_SIGN_CMD`. `.github/workflows/release.yml` publishes both installer assets on a version tag; in-app updates are described below. File associations are not implemented.

The runtime includes Manim/Pango/Cairo/PyAV wheels for template previews and MP4 encoding. External LaTeX is not bundled. Templates that require LaTeX or external media tools remain outside this bounded packaging target. A clean Windows VM acceptance test, runtime/dependency security and redistribution review are release work. Setup handles WebView2 itself; unsigned executable reputation is handled by signing, not by hiding the warning.

## Windows installer (`ManimStudioSetup.exe`)

`./desktop/package.ps1` writes `desktop/dist/ManimStudioSetup.exe` after the portable folder has passed its smoke test. It is built the same way as the portable starter: a C# 5 WinForms executable compiled by the .NET Framework `csc.exe`, with a deflated zip of `desktop/dist/ManimStudio` appended after it (not embedded as a resource):

```text
[stub exe][zip payload][8-byte little-endian payload length][8-byte "MSETUP01" magic]
```

`scripts/build_installer.py` stamps the version from the root `package.json` into the stub, draws a simple black rounded square with a white play triangle as an `.ico` with Pillow when the repository has none, and appends the payload. `scripts/package.py` uses the same icon for `Manim Studio.exe`.

What Setup does:

* Installs for the current person in `%LOCALAPPDATA%\Programs\ManimStudio`; the manifest requests `asInvoker`, so Windows never asks for an administrator password.
* Extracts into a sibling temporary folder and swaps it in only on success, so a failed install or upgrade leaves the previous copy working. It refuses with a plain message and a Retry button while Manim Studio is running from that folder, checks free disk space first, and rejects zip-slip paths.
* Offers Start menu and desktop shortcuts (desktop is a checkbox, on by default), writes the per-user uninstall entry, and copies itself to `Uninstall.exe`.
* Checks the Evergreen WebView2 runtime in the registry (`HKLM` WOW6432Node and `HKCU`). When it is missing, Setup downloads Microsoft's bootstrapper, verifies its Authenticode signature and Microsoft signer subject, and runs it with `/silent /install`. Offline, the rest of the install still completes and Setup says plainly that opening it again retries the browser engine.
* Uninstall removes only the app folder, shortcuts and registry entry. It then asks, with "keep" as the default, whether to also delete the person's videos and projects in `%LOCALAPPDATA%\ManimStudio`. AI app configurations are never touched.

The installed app keeps using `%LOCALAPPDATA%\ManimStudio` for videos, projects and settings.

Command-line options used by tests and quiet deployment:

| Option          | Effect                                                                    |
| --------------- | ------------------------------------------------------------------------- |
| `/S`            | Silent install: no window, exit code only                                 |
| `/nowebview2`   | Do not download WebView2 (used by silent installs and tests)              |
| `/dir:<path>`   | Install elsewhere; also uses `ManimStudio-Test` and skips shortcuts       |
| `/uninstall`    | Remove the installed copy; combine with `/S` for no UI                    |
| `/update`       | Install over the existing copy after the old app has closed               |
| `/waitpid:<pid>`| Wait up to 60 s for that process to exit (the app's shell)                |
| `/relaunch`     | Start the installed app again after the attempt, outside any Job          |
| `/resultdir:<path>` | Where to write `update-result.json` (tests; defaults to the data folder) |

## Automatic updates

`backend/studio/updates.py` checks the project's newest GitHub release at most once a
day, in a background thread, and only while About → Check for updates automatically
is on (`update_check` in the workspace preferences, on by default). The check sends
one GET with a User-Agent and a five second timeout; it sends nothing about the
person. Drafts and prereleases are skipped, a release counts only when it carries
both `ManimStudioSetup.exe` and `ManimStudioSetup.exe.sha256`, and an older version
is never offered. Offline or rate-limited is a quiet "couldn't check" state.

Downloading happens only after the person asks. The installer is written to
`<workspace>/studio/updates/` through a temporary file, must match the release's
SHA-256, is limited to 1 GB, and a mismatch deletes it. Only one installer is kept,
and the installer removes itself after a successful update.

**The digest comes from the same release, so it proves the download arrived intact,
not who published it.** When the running `Manim Studio.exe` has a valid Authenticode
signature, the downloaded installer must also be validly signed with the same
subject; that check uses `Get-AuthenticodeSignature` through PowerShell with a fixed
command and the path in the environment. An unsigned copy skips this extra check,
which is why signing the release is still the real identity guarantee.

Installing starts the verified installer with `/S /update /relaunch /waitpid:<shell
pid>`, then closes the app through its normal shutdown route. An export that is
queued or rendering is never interrupted: the route answers 409 with "An export is
still running. It can finish first." Both Windows Jobs (the shell's and the native
starter's) carry `JOB_OBJECT_LIMIT_BREAKAWAY_OK`, and the installer is started with
`CREATE_BREAKAWAY_FROM_JOB`, so it outlives the Job that is closed as the app exits.
`desktop/tests/test_desktop.py` proves that with a real Job.

The installer and app are **unsigned**. Windows SmartScreen warns the first time someone runs them ("Windows protected your PC" → **More info** → **Run anyway**). Do not hide that warning; sign the executables when a code-signing certificate exists. `scripts/package.py` and `scripts/build_installer.py` run `MANIM_SIGN_CMD` for both executables when it is set, and print a note when it is not:

```powershell
$env:MANIM_SIGN_CMD = 'signtool sign /fd sha256 /tr http://timestamp.digicert.com /td sha256 /f C:\keys\studio.pfx /p <password> {file}'
./desktop/package.ps1
```

`{file}` is replaced by the quoted executable path; without it, the path is appended. macOS and Linux installers are not built here, and could not be tested on this Windows workstation; source users there run `python3 run.py` or `sh start.sh`.

## Validation

```powershell
./desktop/.runtime/python.exe -m unittest discover -s desktop/tests -v
python -B -m unittest discover -s desktop/tests -p test_desktop.py -k PortTests -v
python -m unittest discover -s desktop/tests -p test_installer.py -v
python -m unittest discover -s desktop/tests -p test_run_bootstrap.py -v
./desktop/dist/ManimStudio/runtime/python.exe -B ./desktop/scripts/smoke.py --app-root ./desktop/dist/ManimStudio --data-dir ./desktop/build/manual-render-smoke
```

The installer tests compile the real stub with system Python, build a tiny fake payload, silently install it under a temporary folder with `/dir:` and `/nowebview2`, check the files and the test-only uninstall entry, install an upgrade, then silently uninstall and wait for the folder and registry entry to disappear. They also check that a zip-slip entry is refused and that `/update` replaces one fake version with another in place, writing `update-result.json` under `/resultdir:`. `/dir:` and `/resultdir:` never touch the real install location, data folder, production uninstall key, or shortcuts. The desktop tests start a real Job, let a child break away with `CREATE_BREAKAWAY_FROM_JOB`, close the Job, and check that the child is still alive. The run.py tests cover the version check, requirements hash stamp, virtual-environment detection, and the Linux/macOS package-manager command choice without running pip or using the network.

Tests exercise port reuse across launches, occupied-port fallback, real loopback authentication/session bootstrap, static frontend/catalog serving, host/origin rejection, WebSocket cookie auth, independent instances, single-workspace locking, graceful shutdown, owner crash, and killing an orphaned grandchild. The `PortTests` subset also runs with system Python on Windows with `psutil`, without the embedded backend dependencies. `-UiSmoke` additionally opens WebView2 and verifies React mounts and makes an authenticated catalog request, then closes. Validation outcomes and limits are recorded in `VALIDATION.md` after execution.

The renderer smoke writes `render-smoke.json` and its workspace under the specified test data folder. During a quick close with requests still running, uvicorn can log a graceful-timeout cancellation before the host completes bounded cleanup. The process-tree checks verify termination rather than requiring an empty log.
