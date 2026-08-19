import argparse
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a given TCP port is already open/bound on the host."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def build_frontend(force: bool = False):
    """Builds the React frontend SPA into frontend/dist."""
    root_dir = os.path.dirname(os.path.abspath(__file__))
    frontend_dir = os.path.join(root_dir, "frontend")
    dist_dir = os.path.join(frontend_dir, "dist")
    index_html = os.path.join(dist_dir, "index.html")

    if force or not os.path.exists(dist_dir) or not os.path.exists(index_html):
        print("Frontend build not detected or rebuild requested. Preparing build...")

        # Check node_modules
        node_modules = os.path.join(frontend_dir, "node_modules")
        if not os.path.exists(node_modules):
            print("Installing frontend dependencies (npm install)... This may take a moment.")
            subprocess.run("npm install", shell=True, cwd=frontend_dir, check=True)

        print("Building frontend (npm run build)...")
        subprocess.run("npm run build", shell=True, cwd=frontend_dir, check=True)
        print("Frontend built successfully!")


def open_browser(port: int = 8000):
    """Wait for Uvicorn to initialize and open the default browser."""
    time.sleep(1.5)
    url = f"http://localhost:{port}"
    print(f"Opening web browser at {url}...")
    webbrowser.open(url)


def main():
    parser = argparse.ArgumentParser(description="Start Manim Composer unified server.")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind server on (default: 8000)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host address (default: 127.0.0.1)")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open the browser")
    parser.add_argument("--build", action="store_true", help="Force rebuilding the frontend bundle before start")
    args = parser.parse_args()

    root_dir = os.path.dirname(os.path.abspath(__file__))

    # 1. Build frontend
    try:
        build_frontend(force=args.build)
    except FileNotFoundError:
        print("\n[ERROR] npm executable not found on your system PATH.", file=sys.stderr)
        print("Please install Node.js (>=18) from https://nodejs.org and ensure npm is available in your PATH.\n", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Frontend build failed: {e}", file=sys.stderr)
        print("Please ensure Node.js (>=18) and npm are installed and run:", file=sys.stderr)
        print("    cd frontend && npm install && npm run build\n", file=sys.stderr)
        sys.exit(1)

    # 2. Check port availability
    if is_port_in_use(args.port, args.host):
        print(
            f"\n[ERROR] Port {args.port} is already in use by another process.",
            file=sys.stderr,
        )
        print(
            f"Please terminate the existing process or run with: python run.py --port {args.port + 1}\n",
            file=sys.stderr,
        )
        sys.exit(1)

    # 3. Launch browser in a separate thread if enabled
    if not args.no_browser:
        threading.Thread(target=open_browser, args=(args.port,), daemon=True).start()

    # 4. Configure Python path and start Uvicorn server
    backend_dir = os.path.join(root_dir, "backend")
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    try:
        import uvicorn
        print(f"Starting Manim Composer unified server on http://{args.host}:{args.port} ...")
        uvicorn.run("backend.main:app", host=args.host, port=args.port, reload=False)
    except KeyboardInterrupt:
        print("\nManim Composer server stopped. Goodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()

