"""One-command launcher: sets up a private Python environment, builds the frontend, then serves app + API."""
from __future__ import annotations

import argparse
import hashlib
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

VENV_DIR = os.path.join(ROOT_DIR, ".venv")
REQUIREMENTS_FILE = os.path.join(ROOT_DIR, "backend", "requirements.txt")
STAMP_NAME = "manim-requirements.sha256"
MINIMUM_PYTHON = (3, 11)
REQUIRED_PACKAGES = ("manim", "fastapi", "uvicorn")

APT_COMMAND = "sudo apt install build-essential pkg-config libcairo2-dev libpango1.0-dev python3-dev"
DNF_COMMAND = "sudo dnf install pkgconfig cairo-devel pango-devel python3-devel gcc-c++"
PACMAN_COMMAND = "sudo pacman -S --needed base-devel pkgconf cairo pango python"
BREW_COMMAND = "brew install cairo pango pkg-config"


# backend/main.py prints the same warning (tests/test_cli.py keeps them in sync).
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
            print("[warn] Node.js was not found, so the existing frontend build will be used.", flush=True)
            print("       Install Node.js 20.19+ from https://nodejs.org if you change the frontend.", flush=True)
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


def python_version_supported(version_info=None) -> bool:
    """Return whether this interpreter can run Manim Studio."""
    info = version_info if version_info is not None else sys.version_info
    return (info[0], info[1]) >= MINIMUM_PYTHON


