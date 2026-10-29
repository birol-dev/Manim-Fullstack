"""Export queue: one export at a time, in a background thread, each video in its own Manim process.

    manim -r W,H --fps F [--format gif|webm|mov] [--transparent] --media_dir <job>/media \
          backend/studio/runner.py StudioRender          (env COMPOSER_JOB=<job>/job.json)

Videos run through ``executor.ManimExecutor`` (output streaming, progress parsing, the
render timeout, process-tree cancel), with their own executor instance and job folder,
so they never share the IDE's render queue or media folders. PNG exports are a
full-resolution poster from the warm preview worker.

State lives in memory and in a small JSON index (``workspace/studio/exports.json``)
so the list survives a restart; exports that were queued or rendering when the app
stopped come back as ``failed``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import secrets
import shutil
import sys
import threading
from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional

from .errors import BusyError, NotFoundError, StudioError
from .storage import STUDIO_DIR, utc_now

BACKEND_DIR = os.path.dirname(STUDIO_DIR)
if BACKEND_DIR not in sys.path:  # executor / file_ops are top-level backend modules
    sys.path.insert(0, BACKEND_DIR)

import file_ops  # noqa: E402

logger = logging.getLogger("studio.exports")

RUNNER_PATH = os.path.join(STUDIO_DIR, "runner.py")
SCENE_NAME = "StudioRender"
EXPORT_FORMATS = ("mp4", "gif", "webm", "mov", "png")
ACTIVE = ("queued", "rendering")
FINISHED = ("done", "failed", "cancelled")
INTERRUPTED = "Interrupted: the app stopped before this export finished."
_EXPORT_ID = re.compile(r"^[0-9a-f]{12}$")
_ERROR_LINE = re.compile(r"\b[A-Za-z_][\w.]*(?:Error|Exception)\b")
_BOX_CHARS = "│┃╭╰─━┏┗┓┛╮╯"


class ConflictError(StudioError):
    status = 409


class ExportCancelled(Exception):
    pass


class ExportFailed(Exception):
    pass


@dataclass
class VideoJob:
    job_dir: str
    job_file: str
    media_dir: str
    width: int
    height: int
    fps: int
    format: str
    transparent: bool
    timeout: float


def default_render_timeout() -> float:
    from executor import DEFAULT_RENDER_TIMEOUT_SECONDS  # reads MANIM_RENDER_TIMEOUT

    return float(DEFAULT_RENDER_TIMEOUT_SECONDS)


class ManimVideoRunner:
    """Renders one VideoJob with ManimExecutor. ``run`` blocks; ``cancel`` may come from any thread."""

    def __init__(self, command=None, app_root: Optional[str] = None):
        self.command = list(command) if command else [sys.executable, "-m", "manim"]
        self.app_root = app_root
        self._guard = threading.Lock()
        self._cancelled = False
        self._loop = None
        self._executor = None

    def run(self, job: VideoJob, on_progress: Callable, on_log: Callable) -> str:
        return asyncio.run(self._run(job, on_progress, on_log))

    def cancel(self) -> None:
        with self._guard:
            self._cancelled = True
            loop, executor = self._loop, self._executor
        if loop is not None and executor is not None:
            try:
                asyncio.run_coroutine_threadsafe(executor.cancel(), loop)
            except RuntimeError:
                pass  # the loop already finished

    @staticmethod
    def args(job: VideoJob) -> list:
        extra = ["-r", f"{job.width},{job.height}", "--fps", str(job.fps), "--media_dir", job.media_dir,
                 "--disable_caching"]
        if job.format in ("gif", "webm", "mov"):
            extra += ["--format", job.format]
        if job.transparent:
            extra.append("--transparent")
        return extra

    async def _run(self, job: VideoJob, on_progress, on_log) -> str:
        from executor import ManimExecutor, media_file_is_complete

        executor = ManimExecutor(job.job_dir, render_timeout=job.timeout, app_root=self.app_root)
        with self._guard:
            if self._cancelled:
                raise ExportCancelled()
            self._loop, self._executor = asyncio.get_running_loop(), executor
        ready = {}
        lines = deque(maxlen=60)

        async def events(event):
            if self._cancelled:
                # A cancel that arrived before Manim was spawned: the executor stops it at once.
                await executor.cancel()
            kind = event.get("type")
            if kind == "progress":
                on_progress(event.get("animation"), event.get("percent", 0))
            elif kind == "file_ready":
                ready["path"] = event.get("abs_path")
            elif kind in ("log", "error"):
                message = event.get("message") or ""
                lines.append(message)
                on_log(message)

        try:
            result = await executor.execute(self.command, RUNNER_PATH, SCENE_NAME, "m", False, events,
                                            output_stem=os.path.splitext(os.path.basename(RUNNER_PATH))[0],
                                            extra_args=self.args(job), extra_env={"COMPOSER_JOB": job.job_file})
        finally:
            with self._guard:
                self._loop = self._executor = None
        status = result.get("status")
        if status == "cancelled" or self._cancelled:
            raise ExportCancelled()
        if status == "timeout":
            raise ExportFailed(f"The export took longer than {job.timeout:.0f} s and was stopped.")
        if not result.get("success"):
            raise ExportFailed(self.failure_message(lines, result))
        path = ready.get("path") or find_output(job.media_dir)
        if not path or not media_file_is_complete(path):
            raise ExportFailed("Manim finished, but the video file is missing or incomplete.")
        return path

    @staticmethod
    def failure_message(lines, result: dict) -> str:
        for line in reversed(lines):
            text = line.strip()
            if text and text[0] not in _BOX_CHARS and _ERROR_LINE.search(text):
                return text[:500]
        if result.get("exit_code") is not None:
            return f"Manim exited with code {result['exit_code']}."
        return result.get("error") or "The export failed."


def find_output(media_dir: str) -> Optional[str]:
    """Newest StudioRender.* video (or gif) under *media_dir*, ignoring partial movie files."""
    best = None
    for dirpath, dirnames, filenames in os.walk(media_dir):
        dirnames[:] = [d for d in dirnames if d != "partial_movie_files"]
        for name in filenames:
            stem, ext = os.path.splitext(name)
            if stem == SCENE_NAME and ext.lower() in (".mp4", ".mov", ".webm", ".gif"):
                path = os.path.join(dirpath, name)
                mtime = os.path.getmtime(path)
                if best is None or mtime > best[0]:
                    best = (mtime, path)
    return best[1] if best else None


def public(record: dict) -> dict:
    return {key: value for key, value in record.items() if not key.startswith("_")}


class ExportManager:
    """The export queue. Thread-safe; the service wraps it in async calls.

    *plan(job)* returns the storyboard metadata of a job (``plays``, ``length``) or raises;
    *still(job, width, height, out)* renders a full-size poster; *runner_factory()*
    returns a fresh ``ManimVideoRunner``-like object per video.
    """

    def __init__(self, *, exports_dir: str, work_dir: str, index_path: str, media_root: str,
                 plan: Callable, still: Callable, runner_factory: Callable, base_timeout: Optional[float] = None,
                 max_active: int = 20, max_records: int = 200):
        self.exports_dir = exports_dir
        self.work_dir = work_dir
        self.index_path = index_path
        self.media_root = media_root
        self.plan = plan
        self.still = still
        self.runner_factory = runner_factory
        self.base_timeout = base_timeout
        self.max_active = max_active
        self.max_records = max_records
        self._lock = threading.RLock()
        self._wake = threading.Condition(self._lock)
        self._records: dict = {}
        self._loaded = False
        self._stopping = False
        self._thread: Optional[threading.Thread] = None
        self._current = None  # (export id, runner)

    # -- index -------------------------------------------------------------------
    def _ensure_loaded(self) -> None:
        with self._lock:
            if self._loaded:
                return
            self._loaded = True
            if os.path.isdir(self.work_dir):
                for name in os.listdir(self.work_dir):
                    if _EXPORT_ID.fullmatch(name):
                        shutil.rmtree(os.path.join(self.work_dir, name), ignore_errors=True)
            try:
                with open(self.index_path, encoding="utf-8") as f:
                    data = json.load(f)
            except FileNotFoundError:
                return
            except (OSError, ValueError) as exc:
                logger.warning("studio: ignoring unreadable export index %s (%s)", self.index_path, exc)
                return
            changed = False
            for raw in data.get("exports", []) if isinstance(data, dict) else []:
                if not isinstance(raw, dict) or not _EXPORT_ID.match(str(raw.get("id", ""))):
                    continue
                record = dict(raw)
                if record.get("status") in ACTIVE:
                    record.update(status="failed", progress=None, message=INTERRUPTED, error=INTERRUPTED)
                    changed = True
                if record.get("status") == "done":
                    filename = record.get("filename") or ""
                    if os.path.basename(filename) != filename or not os.path.isfile(
                            os.path.join(self.exports_dir, filename)):
                        changed = True
                        continue  # the file was deleted
                self._records[record["id"]] = record
            if changed:
                self._save_locked()

    def _save_locked(self) -> None:
        records = sorted(self._records.values(), key=lambda r: r.get("created", ""), reverse=True)
        if len(records) > self.max_records:
            for old in records[self.max_records:]:
                if old.get("status") in FINISHED:
                    filename = old.get("filename")
                    if filename and os.path.basename(filename) == filename:
                        path = os.path.realpath(os.path.join(self.exports_dir, filename))
                        root = os.path.realpath(self.exports_dir)
                        try:
                            inside = path != root and os.path.commonpath([root, path]) == root
                        except ValueError:
                            inside = False
                        if inside:
                            try:
                                os.unlink(os.path.join(self.exports_dir, filename))
                            except FileNotFoundError:
                                pass
                            except OSError as exc:
                                logger.warning("studio: could not delete pruned export %s (%s)", filename, exc)
                                continue
                    self._records.pop(old["id"], None)
            records = [r for r in records if r["id"] in self._records]
        data = json.dumps({"version": 1, "exports": [public(r) for r in records]}, indent=1).encode("utf-8")
        try:
            os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
            file_ops.atomic_write(self.index_path, data)
        except OSError as exc:
            logger.warning("studio: could not write the export index (%s)", exc)

    # -- public API ----------------------------------------------------------------
    def start(self, record: dict, job: dict) -> dict:
        """Queue an export. *record* holds the public fields (template, title, format, quality,
        width, height, fps, ...); *job* the render job (template, params, settings, assets_dir)."""
        self._ensure_loaded()
        with self._lock:
            active = sum(1 for r in self._records.values() if r.get("status") in ACTIVE)
            if active >= self.max_active:
                raise BusyError(f"{active} exports are already waiting. Try again when some have finished.")
            export_id = secrets.token_hex(6)
            while export_id in self._records:
                export_id = secrets.token_hex(6)
            entry = {"id": export_id, **record, "status": "queued", "progress": None,
                     "message": "Waiting to start", "created": utc_now(), "_job": dict(job),
                     "_log": deque(maxlen=40)}
            self._records[export_id] = entry
            self._save_locked()
            self._ensure_thread()
            self._wake.notify_all()
            return public(entry)

    def get(self, export_id: str) -> dict:
        self._ensure_loaded()
        with self._lock:
            return public(self._get_locked(export_id))

    def list(self) -> list:
        self._ensure_loaded()
        with self._lock:
            records = sorted(self._records.values(), key=lambda r: r.get("created", ""), reverse=True)
            return [public(r) for r in records]

    def cancel(self, export_id: str) -> dict:
        self._ensure_loaded()
        runner = None
        with self._lock:
            record = self._get_locked(export_id)
            if record["status"] == "queued":
                record.update(status="cancelled", progress=None, message="Cancelled", finished=utc_now())
                self._save_locked()
            elif record["status"] == "rendering":
                record["_cancel"] = True
                record["message"] = "Stopping"
                if self._current and self._current[0] == export_id:
                    runner = self._current[1]
            snapshot = public(record)
        if runner is not None:
            runner.cancel()
        return snapshot

    def remove(self, export_id: str) -> dict:
        """Forget a finished export and delete its file."""
        self._ensure_loaded()
        with self._lock:
            record = self._get_locked(export_id)
            if record["status"] in ACTIVE:
                raise ConflictError("This export is still running; cancel it first.")
            filename = record.get("filename")
            if filename and os.path.basename(filename) == filename:
                try:
                    os.unlink(os.path.join(self.exports_dir, filename))
                except FileNotFoundError:
                    pass
                except OSError as exc:
                    raise StudioError(f"The file could not be deleted ({exc.strerror or exc}).") from exc
            self._records.pop(export_id, None)
            self._save_locked()
            return public(record)

    def shutdown(self, timeout: float = 10.0, on_stopping: Optional[Callable] = None) -> None:
        """Stop the running export and the queue thread. The running one ends as failed
        (interrupted); queued ones stay queued: in this process they run when the queue is
        used again, after a restart they come back as failed (interrupted). *on_stopping*
        runs once the queue is stopping, before waiting for the thread (the service closes
        the preview worker there, so a storyboard in progress ends at once)."""
        with self._lock:
            self._stopping = True
            current, thread = self._current, self._thread
            self._wake.notify_all()
        if current is not None:
            current[1].cancel()
        if on_stopping is not None:
            on_stopping()
        if thread is not None and thread.is_alive():
            thread.join(timeout)
        with self._lock:
            if self._loaded:
                self._save_locked()

    # -- worker thread -------------------------------------------------------------
    def _get_locked(self, export_id: str) -> dict:
        record = self._records.get(export_id) if isinstance(export_id, str) else None
        if record is None:
            raise NotFoundError(f"No export {export_id!r}.")
        return record

    def _ensure_thread(self) -> None:
        thread = self._thread
        if thread is not None and thread.is_alive() and self._stopping:
            self._lock.release()  # let a stopping thread wind down (its job was stopped)
            try:
                thread.join(15)
            finally:
                self._lock.acquire()
            thread = self._thread
        self._stopping = False
        if thread is not None and thread.is_alive():
            self._wake.notify_all()  # still finishing a job: it keeps serving the queue
            return
        self._thread = threading.Thread(target=self._run_forever, name="studio-exports", daemon=True)
        self._thread.start()

    def _next_queued_locked(self) -> Optional[str]:
        queued = [r for r in self._records.values() if r.get("status") == "queued" and "_job" in r]
        if not queued:
            return None
        return min(queued, key=lambda r: r.get("created", ""))["id"]

    def _run_forever(self) -> None:
        while True:
            with self._wake:
                export_id = None
                while not self._stopping:
                    export_id = self._next_queued_locked()
                    if export_id is not None:
                        break
                    self._wake.wait()
                if self._stopping:
                    return
            try:
                self._process(export_id)
            except Exception:  # noqa: BLE001 - keep the queue alive
                logger.exception("studio: export %s crashed the queue", export_id)
                with self._lock:
                    record = self._records.get(export_id)
                    if record is not None and record.get("status") in ACTIVE:
                        record.update(status="failed", progress=None, message="Export failed",
                                      error="Internal error in the export queue.")
                        record.pop("_job", None)

    def _update(self, record: dict, save: bool = False, **fields) -> None:
        with self._lock:
            record.update(fields)
            if save:
                self._save_locked()

    def _check_cancel(self, record: dict) -> None:
        if record.get("_cancel") or self._stopping:
            raise ExportCancelled()

    def _timeout_for(self, record: dict, length: Optional[float]) -> float:
        base = self.base_timeout if self.base_timeout is not None else default_render_timeout()
        seconds = length or (record["_job"].get("settings") or {}).get("length") or 600
        scale = max(1.0, record["width"] * record["height"] / (1920 * 1080)) * max(1.0, record["fps"] / 30)
        return max(base, 120 + 4 * float(seconds) * scale)

    def _publish(self, record: dict, src: str, ext: str) -> str:
        os.makedirs(self.exports_dir, exist_ok=True)
        name = f"{record['_slug']}-{record['id']}{ext.lower()}"
        dest = os.path.join(self.exports_dir, name)
        if os.path.exists(dest):  # ids are unique: never replace another export's file
            raise FileExistsError(f"An export file named {name} already exists.")
        shutil.move(src, dest)
        return dest

    def _process(self, export_id: str) -> None:
        with self._lock:
            record = self._records.get(export_id)
            if record is None or record.get("status") != "queued":
                return
            record.update(status="rendering", progress=0, message="Getting ready", started=utc_now())
            record.setdefault("_slug", record.get("template") or "video")
            self._save_locked()
        job = record["_job"]
        job_dir = os.path.join(self.work_dir, export_id)
        duration = None
        final = None
        try:
            os.makedirs(job_dir, exist_ok=True)
            if record["format"] == "png":
                self._update(record, message="Rendering the image")
                out = os.path.join(job_dir, "poster.png")
                self.still(job, record["width"], record["height"], out)
                self._check_cancel(record)
                final = self._publish(record, out, ".png")
            else:
                try:
                    plan = self.plan(job) or {}
                except Exception as exc:  # noqa: BLE001 - progress is a nicety; the export decides
                    logger.info("studio: no storyboard for export %s (%s)", export_id, exc)
                    plan = {}
                self._check_cancel(record)
                plays = plan.get("plays") or None
                duration = plan.get("length")
                job_file = os.path.join(job_dir, "job.json")
                with open(job_file, "w", encoding="utf-8") as f:
                    json.dump({**job, "mode": "video"}, f)
                runner = self.runner_factory()
                with self._lock:
                    self._current = (export_id, runner)
                    record.update(progress=0 if plays else None, message="Starting Manim")
                self._check_cancel(record)

                def on_progress(animation, percent):
                    with self._lock:
                        if record.get("_cancel"):
                            return
                        if plays and animation is not None:
                            overall = int((animation + max(0, min(100, percent)) / 100) / plays * 100)
                            record["progress"] = max(record.get("progress") or 0, min(99, overall))
                            record["message"] = f"Rendering animation {min(animation + 1, plays)} of {plays}"
                        elif animation is not None:
                            record["message"] = f"Rendering animation {animation + 1}"

                def on_log(line):
                    record["_log"].append(line)

                video = VideoJob(job_dir=job_dir, job_file=job_file, media_dir=os.path.join(job_dir, "media"),
                                 width=record["width"], height=record["height"], fps=record["fps"],
                                 format=record["format"], transparent=bool(record.get("transparent")),
                                 timeout=self._timeout_for(record, duration))
                path = runner.run(video, on_progress, on_log)
                self._check_cancel(record)
                final = self._publish(record, path, os.path.splitext(path)[1] or f".{record['format']}")
            with self._lock:
                self._check_cancel(record)
                rel = os.path.relpath(final, self.media_root).replace("\\", "/")
                self._update(record, save=True, status="done", progress=100, message="Ready",
                             url="/media/" + rel, filename=os.path.basename(final), size=os.path.getsize(final),
                             duration=duration, finished=utc_now())
        except ExportCancelled:
            if final is not None:
                try:
                    os.unlink(final)
                except OSError:
                    pass
            if record.get("_cancel"):
                self._update(record, save=True, status="cancelled", progress=None, message="Cancelled",
                             finished=utc_now())
            else:  # the app is shutting down
                self._update(record, save=True, status="failed", progress=None, message=INTERRUPTED,
                             error=INTERRUPTED, finished=utc_now())
        except Exception as exc:  # noqa: BLE001 - every failure ends up on the record
            message = INTERRUPTED if self._stopping else (str(exc) or type(exc).__name__)
            fields = {"status": "failed", "progress": None, "message": "Export failed", "error": message,
                      "finished": utc_now()}
            if record["_log"]:
                fields["log"] = list(record["_log"])[-20:]
            self._update(record, save=True, **fields)
        finally:
            with self._lock:
                if self._current and self._current[0] == export_id:
                    self._current = None
                record.pop("_job", None)
            shutil.rmtree(job_dir, ignore_errors=True)
