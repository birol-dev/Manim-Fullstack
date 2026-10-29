"""Desktop-only uvicorn host. A persisted loopback port is passed directly to uvicorn."""
from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import os
from pathlib import Path
import socket
import sys


DEFAULT_PORT = 47817


def bind_socket(port_file: Path) -> socket.socket:
    try:
        port = int(port_file.read_text(encoding="ascii"))
        if not 0 < port < 65536:
            port = DEFAULT_PORT
    except (OSError, ValueError):
        port = DEFAULT_PORT
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # Exclusive use on Windows; no reuse of an unrelated listener's port.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            sock.bind(("127.0.0.1", 0))
        try:
            port_file.write_text(f"{sock.getsockname()[1]}\n", encoding="ascii")
        except OSError:
            print("Could not save desktop port; address may change on next launch.", file=sys.stderr)
        return sock
    except BaseException:
        sock.close()
        raise


def main():
    # No imports of backend code or descendants before the parent assigns our Job.
    if sys.stdin.buffer.readline() != b"start\n":
        return 2
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-root", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.app_root.resolve()
    token = os.environ["MANIM_API_TOKEN"]
    instance = os.environ["STUDIO_DESKTOP_INSTANCE"]
    sys.path.insert(0, str(root / "backend"))

    import uvicorn
    import main as backend

    # Require the backend integration contract; never silently write to the install tree.
    if Path(backend.WORKSPACE_DIR).resolve() != Path(os.environ["MANIM_WORKSPACE"]).resolve():
        raise RuntimeError("Backend must support MANIM_WORKSPACE before desktop launch.")
    if Path(backend.FRONTEND_DIR).resolve() != Path(os.environ["MANIM_FRONTEND_DIR"]).resolve():
        raise RuntimeError("Backend must support MANIM_FRONTEND_DIR before desktop launch.")

    sock = bind_socket(args.data_dir / "desktop-port")
    port = sock.getsockname()[1]
    authority = f"127.0.0.1:{port}"
    origin = f"http://{authority}"
    os.environ["MANIM_ALLOWED_ORIGINS"] = origin
    os.environ["MANIM_DEV_ORIGIN_PORTS"] = ""  # no unrelated development origins
    os.environ["MANIM_ALLOW_LAN"] = "0"

    class Gateway:
        async def __call__(self, scope, receive, send):
            if scope["type"] == "http" and scope["path"].startswith("/__desktop__/"):
                headers = dict(scope["headers"])
                peer = scope.get("client")
                allowed = (peer and peer[0] == "127.0.0.1"
                           and headers.get(b"host") == authority.encode()
                           and headers.get(b"origin", origin.encode()) == origin.encode()
                           and hmac.compare_digest(headers.get(b"authorization", b""), f"Bearer {token}".encode()))
                path, method = scope["path"], scope["method"]
                status, body = 403, b'{"detail":"Forbidden"}'
                if allowed and (path, method) == ("/__desktop__/ping", "GET"):
                    status, body = 200, json.dumps({"instance": instance, "pid": os.getpid()}).encode()
                elif allowed and (path, method) == ("/__desktop__/shutdown", "POST"):
                    server.should_exit = True
                    status, body = 200, b'{"stopping":true}'
                elif allowed:
                    status, body = 404, b'{}'
                await send({"type": "http.response.start", "status": status,
                            "headers": [(b"content-type", b"application/json"), (b"cache-control", b"no-store")]})
                await send({"type": "http.response.body", "body": body})
                return
            await backend.app(scope, receive, send)

    class DesktopServer(uvicorn.Server):
        async def startup(self, sockets=None):
            await super().startup(sockets=sockets)
            if self.started:
                print(json.dumps({"protocol": 1, "port": port, "instance": instance, "pid": os.getpid()}), flush=True)

    server = DesktopServer(uvicorn.Config(Gateway(), host="127.0.0.1", port=port,
                                          access_log=False, log_level="warning",
                                          timeout_graceful_shutdown=6))

    async def watch_parent():
        # The parent keeps this pipe open for the entire session. EOF also covers crashes.
        await asyncio.to_thread(sys.stdin.buffer.read)
        server.should_exit = True

    async def serve():
        watcher = asyncio.create_task(watch_parent())
        try:
            await server.serve(sockets=[sock])
        finally:
            watcher.cancel()
            sock.close()

    # uvicorn's loop helper may wait for an executor thread; parent closes stdin on stop.
    asyncio.run(serve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
