"""One-command launcher: builds the frontend if needed, then serves app + API on one port."""

import argparse
import importlib.util
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")
DIST_INDEX = os.path.join(FRONTEND_DIR, "dist", "index.html")
# Anything that changes the bundle; a newer file here means the build is stale.
FRONTEND_SOURCES = ("src", "public", "index.html", "package.json", "package-lock.json", "vite.config.ts")


# backend/main.py prints the same warning (tests/test_cli_r3.py keeps them in sync).
LAN_WARNING = (
    "\n[warn] This process runs the Python you send it, with no login.\n"
    "       Binding beyond 127.0.0.1 lets anyone who can reach the port do that.\n"
    "       Remote clients are refused unless you set MANIM_ALLOW_LAN=1.\n"
)


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a given TCP port is already open/bound on the host."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def _newest_mtime(path: str) -> float:
    if os.path.isfile(path):
        return os.path.getmtime(path)
    newest = 0.0
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d != "test"]  # test helpers don't affect the bundle
        for name in files:
            if ".test." in name:
                continue
            try:
                newest = max(newest, os.path.getmtime(os.path.join(root, name)))
            except OSError:
                pass
    return newest


def frontend_build_is_stale() -> bool:
    if not os.path.exists(DIST_INDEX):
        return True
    built_at = os.path.getmtime(DIST_INDEX)
    return any(
        _newest_mtime(os.path.join(FRONTEND_DIR, source)) > built_at
        for source in FRONTEND_SOURCES
        if os.path.exists(os.path.join(FRONTEND_DIR, source))
    )


def build_frontend(force: bool = False) -> None:
    """Build the React app into frontend/dist when it is missing or out of date."""
    if not force and not frontend_build_is_stale():
        return

    npm = shutil.which("npm")
    if npm is None:
        if os.path.exists(DIST_INDEX):
            print("[warn] npm not found; serving the existing (possibly outdated) frontend build.", flush=True)
            return
        raise FileNotFoundError("npm")

    print("Building the frontend (first run or sources changed)...", flush=True)
    if not os.path.isdir(os.path.join(FRONTEND_DIR, "node_modules")):
        print("Installing frontend dependencies (npm install)... this can take a minute.", flush=True)
        subprocess.run([npm, "install", "--no-fund", "--no-audit"], cwd=FRONTEND_DIR, check=True)
    subprocess.run([npm, "run", "build"], cwd=FRONTEND_DIR, check=True)
    print("Frontend built.", flush=True)


def open_browser(url: str) -> None:
    """Give Uvicorn a moment to start, then open the app."""
    time.sleep(1.5)
    webbrowser.open(url)


def main() -> None:
    parser = argparse.ArgumentParser(description="Start Manim Composer (frontend + API on one port).")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser window")
    parser.add_argument("--build", action="store_true", help="Force a fresh frontend build")
    args = parser.parse_args()

    missing = [name for name in ("fastapi", "uvicorn") if importlib.util.find_spec(name) is None]
    if missing:
        print(f"\n[error] Missing Python dependency: {', '.join(missing)}", file=sys.stderr)
        print("Install the backend requirements first:\n    pip install -r backend/requirements.txt\n", file=sys.stderr)
        sys.exit(1)

    try:
        build_frontend(force=args.build)
    except FileNotFoundError:
        print("\n[error] npm was not found on your PATH.", file=sys.stderr)
        print("Install Node.js 20.19+ from https://nodejs.org, then run this again.\n", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as exc:
        print(f"\n[error] Frontend build failed (exit code {exc.returncode}).", file=sys.stderr)
        print("Try it by hand to see the full output:\n    cd frontend && npm install && npm run build\n", file=sys.stderr)
        sys.exit(1)

    if is_port_in_use(args.port, args.host):
        print(f"\n[error] Port {args.port} is already in use.", file=sys.stderr)
        print(f"Stop the other process or pick another port:\n    python run.py --port {args.port + 1}\n", file=sys.stderr)
        sys.exit(1)

    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(LAN_WARNING, file=sys.stderr)

    browser_host = "localhost" if args.host in ("127.0.0.1", "0.0.0.0", "::") else args.host
    url = f"http://{browser_host}:{args.port}"
    if not args.no_browser:
        threading.Thread(target=open_browser, args=(url,), daemon=True).start()

    for path in (ROOT_DIR, os.path.join(ROOT_DIR, "backend")):
        if path not in sys.path:
            sys.path.insert(0, path)

    import uvicorn

    print(f"Manim Composer is running at {url}  (Ctrl+C to stop)", flush=True)
    try:
        uvicorn.run("backend.main:app", host=args.host, port=args.port, reload=False, log_level="warning")
    except KeyboardInterrupt:
        pass
    print("\nManim Composer stopped.", flush=True)


if __name__ == "__main__":
    main()
