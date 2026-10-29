"""The warm preview worker: one long-lived process with Manim imported once.

Importing Manim takes ~3 s; a poster in a warm process takes well under a second. The
service owns one ``PreviewWorker`` (the parent side, below) and sends it one job at a
time. The child runs ``python -m studio.worker`` from the backend folder.

Protocol (JSON lines, UTF-8):

* parent -> child, on the child's stdin, one request per line::

      {"id": 7, "op": "render", "job": {...}, "width": 640, "height": 360, "media_dir": "..."}
      {"id": 8, "op": "ping"}
      {"op": "quit"}

  ``job`` is a kit render job (``template params settings mode assets_dir output``);
  ``mode`` is ``poster`` or ``storyboard``; ``media_dir`` is Manim's scratch folder.

* child -> parent: every protocol line starts with ``@@studio `` and is written to a
  private copy of the original stdout. The child points its own fd 1 (and
  ``sys.stdout``) at stderr before importing Manim, so prints and Manim's console
  chatter go to stderr and can never be mistaken for a reply::

      @@studio {"event": "ready", "pid": 123, "manim": "0.19.0", "import_ms": 3100}
      @@studio {"event": "fatal", "error": "ModuleNotFoundError: No module named 'manim'"}
      @@studio {"id": 7, "ok": true, "ms": 412, "output": "...png", "storyboard": {...}}
      @@studio {"id": 7, "ok": false, "error": "ValueError: ...", "traceback": "..."}

The child exits on ``quit`` or when its stdin closes (the parent went away). Template
modules are cached and re-imported when the template's files change on disk; kit
changes need a new process (the service restarts it).
"""

from __future__ import annotations

import itertools
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from typing import Optional

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIX = "@@studio "
MODES = ("poster", "storyboard", "motion")

# --------------------------------------------------------------------------- #
# Child process
# --------------------------------------------------------------------------- #


