"""Fakes for the studio service tests: a preview worker and an export runner without Manim."""

import json
import os
import struct
import threading
import time
import zlib

from studio.exports import ExportCancelled, ExportFailed
from studio.service import StudioService
from tests.media_bytes import MP4

STORYBOARD = {"frames": 3, "plays": 4, "columns": 3, "times": [0.5, 1.5, 6.0], "frame_size": [64, 36],
              "length": 6.0}


def tiny_png(width: int, height: int) -> bytes:
    """A real (black) RGB PNG of this size."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\x00\x00\x00" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class FakeWorker:
    """Writes the PNG (and storyboard JSON) a real worker would; records every job."""

    def __init__(self):
        self.calls = []
        self.fail = None  # an exception to raise instead of rendering
        self.stops = 0
        self.alive = False
        self.delay = 0.0

    def render(self, job, width, height, media_dir=None, timeout=None):
        self.calls.append({"job": job, "width": width, "height": height, "timeout": timeout})
        if self.delay:
            time.sleep(self.delay)
        if self.fail is not None:
            raise self.fail
        out = job["output"]
        os.makedirs(os.path.dirname(out), exist_ok=True)
        if job["mode"] == "storyboard":
            with open(os.path.splitext(out)[0] + ".json", "w", encoding="utf-8") as f:
                json.dump(STORYBOARD, f)
            data = tiny_png(200, 90)
        else:
            data = tiny_png(width, height)
        with open(out, "wb") as f:
            f.write(data)
        return {"id": len(self.calls), "ok": True, "ms": 1, "output": out}

    def start(self):
        self.alive = True
        return {"event": "ready"}

    def stop(self, timeout=3.0):
        self.stops += 1
        self.alive = False

    def close(self):
        self.stop()


class FakeRunner:
    """Stands in for ManimVideoRunner. ``behavior``: ok, fail, block (until cancelled), or a gif."""

    def __init__(self, behavior="ok", ext=".mp4"):
        self.behavior = behavior
        self.ext = ext
        self.job = None
        self.started = threading.Event()
        self.cancelled = threading.Event()
        self.release = threading.Event()

    def run(self, job, on_progress, on_log):
        self.job = job
        on_progress(0, 100)
        on_progress(1, 50)
        self.started.set()
        if self.behavior == "block":
            deadline = time.monotonic() + 20
            while not self.release.is_set():
                if self.cancelled.is_set():
                    raise ExportCancelled()
                if time.monotonic() > deadline:
                    raise ExportFailed("fake runner was never released")
                time.sleep(0.01)
        if self.behavior == "fail":
            on_log("ValueError: the fake template broke")
            raise ExportFailed("ValueError: the fake template broke")
        on_progress(3, 100)
        out = os.path.join(job.media_dir, "videos", "runner", "480p15", "StudioRender" + self.ext)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as f:
            f.write(MP4)
        return out

    def cancel(self):
        self.cancelled.set()


class RunnerFactory:
    """Hands out runners in order (the last one repeats); keeps them for assertions."""

    def __init__(self, *runners):
        self.queue = list(runners) or [FakeRunner()]
        self.made = []

    def __call__(self):
        runner = self.queue.pop(0) if len(self.queue) > 1 else self.queue[0]
        self.made.append(runner)
        return runner


def make_service(tmp_path, worker=None, runners=None, **options):
    worker = worker or FakeWorker()
    icons = tmp_path / "icons"
    icons.mkdir(exist_ok=True)
    svc = StudioService(str(tmp_path / "ws"), worker_factory=lambda: worker,
                        runner_factory=runners or RunnerFactory(), icons_dir=str(icons), **options)
    return svc, worker


def wait_until(predicate, timeout=10.0, interval=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    raise AssertionError("condition not met in time")
