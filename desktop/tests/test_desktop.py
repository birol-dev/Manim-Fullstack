"""Windows integration tests. Run with desktop/.runtime/python.exe -m unittest discover -s desktop/tests -v."""
from __future__ import annotations

import http.cookiejar
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import urllib.error
import urllib.request

DESKTOP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP))
from launcher import AGENT_HOST_MARKER, HANDOVER_REQUEST, Backend, WorkspaceLock, configure_logging, smoke
from sidecar import bind_socket
from win_job import Job
import psutil


def wait_until(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.1)
    raise AssertionError("Condition did not become true before the deadline")


class PortTests(unittest.TestCase):
    def test_port_reused_across_launches(self):
        with tempfile.TemporaryDirectory(prefix="studio-port-") as temporary:
            port_file = Path(temporary) / "desktop-port"
            with bind_socket(port_file) as first:
                port = first.getsockname()[1]
                self.assertEqual(int(port_file.read_text(encoding="ascii")), port)
                self.assertEqual(first.getsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE), 1)
            with bind_socket(port_file) as second:
                self.assertEqual(second.getsockname()[1], port)

    def test_default_port_when_free(self):
        with tempfile.TemporaryDirectory(prefix="studio-port-") as temporary:
            port_file = Path(temporary) / "desktop-port"
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            with mock.patch("sidecar.DEFAULT_PORT", port):
                with bind_socket(port_file) as sock:
                    self.assertEqual(sock.getsockname()[1], port)

    def test_two_data_folders_have_distinct_ports(self):
        with tempfile.TemporaryDirectory(prefix="studio-port-") as temporary:
            first_data, second_data = Path(temporary) / "first", Path(temporary) / "second"
            first_data.mkdir()
            second_data.mkdir()
            with bind_socket(first_data / "desktop-port") as first:
                port = first.getsockname()[1]
                with mock.patch("sidecar.DEFAULT_PORT", port):
                    with bind_socket(second_data / "desktop-port") as second:
                        self.assertNotEqual(second.getsockname()[1], port)

    def test_taken_port_falls_back_and_remembers(self):
        with tempfile.TemporaryDirectory(prefix="studio-port-") as temporary:
            port_file = Path(temporary) / "desktop-port"
            with socket.socket() as taken:
                taken.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                taken.bind(("127.0.0.1", 0))
                taken.listen()
                port = taken.getsockname()[1]
                for remembered in (False, True):
                    with self.subTest(remembered=remembered), mock.patch("sidecar.DEFAULT_PORT", port):
                        if remembered:
                            port_file.write_text(str(port), encoding="ascii")
                        with bind_socket(port_file) as fallback:
                            replacement = fallback.getsockname()[1]
                            self.assertNotEqual(replacement, port)
                            self.assertEqual(int(port_file.read_text(encoding="ascii")), replacement)
                        with bind_socket(port_file) as restarted:
                            self.assertEqual(restarted.getsockname()[1], replacement)