def _claim_protocol_channel():
    """Keep the real stdout for replies; send fd 1 and sys.stdout to stderr."""
    sys.stdout.flush()
    fd = os.dup(1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    return os.fdopen(fd, "wb", buffering=0)


class _Child:
    def __init__(self, channel):
        self.channel = channel
        self.templates = {}  # id -> (fingerprint, Template class)

    def send(self, message: dict) -> None:
        data = (PREFIX + json.dumps(message, ensure_ascii=True, default=str) + "\n").encode("ascii")
        view = memoryview(data)
        while view:  # an unbuffered pipe write may be partial
            written = self.channel.write(view)
            view = view[written or 0:]

    # -- templates -------------------------------------------------------------
    def template_class(self, template_id: str):
        import importlib

        from studio import registry
        from studio.storage import template_dir, tree_fingerprint

        registry.get_template(template_id)  # refuses ids that aren't installed templates
        fingerprint = tree_fingerprint(template_dir(template_id))
        hit = self.templates.get(template_id)
        if hit is not None and hit[0] == fingerprint:
            return hit[1]
        if hit is not None:
            # Edited on disk: forget the old modules so the import below reads the new files.
            package = f"{registry.PACKAGE}.{template_id}"
            for name in [n for n in sys.modules if n == package or n.startswith(package + ".")]:
                del sys.modules[name]
            registry._cache.pop(template_id, None)
            importlib.invalidate_caches()
            registry.get_template(template_id)
        module = importlib.import_module(f"{registry.PACKAGE}.{template_id}.scene")
        self.templates[template_id] = (fingerprint, module.Template)
        return module.Template

    # -- requests --------------------------------------------------------------
    def render(self, request: dict) -> dict:
        from manim import tempconfig

        from studio.formats import frame_size
        from studio.kit import runtime

        rid = request.get("id")
        job = dict(request.get("job") or {})
        mode = job.get("mode")
        out = job.get("output")
        if mode not in MODES or not out:
            return {"id": rid, "ok": False, "error": "A render needs mode poster/storyboard/motion and an output path."}
        started = time.perf_counter()
        try:
            width, height = int(request["width"]), int(request["height"])
            frame_width, frame_height = frame_size(width, height)
            cls = self.template_class(job["template"])
            background = ((job.get("settings") or {}).get("background") or {})
            cfg = {
                "pixel_width": width,
                "pixel_height": height,
                "frame_width": frame_width,
                "frame_height": frame_height,
                "save_last_frame": mode != "motion",
                "write_to_movie": mode == "motion",
                "frame_rate": 15,
                "format": "mp4",
                "output_file": os.path.splitext(os.path.basename(out))[0],
                "disable_caching": True,
                "media_dir": request.get("media_dir") or os.path.join(os.path.dirname(out), "_media"),
                "verbosity": "ERROR",
                "progress_bar": "none",
                "transparent": mode != "motion" and background.get("kind") == "transparent",
            }
            for stale in (out, os.path.splitext(out)[0] + ".json"):
                if os.path.exists(stale):
                    os.unlink(stale)
            runtime.set_job(job)
            try:
                with tempconfig(cfg):
                    scene = cls()
                    scene.render()
                    if mode == "motion":
                        shutil.copyfile(scene.renderer.file_writer.movie_file_path, out)
            finally:
                runtime.set_job(None)
        except (Exception, SystemExit) as exc:
            import traceback

            return {"id": rid, "ok": False, "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc(limit=-12)}
        if not os.path.isfile(out):
            return {"id": rid, "ok": False, "error": "The template finished without writing an image."}
        reply = {"id": rid, "ok": True, "ms": round((time.perf_counter() - started) * 1000), "output": out}
        if mode == "motion":
            reply.update(duration=round(scene.elapsed, 2), truncated=scene.elapsed >= job["max_duration"] - 1 / 15)
        if mode == "storyboard":
            try:
                with open(os.path.splitext(out)[0] + ".json", encoding="utf-8") as f:
                    reply["storyboard"] = json.load(f)
            except (OSError, ValueError) as exc:
                return {"id": rid, "ok": False, "error": f"The storyboard metadata is missing ({exc})."}
        return reply

    def serve(self, stdin) -> int:
        while True:
            raw = stdin.readline()
            if not raw:
                return 0  # the parent closed the pipe (or died)
            try:
                request = json.loads(raw.decode("utf-8"))
                if not isinstance(request, dict):
                    raise ValueError("not an object")
            except ValueError as exc:
                self.send({"id": None, "ok": False, "error": f"Bad request line: {exc}"})
                continue
            op = request.get("op")
            if op == "quit":
                return 0
            if op == "ping":
                self.send({"id": request.get("id"), "ok": True, "pid": os.getpid()})
            elif op == "render":
                self.send(self.render(request))
            else:
                self.send({"id": request.get("id"), "ok": False, "error": f"Unknown op {op!r}."})


def child_main(argv=None) -> int:
    channel = _claim_protocol_channel()
    if BACKEND_DIR not in sys.path:
        sys.path.insert(0, BACKEND_DIR)
    child = _Child(channel)
    started = time.perf_counter()
    try:
        import manim
        from manim import config

        from studio.kit import fonts

        media_dir = os.environ.get("STUDIO_WORKER_MEDIA")
        if media_dir:
            # Anything Manim writes before the first job's tempconfig (text caches) goes here.
            config.media_dir = media_dir
        fonts.available_families()  # registers bundled fonts and lists the installed ones (slow once)
    except BaseException as exc:  # noqa: BLE001 - report anything, then exit
        child.send({"event": "fatal", "error": f"{type(exc).__name__}: {exc}"})
        return 3
    try:
        # Manim keeps its own font list (another ~1.5 s list_fonts on first Text) and Pango
        # has a first-layout cost: pay both now rather than in the first preview.
        from manim import Text

        if hasattr(Text, "font_list"):
            Text.font_list()
        if os.environ.get("STUDIO_WORKER_MEDIA"):  # Text writes an SVG into media_dir/texts
            Text("Aa", font=fonts.resolve("Inter"))
    except Exception:  # noqa: BLE001 - warm-up only
        pass
    child.send({"event": "ready", "pid": os.getpid(), "manim": getattr(manim, "__version__", "?"),
                "import_ms": round((time.perf_counter() - started) * 1000)})
    try:
        return child.serve(sys.stdin.buffer)
    except KeyboardInterrupt:
        return 0


# --------------------------------------------------------------------------- #
# Parent side
# --------------------------------------------------------------------------- #

_EOF = object()


class WorkerStartError(RuntimeError):
    """The worker could not start (it reported a fatal error or exited)."""


class WorkerTimeout(RuntimeError):
    pass


class WorkerCrashed(RuntimeError):
    pass


class WorkerCancelled(RuntimeError):
    pass


class WorkerReplyError(RuntimeError):
    """The worker is fine, but the job failed; ``traceback`` comes from the child."""

    def __init__(self, message: str, traceback: str = ""):
        super().__init__(message)
        self.traceback = traceback


def _read_replies(stream, replies: "queue.Queue", chatter: deque) -> None:
    try:
        for raw in iter(stream.readline, b""):
            text = raw.decode("utf-8", "replace").rstrip("\r\n")
            if text.startswith(PREFIX):
                try:
                    replies.put(json.loads(text[len(PREFIX):]))
                    continue
                except ValueError:
                    pass
            if text.strip():
                chatter.append(text)
    except (OSError, ValueError):
        pass
    finally:
        replies.put(_EOF)


def _drain(stream, lines: deque) -> None:
    try:
        for raw in iter(stream.readline, b""):
            text = raw.decode("utf-8", "replace").rstrip("\r\n")
            if text.strip():
                lines.append(text)
    except (OSError, ValueError):
        pass


class PreviewWorker:
    """Parent side of the worker: blocking and thread-safe (one request at a time).

    Starts the child on first use, restarts it after a crash or a timeout (the timed
    out child is killed), and recycles it after ``max_jobs`` renders.
    """

    def __init__(self, *, command=None, cwd: str = BACKEND_DIR, env: Optional[dict] = None,
                 media_dir: Optional[str] = None, start_timeout: float = 90.0, request_timeout: float = 45.0,
                 max_jobs: int = 200, log_lines: int = 200):
        self.command = list(command) if command else [sys.executable, "-u", "-m", "studio.worker"]
        self.cwd = cwd
        self.extra_env = dict(env or {})
        self.media_dir = media_dir
        self.start_timeout = start_timeout
        self.request_timeout = request_timeout
        self.max_jobs = max_jobs
        self.log = deque(maxlen=log_lines)  # the child's stderr (and stray stdout), for errors
        self.info: dict = {}
        self.starts = 0
        self.jobs = 0  # jobs done by the current process
        self._lock = threading.Lock()
        self._closing = False
        self._proc: Optional[subprocess.Popen] = None
        self._replies: Optional[queue.Queue] = None
        self._ids = itertools.count(1)

    # -- lifecycle -------------------------------------------------------------
    @property
    def alive(self) -> bool:
        proc = self._proc
        return proc is not None and proc.poll() is None

    @property
    def pid(self) -> Optional[int]:
        proc = self._proc
        return proc.pid if proc is not None and proc.poll() is None else None

    def _env(self) -> dict:
        env = dict(os.environ)
        env.pop("COMPOSER_JOB", None)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        if self.media_dir:
            env["STUDIO_WORKER_MEDIA"] = self.media_dir
        env.update(self.extra_env)
        return env

    def _spawn(self) -> None:
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        else:
            kwargs["start_new_session"] = True  # Ctrl+C in the server's terminal isn't for us
        if self.media_dir:
            shutil.rmtree(self.media_dir, ignore_errors=True)
            os.makedirs(self.media_dir, exist_ok=True)
        proc = subprocess.Popen(self.command, cwd=self.cwd, env=self._env(), stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
        replies: queue.Queue = queue.Queue()
        threading.Thread(target=_read_replies, args=(proc.stdout, replies, self.log),
                         name="studio-worker-out", daemon=True).start()
        threading.Thread(target=_drain, args=(proc.stderr, self.log), name="studio-worker-err",
                         daemon=True).start()
        self._proc, self._replies = proc, replies
        self.jobs = 0
        self.starts += 1

    def _check_closing(self) -> None:
        if self._closing:
            raise WorkerCrashed("The preview worker is closing.")

    def _ensure_started(self) -> None:
        self._check_closing()
        if self.alive:
            return
        self._kill()
        self.log.clear()
        self._spawn()
        self._check_closing()
        replies = self._replies
        deadline = time.monotonic() + self.start_timeout
        while True:
            remaining = deadline - time.monotonic()
            try:
                message = replies.get(timeout=max(remaining, 0.01))
            except queue.Empty:
                self._kill()
                raise WorkerTimeout(f"The preview worker did not start within {self.start_timeout:.0f} s.")
            self._check_closing()
            if message is _EOF:
                self._kill()
                raise WorkerStartError("The preview worker exited while starting. " + self.tail(6))
            if isinstance(message, dict) and message.get("event") == "fatal":
                self._kill()
                raise WorkerStartError(f"The preview worker could not load Manim: {message.get('error')}")
            if isinstance(message, dict) and message.get("event") == "ready":
                self.info = message
                return

    def start(self) -> dict:
        """Start the child now (warm-up). Returns its ready message."""
        with self._lock:
            self._ensure_started()
            return dict(self.info)

    def tail(self, lines: int = 8) -> str:
        return " | ".join(list(self.log)[-lines:])

    def _kill(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        if proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass
        try:
            proc.wait(timeout=5)
        except (subprocess.TimeoutExpired, OSError):
            pass
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            try:
                if stream:
                    stream.close()
            except OSError:
                pass

    def stop(self, timeout: float = 3.0) -> None:
        """Ask the child to quit after its current job (waits for it), then make sure it's gone."""
        with self._lock:
            self._stop_locked(timeout)

    def _stop_locked(self, timeout: float) -> None:
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                proc.stdin.write(b'{"op": "quit"}\n')
                proc.stdin.flush()
                proc.wait(timeout=timeout)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                pass
        self._kill()

    def close(self) -> None:
        """Kill the child now, without waiting for a job in progress (app shutdown)."""
        self._closing = True
        try:
            self._kill()
            with self._lock:
                self._kill()  # startup may have spawned a child while close was waiting
        finally:
            self._closing = False

    # -- requests --------------------------------------------------------------
    def request(self, payload: dict, timeout: Optional[float] = None, cancel=None) -> dict:
        with self._lock:
            return self._request_locked(payload, self.request_timeout if timeout is None else timeout, cancel)

    def _request_locked(self, payload: dict, timeout: float, cancel=None) -> dict:
        for attempt in (1, 2):
            if cancel is not None and cancel.is_set():
                raise WorkerCancelled()
            self._ensure_started()
            rid = next(self._ids)
            line = json.dumps({**payload, "id": rid}, ensure_ascii=True) + "\n"
            proc, replies = self._proc, self._replies
            self._check_closing()
            try:
                proc.stdin.write(line.encode("ascii"))
                proc.stdin.flush()
            except (OSError, ValueError):
                # It died between jobs; the job never reached it, so a new one may run it.
                self._kill()
                if attempt == 1:
                    continue
                raise WorkerCrashed("The preview worker stopped. " + self.tail(6))
            deadline = time.monotonic() + timeout
            while True:
                if cancel is not None and cancel.is_set():
                    self._kill()
                    raise WorkerCancelled()
                remaining = deadline - time.monotonic()
                try:
                    message = replies.get(timeout=max(min(remaining, 0.1) if cancel is not None else remaining, 0.01))
                except queue.Empty:
                    if remaining > 0 and cancel is not None:
                        continue
                    self._kill()
                    raise WorkerTimeout(f"The preview took longer than {timeout:.0f} s and was stopped.")
                self._check_closing()
                if message is _EOF:
                    self._kill()
                    raise WorkerCrashed("The preview worker crashed. " + self.tail(6))
                if isinstance(message, dict) and message.get("id") == rid:
                    break
            self.jobs += 1
            if self.max_jobs and self.jobs >= self.max_jobs:
                self._stop_locked(3.0)  # recycle: the next request starts a fresh process
                if self.media_dir:
                    shutil.rmtree(self.media_dir, ignore_errors=True)
            return message
        raise WorkerCrashed("The preview worker stopped.")  # pragma: no cover - loop always returns

    def render(self, job: dict, width: int, height: int, media_dir: Optional[str] = None,
               timeout: Optional[float] = None, cancel=None) -> dict:
        """Render a poster or storyboard; returns the child's reply or raises WorkerReplyError."""
        reply = self.request({"op": "render", "job": job, "width": int(width), "height": int(height),
                              "media_dir": media_dir or self.media_dir}, timeout, cancel)
        if not reply.get("ok"):
            raise WorkerReplyError(reply.get("error") or "The preview failed.", reply.get("traceback") or "")
        return reply


if __name__ == "__main__":
    sys.exit(child_main())
