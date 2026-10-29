"""Native Windows shell and reusable lifecycle supervisor. No frontend changes required."""
from __future__ import annotations

import argparse
import ctypes
import http.cookiejar
import json
import logging
from logging.handlers import RotatingFileHandler
import msvcrt
import os
from pathlib import Path
import queue
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from win_job import Job

SHELL_DIR = Path(__file__).resolve().parent

# An agent host publishes this marker while it owns the workspace lock. The app
# may then ask it to hand the backend over instead of refusing to start.
AGENT_HOST_MARKER = "agent-host.json"
HANDOVER_REQUEST = "handover-request"
HANDOVER_TIMEOUT = 20


def app_data() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        raise RuntimeError("LOCALAPPDATA is unavailable; cannot choose a safe data directory.")
    return Path(base) / "ManimStudio"


class WorkspaceBusy(RuntimeError):
    """Another Studio process owns this data folder."""


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    kernel32.WaitForSingleObject.restype = ctypes.c_ulong
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    process = kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if not process:
        return False
    try:
        return kernel32.WaitForSingleObject(process, 0) == 0x102  # WAIT_TIMEOUT
    finally:
        kernel32.CloseHandle(process)


def agent_host_owner(folder: Path) -> int | None:
    """The live agent host that published ownership of this folder, if any."""
    try:
        record = json.loads((folder / AGENT_HOST_MARKER).read_text(encoding="utf-8"))
        pid = record.get("pid")
    except (OSError, ValueError, AttributeError):
        return None
    if type(pid) is int and _process_alive(pid):
        return pid
    return None


class WorkspaceLock:
    def __init__(self, folder: Path, *, handover_timeout: float = HANDOVER_TIMEOUT):
        folder.mkdir(parents=True, exist_ok=True)
        self.file = (folder / "desktop.lock").open("a+b")
        try:
            # A byte lock prevents even reading that byte from a second Windows handle.
            # Check length without touching it, then catch both the lock and initial I/O.
            self.file.seek(0, 2)
            if self.file.tell() == 0:
                self.file.write(b"0")
                self.file.flush()
            self._acquire()
        except OSError:
            if agent_host_owner(folder) is None:
                self.file.close()
                raise WorkspaceBusy("Studio is already using this data folder. Close its other window first.") from None
            try:
                (folder / HANDOVER_REQUEST).write_text(str(os.getpid()), encoding="ascii")
            except OSError:
                self.file.close()
                raise WorkspaceBusy("Studio is already using this data folder. Close its other window first.") from None
            deadline = time.monotonic() + handover_timeout
            while True:
                try:
                    self._acquire()
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        try:
                            (folder / HANDOVER_REQUEST).unlink()
                        except OSError:
                            pass
                        self.file.close()
                        raise WorkspaceBusy(
                            "Studio's background agent did not release this data folder. Close it and try again."
                        ) from None
                    time.sleep(0.1)

    def _acquire(self):
        self.file.seek(0)
        msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)

    def close(self):
        if not self.file.closed:
            self.file.seek(0)
            msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            self.file.close()