class WindowsTreeTests(unittest.TestCase):
    def test_embedded_runtime_ignores_user_packages(self):
        self.assertTrue(sys.flags.isolated)
        self.assertTrue(sys.flags.no_site)
        self.assertFalse(any("AppData\\Roaming\\Python" in path for path in sys.path))

    def test_job_kills_orphaned_grandchild(self):
        with tempfile.TemporaryDirectory(prefix="studio-job-") as temporary:
            pidfile = Path(temporary) / "pid.json"
            # Parent exits after creating the grandchild; PID-tree enumeration would lose it.
            code = ("import sys,subprocess,json,pathlib; "
                    "sys.stdin.readline(); "
                    "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)'],creationflags=0x08000000); "
                    "pathlib.Path(sys.argv[1]).write_text(json.dumps(p.pid))")
            process = subprocess.Popen([sys.executable, "-c", code, str(pidfile)], stdin=subprocess.PIPE,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            job = Job()
            try:
                job.assign(process.pid)
                process.stdin.write(b"start\n")
                process.stdin.close()
                process.wait(timeout=10)
                pid = json.loads(pidfile.read_text())
                self.assertTrue(psutil.pid_exists(pid))
                job.close()
                wait_until(lambda: not psutil.pid_exists(pid))
            finally:
                job.close()
                if process.poll() is None:
                    process.kill()
                    process.wait()

    def test_workspace_lock_releases(self):
        with tempfile.TemporaryDirectory(prefix="studio-lock-") as temporary:
            first = WorkspaceLock(Path(temporary))
            try:
                with self.assertRaises(RuntimeError):
                    WorkspaceLock(Path(temporary))
            finally:
                first.close()
            WorkspaceLock(Path(temporary)).close()


class HandoverTests(unittest.TestCase):
    def test_second_window_is_refused_without_an_agent_host(self):
        with tempfile.TemporaryDirectory(prefix="studio-handover-") as temporary:
            folder = Path(temporary)
            first = WorkspaceLock(folder)
            try:
                with self.assertRaises(RuntimeError):
                    WorkspaceLock(folder, handover_timeout=5)
                self.assertFalse((folder / HANDOVER_REQUEST).exists())
            finally:
                first.close()

    def test_agent_host_releases_the_folder_for_the_app(self):
        with tempfile.TemporaryDirectory(prefix="studio-handover-") as temporary:
            folder = Path(temporary)
            first = WorkspaceLock(folder)
            (folder / AGENT_HOST_MARKER).write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
            releaser = threading.Timer(0.5, first.close)
            releaser.start()
            try:
                second = WorkspaceLock(folder, handover_timeout=15)
            finally:
                releaser.cancel()
                first.close()
            second.close()
            # The agent host deletes the request once its backend has stopped.
            self.assertTrue((folder / HANDOVER_REQUEST).exists())

    def test_dead_agent_host_marker_does_not_wait(self):
        with tempfile.TemporaryDirectory(prefix="studio-handover-") as temporary:
            folder = Path(temporary)
            first = WorkspaceLock(folder)
            (folder / AGENT_HOST_MARKER).write_text(json.dumps({"pid": 999999999}), encoding="utf-8")
            try:
                with self.assertRaises(RuntimeError):
                    WorkspaceLock(folder, handover_timeout=5)
                self.assertFalse((folder / HANDOVER_REQUEST).exists())
            finally:
                first.close()


class BackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="studio-desktop-")
        cls.data = Path(cls.temporary.name)
        configure_logging(cls.data)
        cls.backend = Backend(DESKTOP.parent, cls.data).start()

    @classmethod
    def tearDownClass(cls):
        pid = cls.backend.process.pid
        port = int(cls.backend.url.rsplit(":", 1)[1])
        cls.backend.stop()
        assert not psutil.pid_exists(pid), "Backend survived graceful shell exit"
        with socket.socket() as probe:
            assert probe.connect_ex(("127.0.0.1", port)) != 0, "Listener survived shell exit"
        # Logging holds the log open, so leave the temporary data under the generated build folder instead.
        import logging
        logging.shutdown()
        cls.temporary.cleanup()

    def status(self, path, *, headers=None, method="GET"):
        request = urllib.request.Request(self.backend.url + path, headers=headers or {}, method=method)
        try:
            with self.backend.http.open(request, timeout=10) as response:
                return response.status
        except urllib.error.HTTPError as error:
            return error.code

    def test_auth_cookie_frontend_and_catalog(self):
        smoke(self.backend)
        for path in ("/", "/api/status", "/api/studio/catalog", "/media/missing.png", "/assets/missing.png"):
            self.assertIn(self.status(path), (401, 403), path)
        self.assertIn(self.status("/api/desktop/session?token=wrong"), (401, 403))
        self.assertEqual(self.status("/__desktop__/ping"), 403)
        self.assertEqual(self.status("/__desktop__/shutdown", method="POST"), 403)

    def test_origin_and_host_rejected_even_with_token(self):
        for path in ("/api/studio/catalog", "/__desktop__/ping"):
            for extra in ({"Origin": "https://example.invalid"}, {"Host": "example.invalid"}):
                headers = {"Authorization": f"Bearer {self.backend.token}", **extra}
                self.assertEqual(self.status(path, headers=headers), 403)

    def test_mcp_does_not_accept_desktop_bearer(self):
        headers = {"Authorization": f"Bearer {self.backend.token}"}
        self.assertIn(self.status("/mcp/", headers=headers), (401, 403))

    def test_websocket_uses_session_cookie(self):
        from websockets.sync.client import connect
        from websockets.exceptions import InvalidStatus
        address = self.backend.url.replace("http://", "ws://") + "/api/render"
        with self.assertRaises(InvalidStatus):
            with connect(address, origin=self.backend.url, proxy=None, open_timeout=5):
                pass
        cookies = http.cookiejar.CookieJar()
        client = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(cookies))
        client.open(self.backend.session_url, timeout=10).close()
        cookie = "; ".join(f"{item.name}={item.value}" for item in cookies)
        with connect(address, origin=self.backend.url, additional_headers={"Cookie": cookie}, proxy=None, open_timeout=5) as ws:
            ws.send('{"type":"ping"}')

    def test_two_sessions_have_distinct_ports_and_credentials(self):
        with tempfile.TemporaryDirectory(prefix="studio-second-") as temporary:
            with Backend(DESKTOP.parent, Path(temporary)) as second:
                self.assertNotEqual(second.url, self.backend.url)
                self.assertNotEqual(second.instance, self.backend.instance)
                self.assertNotEqual(second.token, self.backend.token)
                with self.assertRaises(urllib.error.HTTPError) as error:
                    second.http.open(urllib.request.Request(second.url + "/__desktop__/ping",
                                     headers={"Authorization": f"Bearer {self.backend.token}"}))
                self.assertEqual(error.exception.code, 403)

    def test_port_reused_across_backend_launches(self):
        with tempfile.TemporaryDirectory(prefix="studio-restart-") as temporary:
            data = Path(temporary)
            with Backend(DESKTOP.parent, data) as first:
                address = first.url
            with Backend(DESKTOP.parent, data) as second:
                self.assertEqual(second.url, address)
            with socket.socket() as taken:
                taken.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                taken.bind(("127.0.0.1", int(address.rsplit(":", 1)[1])))
                taken.listen()
                with Backend(DESKTOP.parent, data) as fallback:
                    replacement = fallback.url
                    self.assertNotEqual(replacement, address)
                    self.assertEqual(int((data / "desktop-port").read_text(encoding="ascii")),
                                     int(replacement.rsplit(":", 1)[1]))
                with Backend(DESKTOP.parent, data) as restarted:
                    self.assertEqual(restarted.url, replacement)

    def test_token_never_in_log(self):
        self.assertNotIn(self.backend.token, (self.data / "logs/desktop.log").read_text(encoding="utf-8"))


