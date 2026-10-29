"""Studio's desktop agent host: reuse, headless start, handover, idle stop and stdio bridging."""

import asyncio
import http.server
import json
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import threading
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "desktop"
if str(DESKTOP) not in sys.path:
    sys.path.insert(0, str(DESKTOP))

from agent_host import AgentHost  # noqa: E402
from launcher import AGENT_HOST_MARKER, HANDOVER_REQUEST, WorkspaceBusy  # noqa: E402

RUNTIME = DESKTOP / ".runtime" / "python.exe"
SERVER = ROOT / "backend" / "studio" / "mcp_server.py"


class FakeBackend:
    def __init__(self, root, data, url):
        self.root, self.data, self.url = root, data, url
        self.started = threading.Event()
        self.stopped = threading.Event()

    def start(self):
        self.started.set()
        return self

    def stop(self):
        self.stopped.set()


class CatalogHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        server = self.server
        server.calls += 1
        if server.calls <= server.failures or self.path != "/api/studio/catalog" \
                or self.headers.get("Authorization") != "Bearer test-token":
            body, status = b'{"detail":"starting"}', 503 if server.calls <= server.failures else 401
        else:
            body, status = b"[]", 200
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class CatalogServer(http.server.ThreadingHTTPServer):
    def __init__(self, failures=0):
        super().__init__(("127.0.0.1", 0), CatalogHandler)
        self.calls = 0
        self.failures = failures
        self.thread = threading.Thread(target=self.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.shutdown()
        self.server_close()


def port_of(server):
    return server.server_address[1]


@pytest.fixture(autouse=True)
def agent_token_env(monkeypatch):
    monkeypatch.setenv("MANIM_MCP_TOKEN", "test-token")


def test_ensure_reuses_a_live_backend(tmp_path):
    with CatalogServer() as server:
        (tmp_path / "desktop-port").write_text(str(port_of(server)), encoding="ascii")

        def refuse(*_):
            raise AssertionError("A live backend must be reused, not replaced")

        host = AgentHost(ROOT, tmp_path, backend_factory=refuse)
        try:
            assert host.ensure() == f"http://127.0.0.1:{port_of(server)}"
            assert host.ensure() == f"http://127.0.0.1:{port_of(server)}"
            assert server.calls == 2
            assert not (tmp_path / AGENT_HOST_MARKER).exists()
        finally:
            host.close()


def test_ensure_starts_a_headless_backend_when_none_answers(tmp_path):
    fake = FakeBackend(ROOT, tmp_path, "http://127.0.0.1:9")
    host = AgentHost(ROOT, tmp_path, backend_factory=lambda root, data: fake)
    try:
        assert host.token == "test-token"
        assert host.ensure() == fake.url
        assert fake.started.is_set()
        assert json.loads((tmp_path / AGENT_HOST_MARKER).read_text(encoding="utf-8"))["pid"] == os.getpid()
    finally:
        host.close()
    assert fake.stopped.is_set()
    assert not (tmp_path / AGENT_HOST_MARKER).exists()


def test_ensure_waits_when_the_lock_is_held_and_the_port_is_not_ready(tmp_path):
    attempts = []

    def busy(root, data):
        attempts.append((root, data))
        raise WorkspaceBusy("Studio is already using this data folder.")

    with CatalogServer(failures=2) as server:
        (tmp_path / "desktop-port").write_text(str(port_of(server)), encoding="ascii")
        host = AgentHost(ROOT, tmp_path, backend_factory=busy, startup_timeout=10, poll_interval=0.05)
        try:
            started = time.monotonic()
            assert host.ensure() == f"http://127.0.0.1:{port_of(server)}"
            assert time.monotonic() - started >= 0.04
            assert len(attempts) == 1 and server.calls == 3
            assert host._backend is None and host._watcher is None
        finally:
            host.close()


def test_handover_request_stops_the_owned_backend(tmp_path):
    fake = FakeBackend(ROOT, tmp_path, "http://127.0.0.1:9")
    host = AgentHost(ROOT, tmp_path, backend_factory=lambda root, data: fake, idle_timeout=60, poll_interval=0.02)
    try:
        host.ensure()
        request = tmp_path / HANDOVER_REQUEST
        request.write_text(str(os.getpid()), encoding="ascii")
        assert fake.stopped.wait(10)
        deadline = time.monotonic() + 10
        while request.exists() or (tmp_path / AGENT_HOST_MARKER).exists():
            assert time.monotonic() < deadline, "the agent host kept the folder after handing it over"
            time.sleep(0.02)
    finally:
        host.close()


def test_idle_backend_stops_and_restarts_on_the_next_call(tmp_path):
    made = []

    def factory(root, data):
        made.append(FakeBackend(root, data, f"http://127.0.0.1:{9 + len(made)}"))
        return made[-1]

    host = AgentHost(ROOT, tmp_path, backend_factory=factory, idle_timeout=0.2, poll_interval=0.02)
    try:
        assert host.ensure() == made[0].url
        assert made[0].stopped.wait(10)
        deadline = time.monotonic() + 10
        while (tmp_path / AGENT_HOST_MARKER).exists():
            assert time.monotonic() < deadline
            time.sleep(0.02)
        assert host.ensure() == made[1].url
        assert len(made) == 2
    finally:
        host.close()


def test_bridge_retries_once_after_a_connection_error():
    pytest.importorskip("mcp.server.mcpserver")
    import httpx2 as httpx
    from studio.mcp_server import RestBridge

    class Host:
        calls = 0

        def ensure(self):
            self.calls += 1
            return f"http://127.0.0.1:{4000 + self.calls}"

    seen = []

    def handler(request):
        seen.append(str(request.url))
        if len(seen) == 1:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200, json=[{"id": "p1"}])

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            host = Host()
            assert await RestBridge(client, host=host).list_projects() == [{"id": "p1"}]
            assert host.calls == 2

    asyncio.run(scenario())
    assert seen == ["http://127.0.0.1:4001/api/studio/projects", "http://127.0.0.1:4002/api/studio/projects"]