class Backend:
    def __init__(self, root: Path, data: Path, python: Path | None = None, timeout: float = 90):
        self.root, self.data = root.resolve(), data.resolve()
        self.frontend = self.root / "frontend/dist"
        if self.root == SHELL_DIR.parent and (SHELL_DIR / "build/frontend/index.html").is_file():
            self.frontend = SHELL_DIR / "build/frontend"
        self.python = python or Path(sys.executable).with_name("python.exe")
        self.timeout = timeout
        self.token, self.instance = secrets.token_urlsafe(32), secrets.token_hex(16)
        self.process = self.job = self.lock = None
        self.url = None
        # Ignore system proxy settings for all loopback requests.
        self.http = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, path: str, method="GET", *, authenticated=True):
        headers = {"Authorization": f"Bearer {self.token}"} if authenticated else {}
        return self.http.open(urllib.request.Request(self.url + path, headers=headers, method=method), timeout=3)

    @property
    def session_url(self):
        return self.url + "/api/desktop/session?token=" + urllib.parse.quote(self.token, safe="")

    def start(self):
        try:
            self._start()
            return self
        except BaseException:
            self.stop()
            raise

    def _start(self):
        if not (self.frontend / "index.html").is_file():
            raise RuntimeError("Built frontend missing. Run desktop/dev.ps1 to build it first.")
        self.lock = WorkspaceLock(self.data)
        for name in ("workspace", "logs", "cache", "tmp", "webview"):
            (self.data / name).mkdir(exist_ok=True)
        env = os.environ.copy()
        for name in ("PYTHONHOME", "PYTHONPATH", "MANIM_MCP_TOKEN", "COMPOSER_JOB"):
            env.pop(name, None)
        env.update({"MANIM_API_TOKEN": self.token, "MANIM_WORKSPACE": str(self.data / "workspace"),
                    "MANIM_FRONTEND_DIR": str(self.frontend), "MANIM_ALLOW_INSTALLS": "0",
                    "MANIM_ALLOW_LAN": "0", "MANIM_ALLOWED_ORIGINS": "", "MANIM_DEV_ORIGIN_PORTS": "",
                    "STUDIO_DESKTOP_INSTANCE": self.instance, "PYTHONIOENCODING": "utf-8",
                    "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
                    "XDG_CACHE_HOME": str(self.data / "cache"), "TEMP": str(self.data / "tmp"),
                    "TMP": str(self.data / "tmp")})
        # Embedded runtime and optional app-local tools only, ahead of Windows OS tools.
        system = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        env["PATH"] = os.pathsep.join(map(str, (self.python.parent, self.python.parent / "Scripts",
                                               self.root / "tools", system / "System32", system)))
        self.job = Job()
        self.process = subprocess.Popen([str(self.python), "-B", "-u", str(SHELL_DIR / "sidecar.py"),
                                         "--app-root", str(self.root), "--data-dir", str(self.data)],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        env=env, cwd=self.data, creationflags=subprocess.CREATE_NO_WINDOW)
        # Sidecar blocks on stdin before importing backend code or starting any children.
        self.job.assign(self.process.pid)
        messages = queue.Queue()

        def stdout_reader():
            try:
                for line in self.process.stdout:
                    if len(line) > 4096:
                        continue
                    try:
                        messages.put(json.loads(line))
                    except (ValueError, UnicodeDecodeError):
                        pass  # Never log bootstrap credentials or arbitrary stdout.
            finally:
                messages.put(None)

        def stderr_reader():
            for line in self.process.stderr:
                text = line.decode("utf-8", errors="replace").rstrip().replace(self.token, "[redacted]")
                logging.getLogger("studio.backend").warning(text)

        threading.Thread(target=stdout_reader, daemon=True).start()
        threading.Thread(target=stderr_reader, daemon=True).start()
        self.process.stdin.write(b"start\n")
        self.process.stdin.flush()
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            try:
                info = messages.get(timeout=min(0.25, max(0.01, deadline - time.monotonic())))
            except queue.Empty:
                if self.process.poll() is not None:
                    raise RuntimeError("Studio's local service exited. See logs in the data folder.")
                continue
            if info is None:
                raise RuntimeError("Studio's local service failed to start. See logs in the data folder.")
            if not isinstance(info, dict) or info.get("instance") != self.instance:
                continue
            port = info.get("port")
            if info.get("protocol") != 1 or info.get("pid") != self.process.pid or type(port) is not int or not 0 < port < 65536:
                raise RuntimeError("Invalid local service handshake.")
            self.url = f"http://127.0.0.1:{port}"
            with self.request("/__desktop__/ping") as response:
                if json.load(response) != {"instance": self.instance, "pid": self.process.pid}:
                    raise RuntimeError("Local service identity check failed.")
            # Fail closed if an older backend ignores MANIM_API_TOKEN.
            for path in ("/api/status", "/", "/api/studio/catalog"):
                try:
                    self.request(path, authenticated=False).close()
                except urllib.error.HTTPError as exc:
                    if exc.code in (401, 403):
                        continue
                    raise RuntimeError("Unexpected desktop authentication response.") from exc
                raise RuntimeError("Backend must enforce MANIM_API_TOKEN on all routes before desktop launch.")
            logging.info("Local service ready (pid %s, port %s)", self.process.pid, port)
            return
        raise RuntimeError("Studio's local service did not become ready within the startup deadline.")

    def stop(self):
        if self.process is not None:
            if self.url and self.process.poll() is None:
                try:
                    self.request("/__desktop__/shutdown", method="POST").close()
                except (OSError, urllib.error.URLError):
                    pass
            if self.process.stdin and not self.process.stdin.closed:
                try:
                    self.process.stdin.close()
                except OSError:
                    pass
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
        if self.job is not None:
            self.job.close()  # also kills orphaned render grandchildren
            self.job = None
        if self.process is not None:
            if self.process.poll() is None:
                self.process.kill()  # only our direct child if Job assignment failed
            self.process.wait(timeout=5)
            for stream in (self.process.stdout, self.process.stderr):
                if stream:
                    stream.close()
        if self.lock is not None:
            self.lock.close()
            self.lock = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *_):
        self.stop()


