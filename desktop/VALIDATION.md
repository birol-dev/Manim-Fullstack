# Desktop validation — Windows x64, 2026-10-28

All maintained source/config/scripts added by this work are under `desktop/`. No commits, global installs, signing, or publishing were performed. Frontend and backend source changes belong to their respective agents.

## Toolchain findings

* Rust 1.98.1 GNU is the default. The installed MSVC Rust toolchain fails a minimal compilation with `link.exe not found`; `vswhere -all -format json` returns `[]`. Tauri 2's supported MSVC build prerequisites are unavailable. No installer was built with Tauri.
* Node 22.23.4 and build-host Python 3.12 are present. The packaged runtime is independently downloaded CPython 3.12.10 x64, not a copy of this machine's Python installation.
* The host has .NET Framework 4.8.1 and WebView2 156.0.4314.50. PyWebView 6.2.1, Python.NET 3.2.1, Manim 0.22.1, ManimPango 0.7.1, Cairo, Pillow 12.3.0 and PyAV 19.0.2 load from the local runtime. `constraints.txt` records the complete dependency snapshot.

## Executed checks

* Local-runtime preparation and Vite production build to `desktop/build/frontend`: passed. Vite was invoked directly against the existing frontend config and dependencies; this did not run a new full frontend typecheck/lint suite.
* `desktop/.runtime/python.exe -m unittest discover -s desktop/tests -v`: **10 tests passed**. They cover HTTP/session auth, static frontend and catalog, host/origin rejection, independent MCP credential rejection, cookie-authenticated WebSocket connection, distinct instances/ports/tokens, token absence in logs, user-site isolation, workspace lock release, owner crash, graceful service exit/listener closure, and an orphaned grandchild killed by a Job Object.
* `launcher.py --ui-smoke`: passed with real WebView2. React mounted, a same-origin catalog fetch returned 200, and navigation ended at `/` without a token in the URL.
* A compiled `Manim Studio.exe` opened the bundled app. Windows computer-use inspection confirmed the Studio UI and loopback URL inside the native window. Clicking the native Close control terminated all **12** observed owned processes, including the GUI host, embedded Python shell/backend, preview worker, WebView2 processes and console hosts. No broad process-name termination was used.
* Real relocated-runtime rendering: countdown template preview returned a **214×120 PNG**. A new MP4 export completed, and bundled PyAV decoded **138 frames**, **854×480**, **9.2 seconds**, **132,949 bytes**. The timer input is five seconds; template intro/outro brings the observed file duration to 9.2 seconds. End-to-end service/preview/export verification took 20.33 seconds in the first run. No system FFmpeg/Manim executable was available through the restricted backend `PATH`.
* The final package command **completed successfully**: fresh desktop UI build, frozen backend snapshot, compiled GUI starter, repeated real PNG/MP4 smoke, source hash comparison, and payload manifest. The final render run took 37.27 seconds and produced the same 9.2-second MP4 dimensions/frame count above. Final report: `desktop/build/package-smoke/render-smoke.json`; copied-source hashes: `desktop/dist/ManimStudio/backend-snapshot.sha256.json`.

The final package contains the complete `backend/studio` tree, including kit code, bundled fonts/icons, MCP server/transport with the latest httpx2 imports and current `main.py` with the MCP lifespan fix. All 452 backend snapshot files match the frozen source. The freshly rebuilt packaged UI also passed the WebView2 smoke. This is the completed portable build, not a pending build or an installer.

## Limits

The output is an **unsigned portable folder**, not an installer. It was tested on this workstation with real WebView2 and isolated embedded dependencies; a clean Windows VM without developer runtimes has not been tested. .NET Framework and WebView2 remain OS prerequisites. External LaTeX and optional external media utilities are not bundled. Installer prerequisite handling, signing and release review remain outside this bounded implementation.

The shell requests graceful shutdown, then enforces a deadline with Windows Job Objects. Closing while frontend requests are still running can leave uvicorn cancellation/timeout messages in the log; process and socket termination passed. The Windows UI test validates the native host and normal close, rather than every template or every UI interaction. The backend owner separately verified official HTTP and stdio MCP clients; desktop tests verify credential separation, not the full MCP protocol suite.