def test_bridge_uses_the_url_client_without_a_host():
    pytest.importorskip("mcp.server.mcpserver")
    import httpx2 as httpx
    from studio.mcp_server import RestBridge

    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, json={"templates": []})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://127.0.0.1:8000") as client:
            assert await RestBridge(client).catalog() == {"templates": []}

    asyncio.run(scenario())
    assert seen == ["http://127.0.0.1:8000/api/studio/catalog"]


def test_connection_endpoint_offers_desktop_stdio(monkeypatch, tmp_path):
    import main
    from fastapi.testclient import TestClient
    from studio.auth import agent_token

    data = tmp_path / "data"
    workspace = data / "workspace"
    workspace.mkdir(parents=True)
    monkeypatch.setenv("MANIM_API_TOKEN", "desktop-secret")
    monkeypatch.setenv("MANIM_WORKSPACE", str(workspace))
    monkeypatch.setattr(main, "WORKSPACE_DIR", str(workspace))
    client = TestClient(main.app, base_url="http://localhost",
                        headers={"Authorization": "Bearer desktop-secret"})
    body = client.get("/api/studio/connection").json()
    assert body["stdio"] == {
        "command": os.path.abspath(sys.executable),
        "args": ["-B", os.path.join(main.BASE_DIR, "backend", "studio", "mcp_server.py"),
                 "--desktop-data", str(data)],
        "background": True,
    }
    assert body["url"] == "http://localhost/mcp/" and body["token"] == agent_token(str(workspace))