def configure_logging(data: Path):
    logs = data / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(logs / "desktop.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(asctime)s %(levelname)s %(message)s", force=True)


def smoke(backend: Backend):
    cookies = http.cookiejar.CookieJar()
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(cookies))
    with client.open(backend.session_url, timeout=10) as response:
        if response.url != backend.url + "/" or b"<html" not in response.read().lower():
            raise RuntimeError("Session bootstrap did not redirect to the built frontend.")
    if not any(c.has_nonstandard_attr("HttpOnly") and c.get_nonstandard_attr("SameSite", "").lower() == "strict" for c in cookies):
        raise RuntimeError("Desktop session must use an HttpOnly SameSite=Strict cookie.")
    with client.open(backend.url + "/api/studio/catalog", timeout=15) as response:
        catalog = json.load(response)
    if not catalog:
        raise RuntimeError("Studio catalog is empty.")
    print("Desktop smoke passed: authenticated instance, session cookie, static frontend, studio catalog.")


def main():
    if os.environ.pop("STUDIO_HOST_GATE", "") == "1":
        if sys.stdin.readline() != "start\n":
            return 2
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-root", type=Path, default=SHELL_DIR.parent)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--smoke", action="store_true", help="Check the local service without opening a window.")
    parser.add_argument("--ui-smoke", action="store_true", help="Open WebView2, check React and cookie fetch, then close.")
    args = parser.parse_args()
    data = (args.data_dir or app_data()).resolve()
    configure_logging(data)
    try:
        with Backend(args.app_root, data) as backend:
            if args.smoke:
                smoke(backend)
                return 0
            import webview
            # No custom Python API is exposed to page JavaScript.
            webview.settings["ALLOW_DOWNLOADS"] = True
            webview.settings["ALLOW_FILE_URLS"] = False
            webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = False
            window = webview.create_window("Manim Studio", backend.session_url, width=1400, height=920,
                                           min_size=(1000, 680), text_select=True, background_color="#101216")
            def restrict_navigation():
                # This adapter is intentionally specific to pinned PyWebView's WebView2 backend.
                def navigating(_sender, event):
                    url = urllib.parse.urlsplit(str(event.Uri))
                    if str(event.Uri) != "about:blank" and f"{url.scheme}://{url.netloc}" != backend.url:
                        event.Cancel = True
                window.native.webview.NavigationStarting += navigating
            window.events.before_show += restrict_navigation
            stop = threading.Event()
            results = []
            window.events.closed += lambda: stop.set()

            def monitor():
                deadline = time.monotonic() + 60
                while not stop.wait(0.5):
                    if backend.process.poll() is not None:
                        logging.error("Local service stopped unexpectedly")
                        ctypes.windll.user32.MessageBoxW(None, "Studio's local service stopped. Reopen Studio to restart it.", "Manim Studio", 0x10)
                        window.destroy()
                        return
                    if args.ui_smoke:
                        try:
                            ready = threading.Event()
                            reply = []
                            def received(value):
                                reply.append(value)
                                ready.set()
                            window.evaluate_js("""(async () => ({
                              url: location.href, rendered: !!document.getElementById('root')?.children.length,
                              status: (await fetch('/api/studio/catalog')).status,
                              cookieHidden: !document.cookie.includes('manim_session=')
                            }))()""", callback=received)
                            ready.wait(3)
                            result = reply[0] if reply else None
                            if result and result.get("rendered") and result.get("status") == 200:
                                results.append(result)
                                window.destroy()
                                return
                        except Exception:
                            pass  # bootstrap and React may still be loading
                        if time.monotonic() > deadline:
                            window.destroy()
                            return

            webview.start(monitor, gui="edgechromium", debug=False, private_mode=True,
                          storage_path=str(data / "webview"))
            if args.ui_smoke:
                if not results or results[0]["url"] != backend.url + "/":
                    raise RuntimeError("WebView2 smoke did not render React with an authenticated same-origin fetch.")
                print("WebView2 smoke passed: React mounted; cookie-authenticated catalog fetched; token removed from URL.")
        return 0
    except Exception as exc:
        logging.exception("Desktop launch failed")
        message = f"{exc}\n\nLogs: {data / 'logs/desktop.log'}"
        if args.smoke or args.ui_smoke:
            print(message, file=sys.stderr)
        else:
            ctypes.windll.user32.MessageBoxW(None, message, "Manim Studio", 0x10)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