def requirements_digest(path: str = REQUIREMENTS_FILE) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as requirements:
        for chunk in iter(lambda: requirements.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stamp_is_current(stamp_path: str, digest: str) -> bool:
    try:
        with open(stamp_path, "r", encoding="utf-8") as stamp:
            return stamp.read().strip() == digest
    except OSError:
        return False


def write_stamp(stamp_path: str, digest: str) -> None:
    with open(stamp_path, "w", encoding="utf-8") as stamp:
        stamp.write(digest + "\n")


def inside_virtualenv(prefix: str | None = None, base_prefix: str | None = None) -> bool:
    prefix = sys.prefix if prefix is None else prefix
    base_prefix = getattr(sys, "base_prefix", sys.prefix) if base_prefix is None else base_prefix
    return prefix != base_prefix


def missing_packages(names=REQUIRED_PACKAGES) -> list:
    missing = []
    for name in names:
        try:
            found = importlib.util.find_spec(name) is not None
        except (ImportError, ValueError):
            found = False
        if not found:
            missing.append(name)
    return missing


def venv_python_path(venv_dir: str = VENV_DIR) -> str:
    if os.name == "nt":
        return os.path.join(venv_dir, "Scripts", "python.exe")
    return os.path.join(venv_dir, "bin", "python")


def system_install_command(platform: str, available) -> str | None:
    """Pick the one command that installs Cairo and Pango for this system."""
    if platform == "darwin":
        return BREW_COMMAND if "brew" in available else None
    if platform.startswith("linux"):
        if "apt-get" in available:
            return APT_COMMAND
        if "dnf" in available:
            return DNF_COMMAND
        if "pacman" in available:
            return PACMAN_COMMAND
    return None


def linux_libraries_present(which=shutil.which, runner=subprocess.run) -> bool:
    if which("pkg-config") is None:
        return False
    for package in ("cairo", "pangocairo"):
        result = runner(["pkg-config", "--exists", package],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode != 0:
            return False
    return True


def macos_libraries_present(which=shutil.which, runner=subprocess.run) -> bool:
    if which("brew") is None:
        return False
    for formula in ("cairo", "pango", "pkg-config"):
        result = runner(["brew", "list", formula],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode != 0:
            return False
    return True


def check_system_libraries() -> bool:
    """On Linux and macOS, offer the exact command when Cairo/Pango are missing."""
    if sys.platform.startswith("win"):
        return True
    if sys.platform == "darwin":
        if macos_libraries_present():
            return True
    elif sys.platform.startswith("linux"):
        if linux_libraries_present():
            return True
    else:
        return True

    available = {name for name in ("apt-get", "dnf", "pacman", "brew") if shutil.which(name)}
    command = system_install_command(sys.platform, available)
    print("\nManim needs a few system libraries that are not installed yet.")
    if command:
        print("Run this command, then start Manim Studio again:\n")
        print(f"    {command}\n")
        if sys.stdin.isatty():
            answer = input("Run it now? [y/N] ").strip().lower()
            if answer in ("y", "yes"):
                if subprocess.run(command, shell=True).returncode == 0:
                    print()
                    return True
                print("\nThat command did not finish. Install the libraries yourself and run this again.")
    elif sys.platform == "darwin":
        print("Install Homebrew from https://brew.sh, then run:\n")
        print(f"    {BREW_COMMAND}\n")
    else:
        print("Install the Cairo and Pango development packages with your package manager,")
        print("then start Manim Studio again.\n")
    return False


def diagnose_pip_failure(output: str) -> str:
    """Turn pip's output into one plain sentence for a non-technical person."""
    text = (output or "").lower()
    if "no module named pip" in text:
        return ("Pip is missing from this Python. Install Python from https://www.python.org/downloads/ "
                "(it includes pip), then run this again.")
    if any(token in text for token in ("could not find a version", "no matching distribution",
                                       "temporary failure in name resolution", "connection", "network",
                                       "timed out", "ssl", "certificate")):
        return "The packages could not be downloaded. Check your internet connection, then run this again."
    if any(token in text for token in ("pkg-config", "cairo", "pango", "manimpango")):
        return "A system library Manim needs is missing. Run the install command printed above, then try again."
    if "permission denied" in text or "access is denied" in text:
        return "This Python cannot write to its package folder. Use the .venv that run.py creates, or ask an administrator."
    return "Installing the Python packages failed. The last lines above show why; fix that and run this again."


def install_requirements() -> None:
    """Install backend/requirements.txt into the active virtual environment when needed."""
    digest = requirements_digest()
    stamp_path = os.path.join(sys.prefix, STAMP_NAME)
    if not missing_packages() and stamp_is_current(stamp_path, digest):
        return
    print("Installing the Python packages Manim needs (first run; this can take a few minutes)...", flush=True)
    command = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
               "-r", REQUIREMENTS_FILE]
    completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if completed.returncode != 0:
        tail = "\n".join((completed.stdout or "").splitlines()[-30:])
        if tail:
            print(tail, file=sys.stderr)
        print(f"\n[error] {diagnose_pip_failure(completed.stdout)}", file=sys.stderr)
        print("Nothing was installed outside this virtual environment.\n", file=sys.stderr)
        sys.exit(1)
    write_stamp(stamp_path, digest)
    print("Python packages installed.", flush=True)


def bootstrap() -> None:
    """Make sure Manim, FastAPI and Uvicorn are available, creating .venv when needed."""
    if os.environ.get("MANIM_RUN_BOOTSTRAP_LOOP") == "1" and not inside_virtualenv():
        print("\n[error] The private .venv could not be used. Delete the .venv folder and run this again.\n",
              file=sys.stderr)
        sys.exit(1)
    missing = missing_packages()
    if inside_virtualenv():
        stamp_path = os.path.join(sys.prefix, STAMP_NAME)
        if missing or not stamp_is_current(stamp_path, requirements_digest()):
            check_system_libraries()
            install_requirements()
        return
    if not missing:
        return  # An existing Python with the packages is fine; never touch the global environment.

    python = venv_python_path()
    if not os.path.isfile(python):
        print("Setting up a private Python environment in .venv (this happens once)...", flush=True)
        try:
            import venv
            venv.EnvBuilder(with_pip=True).create(VENV_DIR)
        except Exception as error:
            print(f"\n[error] The private Python environment could not be created: {error}", file=sys.stderr)
            print("Install Python 3.11 or newer from https://www.python.org/downloads/ and try again.",
                  file=sys.stderr)
            if sys.platform.startswith("linux"):
                print("On Debian or Ubuntu the venv package is called python3-venv.\n", file=sys.stderr)
            else:
                print()
            sys.exit(1)
    print("Starting inside .venv...", flush=True)
    os.environ["MANIM_RUN_BOOTSTRAP_LOOP"] = "1"
    script = os.path.abspath(__file__)
    try:
        if os.name == "nt":
            # os.execv on Windows leaves a detached child, which closes with a double-clicked console.
            completed = subprocess.run([python, script] + sys.argv[1:])
            sys.exit(completed.returncode)
        os.execv(python, [python, script] + sys.argv[1:])
    except OSError as error:
        print(f"\n[error] The private Python environment could not start: {error}\n", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    if not python_version_supported():
        print(f"\n[error] Manim Studio needs Python {MINIMUM_PYTHON[0]}.{MINIMUM_PYTHON[1]} or newer. "
              f"This is Python {sys.version_info[0]}.{sys.version_info[1]}.", file=sys.stderr)
        print("Install the current Python from https://www.python.org/downloads/ and run this again.\n",
              file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Start Manim Studio (frontend + API on one port).")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser window")
    parser.add_argument("--build", action="store_true", help="Force a fresh frontend build")
    parser.add_argument("--no-install", action="store_true",
                        help="Do not create .venv or install Python packages")
    args = parser.parse_args()

    if not args.no_install:
        bootstrap()

    missing = missing_packages()
    if missing:
        print(f"\n[error] The Python packages Manim Studio needs are not installed: {', '.join(missing)}",
              file=sys.stderr)
        if args.no_install:
            print("Run this again without --no-install, or install them with:", file=sys.stderr)
        else:
            print("Install the backend requirements first:", file=sys.stderr)
        print("    pip install -r backend/requirements.txt\n", file=sys.stderr)
        sys.exit(1)

    try:
        build_frontend(force=args.build)
    except FileNotFoundError:
        print("\n[error] Node.js was not found and there is no built frontend yet.", file=sys.stderr)
        print("Install Node.js 20.19+ from https://nodejs.org, then run this again.\n", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as exc:
        print(f"\n[error] Frontend build failed (exit code {exc.returncode}).", file=sys.stderr)
        print("Try it by hand to see the full output:\n    cd frontend && npm install && npm run build\n",
              file=sys.stderr)
        sys.exit(1)

    if is_port_in_use(args.port, args.host):
        print(f"\n[error] Port {args.port} is already in use.", file=sys.stderr)
        print(f"Stop the other process or pick another port:\n    python run.py --port {args.port + 1}\n",
              file=sys.stderr)
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

    print(f"Manim Studio is running at {url}  (Ctrl+C to stop)", flush=True)
    try:
        from backend.main import ws_max_message_bytes

        uvicorn.run(
            "backend.main:app",
            host=args.host,
            port=args.port,
            reload=False,
            log_level="warning",
            ws_max_size=ws_max_message_bytes(),
        )
    except KeyboardInterrupt:
        pass
    print("\nManim Studio stopped.", flush=True)


if __name__ == "__main__":
    main()
