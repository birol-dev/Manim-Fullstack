"""Keep Manim Studio available to an MCP client whether or not the app is open.

The stdio MCP server runs with the desktop runtime Python. This host reuses a
backend that is already listening (the app's, or another agent host's), starts a
headless one when nothing answers, yields the data folder when the app asks for
it, and stops an idle backend so a forgotten AI session leaves nothing running.
No Manim imports are needed here, so the stdio process can import this first.
"""
from __future__ import annotations

import http.client
import json
import os
from pathlib import Path
import sys
import threading
import time
import urllib.request

from launcher import AGENT_HOST_MARKER, HANDOVER_REQUEST, Backend, WorkspaceBusy
from sidecar import DEFAULT_PORT

CATALOG_PATH = "/api/studio/catalog"


class AgentHost:
    def __init__(self, root, data, *, backend_factory=None, idle_timeout: float = 600,
                 startup_timeout: float = 90, poll_interval: float = 0.5, ping_timeout: float = 2,
                 stale_request_age: float = 60):
        self.root = Path(root).resolve()
        self.data = Path(data).resolve()
        self.data.mkdir(parents=True, exist_ok=True)
        self.idle_timeout = float(idle_timeout)
        self.startup_timeout = float(startup_timeout)
        self.poll_interval = float(poll_interval)
        self.ping_timeout = float(ping_timeout)
        self.stale_request_age = float(stale_request_age)
        self._backend_factory = backend_factory or Backend
        self._clock = time.monotonic
        self._http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self._lock = threading.RLock()
        self._backend = None
        self._token = None
        self._last_use = self._clock()
        self._generation = 0
        self._watch_stop = None
        self._watcher = None
        self._stopped = False

    @property
    def token(self) -> str:
        with self._lock:
            return self._agent_token()

    @property
    def base_url(self) -> str:
        """The best guess for links before the backend starts; the port is remembered."""
        return self._endpoint(self._port() or DEFAULT_PORT)

    def ensure(self) -> str:
        """Return a live backend base URL, starting one only when nothing answers."""
        with self._lock:
            if self._stopped:
                raise RuntimeError("The Studio agent host has stopped.")
            self._last_use = self._clock()
            base = self._ping()
            if base:
                return base
            if self._backend is not None:
                self._release()
            self._discard_stale_request()
            try:
                backend = self._backend_factory(self.root, self.data)
                backend.start()
            except WorkspaceBusy:
                # Another Studio process owns the folder and is still starting its
                # listener; wait for it instead of failing the agent's first call.
                return self._await_backend()
            self._backend = backend
            self._publish()
            return backend.url

    def close(self):
        """Stop the backend this host owns and release the folder (stdin EOF / exit)."""
        with self._lock:
            if self._stopped:
                return
            self._stopped = True
            owned = self._backend is not None
            self._release()
            if owned:
                self._drop_request()

    def _agent_token(self) -> str:
        if self._token is None:
            backend = str(self.root / "backend")
            if backend not in sys.path:
                sys.path.insert(0, backend)
            from studio.auth import agent_token

            self._token = agent_token(str(self.data / "workspace"))
        return self._token

    def _port(self) -> int | None:
        try:
            port = int((self.data / "desktop-port").read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            return None
        return port if 0 < port < 65536 else None

    @staticmethod
    def _endpoint(port: int) -> str:
        return f"http://127.0.0.1:{port}"

    def _ping(self) -> str | None:
        port = self._port()
        if port is None:
            return None
        request = urllib.request.Request(self._endpoint(port) + CATALOG_PATH,
                                         headers={"Authorization": f"Bearer {self._agent_token()}"})
        try:
            with self._http.open(request, timeout=self.ping_timeout) as response:
                healthy = response.status == 200
                response.read(1)
        except (OSError, ValueError, http.client.HTTPException):
            return None
        return self._endpoint(port) if healthy else None

    def _await_backend(self) -> str:
        deadline = self._clock() + self.startup_timeout
        while self._clock() < deadline:
            if self._stopped:
                raise RuntimeError("The Studio agent host has stopped.")
            base = self._ping()
            if base:
                return base
            time.sleep(self.poll_interval)
        raise RuntimeError("Another Studio process owns this data folder but did not start in time.")

    def _publish(self):
        try:
            (self.data / AGENT_HOST_MARKER).write_text(
                json.dumps({"pid": os.getpid(), "url": self._backend.url, "started": int(time.time())}),
                encoding="utf-8")
        except OSError:
            pass  # The agent still works; the app simply cannot ask it to hand over.
        self._generation += 1
        stop = threading.Event()
        self._watch_stop = stop
        self._watcher = threading.Thread(target=self._watch, args=(stop, self._generation),
                                         name="studio-agent-host", daemon=True)
        self._watcher.start()

    def _release(self):
        backend, self._backend = self._backend, None
        self._generation += 1
        if self._watch_stop is not None:
            self._watch_stop.set()
            self._watch_stop = None
        self._watcher = None
        if backend is None:
            return
        try:
            backend.stop()
        finally:
            try:
                (self.data / AGENT_HOST_MARKER).unlink()
            except OSError:
                pass

    def _watch(self, stop: threading.Event, generation: int):
        while not stop.wait(self.poll_interval):
            with self._lock:
                if generation != self._generation or self._backend is None:
                    return
                if (self.data / HANDOVER_REQUEST).is_file():
                    try:
                        self._release()
                    except Exception as exc:  # keep the failure visible without killing stdio
                        print(f"Studio agent host: handover failed: {exc}", file=sys.stderr)
                        return
                    self._drop_request()
                    return
                if self._clock() - self._last_use >= self.idle_timeout:
                    try:
                        self._release()
                    except Exception as exc:
                        print(f"Studio agent host: idle stop failed: {exc}", file=sys.stderr)
                    return

    def _drop_request(self):
        try:
            (self.data / HANDOVER_REQUEST).unlink()
        except OSError:
            pass

    def _discard_stale_request(self):
        request = self.data / HANDOVER_REQUEST
        try:
            if time.time() - request.stat().st_mtime > self.stale_request_age:
                request.unlink()
        except OSError:
            pass