class PackagingTests(unittest.TestCase):
    def test_packaged_shell_runs_the_desktop_stdio_command(self):
        """A fake packaged tree: mcp_server.py finds agent_host.py in shell/, as package.py copies it."""
        scripts = DESKTOP / "scripts"
        sys.path.insert(0, str(scripts))
        try:
            import package
        finally:
            sys.path.remove(str(scripts))
        with tempfile.TemporaryDirectory(prefix="studio-package-") as temporary:
            root = Path(temporary) / "ManimStudio"
            package.copy_shell(DESKTOP, root / "shell")
            self.assertEqual({entry.name for entry in (root / "shell").iterdir()},
                             {"launcher.py", "sidecar.py", "agent_host.py", "win_job.py"})
            (root / "backend" / "studio").mkdir(parents=True)
            shutil.copy2(DESKTOP.parent / "backend/studio/mcp_server.py",
                         root / "backend/studio/mcp_server.py")
            data = root / "data"
            data.mkdir()
            code = r"""
import json, runpy, sys
server, data = sys.argv[1], sys.argv[2]
module = runpy.run_path(server)
seen = {}
class Stub:
    def __init__(self, bridge, base_url=None):
        seen["bridge"] = type(bridge).__name__
        seen["host_root"] = str(bridge.host.root)
        seen["base_url"] = base_url
    async def run_stdio_async(self):
        seen["ran"] = True
module["main"].__globals__["create_server"] = lambda bridge, base_url=None: Stub(bridge, base_url)
sys.argv = [server, "--desktop-data", data]
module["main"]()
import agent_host
print(json.dumps({"agent_host": agent_host.__file__, "seen": seen}))
"""
            environment = {name: value for name, value in os.environ.items()
                           if name not in {"MANIM_MCP_TOKEN", "MANIM_API_TOKEN", "MANIM_WORKSPACE",
                                           "PYTHONHOME", "PYTHONPATH"}}
            environment["PYTHONIOENCODING"] = "utf-8"
            completed = subprocess.run(
                [sys.executable, "-B", "-c", code, str(root / "backend/studio/mcp_server.py"), str(data)],
                capture_output=True, text=True, timeout=120, cwd=str(root), env=environment,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.assertEqual(completed.returncode, 0, completed.stderr[-4000:])
            report = json.loads(completed.stdout.strip().splitlines()[-1])
            self.assertEqual(Path(report["agent_host"]).resolve(), (root / "shell/agent_host.py").resolve())
            self.assertEqual(report["seen"]["host_root"], str(root.resolve()))
            self.assertEqual(report["seen"]["bridge"], "RestBridge")
            self.assertTrue(report["seen"]["ran"])


class CrashTests(unittest.TestCase):
    def test_owner_crash_closes_backend(self):
        with tempfile.TemporaryDirectory(prefix="studio-crash-") as temporary:
            folder = Path(temporary)
            ready = folder / "ready.json"
            code = ("import pathlib,json,time,sys; from launcher import Backend; "
                    "b=Backend(pathlib.Path(sys.argv[1]),pathlib.Path(sys.argv[2])).start(); "
                    "pathlib.Path(sys.argv[3]).write_text(json.dumps({'pid':b.process.pid})); time.sleep(120)")
            owner = subprocess.Popen([sys.executable, "-c", code, str(DESKTOP.parent), str(folder), str(ready)],
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                wait_until(ready.exists, timeout=90)
                pid = json.loads(ready.read_text())["pid"]
                owner.kill()
                owner.wait(timeout=5)
                wait_until(lambda: not psutil.pid_exists(pid), timeout=15)
            finally:
                if owner.poll() is None:
                    owner.kill()
                    owner.wait()


if __name__ == "__main__":
    unittest.main()