def test_connection_endpoint_offers_dev_stdio(monkeypatch, tmp_path):
    import main
    from fastapi.testclient import TestClient

    workspace = tmp_path / "workspace"
    (workspace / "studio").mkdir(parents=True)
    monkeypatch.delenv("MANIM_API_TOKEN", raising=False)
    monkeypatch.delenv("MANIM_WORKSPACE", raising=False)
    monkeypatch.setattr(main, "WORKSPACE_DIR", str(workspace))
    client = TestClient(main.app, base_url="http://localhost")
    body = client.get("/api/studio/connection").json()
    assert body["stdio"] == {
        "command": os.path.abspath(sys.executable),
        "args": [os.path.join(main.BASE_DIR, "backend", "studio", "mcp_server.py"),
                 "--url", "http://localhost",
                 "--token-file", os.path.join(str(workspace), "studio", "mcp-token")],
        "background": False,
    }


def _child_env():
    ignored = {"MANIM_MCP_TOKEN", "MANIM_API_TOKEN", "MANIM_WORKSPACE", "MANIM_FRONTEND_DIR",
               "COMPOSER_TOKEN", "COMPOSER_URL", "PYTHONHOME", "PYTHONPATH"}
    env = {name: value for name, value in os.environ.items() if name not in ignored}
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _drain(stream, sink):
    try:
        for line in stream:
            sink.put(line)
    finally:
        sink.put(None)


def _drain_text(stream, lines):
    for line in stream:
        lines.append(line.decode("utf-8", errors="replace"))


def _reply(process, messages, request, timeout):
    process.stdin.write((json.dumps(request) + "\n").encode())
    process.stdin.flush()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            line = messages.get(timeout=min(0.5, max(0.01, deadline - time.monotonic())))
        except queue.Empty:
            continue
        if line is None:
            raise AssertionError("The stdio server closed before answering")
        try:
            response = json.loads(line)
        except ValueError:
            continue
        if response.get("id") == request.get("id"):
            return response
    raise AssertionError(f"MCP request {request.get('method')} timed out")


@pytest.mark.skipif(not RUNTIME.is_file() or not (ROOT / "frontend" / "dist" / "index.html").is_file(),
                    reason="prepared desktop runtime or built frontend is missing")
def test_real_stdio_session_starts_and_stops_a_headless_backend(tmp_path):
    import mcp.types

    data = tmp_path / "studio-data"
    messages, stderr_lines = queue.Queue(), []
    port = None
    process = subprocess.Popen(
        [str(RUNTIME), "-B", str(SERVER), "--desktop-data", str(data)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(ROOT),
        env=_child_env(), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    threading.Thread(target=_drain, args=(process.stdout, messages), daemon=True).start()
    threading.Thread(target=_drain_text, args=(process.stderr, stderr_lines), daemon=True).start()
    try:
        init = _reply(process, messages, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                      "params": {"protocolVersion": mcp.types.LATEST_PROTOCOL_VERSION, "capabilities": {},
                                 "clientInfo": {"name": "desktop-test", "version": "1"}}}, 60)
        assert "result" in init and init["result"]["serverInfo"]["name"], init
        process.stdin.write((json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n").encode())
        process.stdin.flush()

        tools = _reply(process, messages, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, 60)
        assert "list_projects" in {tool["name"] for tool in tools["result"]["tools"]}

        projects = _reply(process, messages, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                           "params": {"name": "list_projects", "arguments": {}}}, 180)
        assert "result" in projects and not projects["result"].get("isError"), projects
        assert isinstance(projects["result"].get("content", []), list)

        port = int((data / "desktop-port").read_text(encoding="ascii").strip())
        with socket.socket() as probe:
            assert probe.connect_ex(("127.0.0.1", port)) == 0, "the headless backend is not listening"
        assert (data / "workspace" / "studio" / "mcp-token").is_file()
    finally:
        try:
            process.stdin.close()
        except OSError:
            pass
        try:
            process.wait(timeout=90)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    assert process.returncode == 0, "".join(stderr_lines)[-4000:]
    if port is not None:
        deadline = time.monotonic() + 20
        with socket.socket() as probe:
            while probe.connect_ex(("127.0.0.1", port)) == 0:
                assert time.monotonic() < deadline, "the sidecar survived the stdio session"
                time.sleep(0.1)
    from launcher import WorkspaceLock

    WorkspaceLock(data).close()
