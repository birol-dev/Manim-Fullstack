"""Frame telemetry through the real executor's stream parser and export queue."""
import asyncio
import json
import runpy
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from studio import exports
from studio.exports import ExportManager, ManimVideoRunner, VideoJob
from tests.media_bytes import valid_bytes
from tests.studio_fakes import wait_until


def test_frame_estimate_waits_for_measured_throughput(monkeypatch):
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(exports, "time", SimpleNamespace(monotonic=lambda: clock.now))
    estimate = exports.FrameEstimate()
    for frame in (0, 10, 20, 30):
        assert estimate.update(frame, 1000, 15) is None
        clock.now += 1
    assert estimate.update(40, 1000, 15) == "About 2 min left"
    clock.now += 1
    assert estimate.update(50, 100, 15) == "Less than a minute left"
    assert estimate.update(50, 100, 15) is None
    assert estimate.update(100, 100, 15) is None


@pytest.mark.parametrize("fmt", ["mp4", "gif", "webm", "mov"])
def test_streamed_frames_reach_record_monotonically(tmp_path, monkeypatch, fmt):
    """No Manim/ffmpeg process needed: realistic bars and split JSON share a pipe.

    Feed the executor's actual chunk/CR parser, not pre-parsed callback events.
    Frame counts deliberately regress once, and a late draw follows finishing.
    """
    from executor import ManimExecutor

    snapshots = []
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(exports, "time", SimpleNamespace(monotonic=lambda: clock.now))

    async def execute(self, command, script, scene, quality, opengl, callback, **kwargs):
        chunks = []
        for frames, phase in [(0, "drawing"), (20, "drawing"), (40, "drawing"),
                              (30, "drawing"), (60, "drawing"), (80, "drawing"),
                              (100, "drawing"), (100, "finishing"), (90, "drawing")]:
            payload = {"phase": phase, "rendered_frames": frames, "total_frames": 100}
            line = (f"Waiting 1: {frames}%|###| {frames}/100 [00:02<00:03]\r"
                    + exports.PROGRESS_PREFIX + json.dumps(payload) + "\n").encode()
            # Arbitrarily split every protocol record across reads.
            chunks.extend([line[:31], line[31:]])

        class ChunkStream:
            def __init__(self):
                self.chunks = iter(chunks)

            async def read(self, size):
                return next(self.chunks, b"")

        async def observe(event):
            clock.now += 1
            await callback(event)
            snapshots.append(manager.list()[0])

        await self._read_stream(ChunkStream(), "stdout", observe)
        out = Path(kwargs["extra_args"][kwargs["extra_args"].index("--media_dir") + 1]) / ("StudioRender." + fmt)
        out.parent.mkdir(parents=True, exist_ok=True)
        # The executor validates files; use a minimal complete media fixture.
        out.write_bytes(valid_bytes(out))
        await callback({"type": "file_ready", "abs_path": str(out)})
        return {"success": True, "status": "success"}

    monkeypatch.setattr(ManimExecutor, "execute", execute)
    manager = ExportManager(exports_dir=str(tmp_path / "exports"), work_dir=str(tmp_path / "work"),
                            index_path=str(tmp_path / "index.json"), media_root=str(tmp_path),
                            plan=lambda job: {"length": 5}, still=None, runner_factory=ManimVideoRunner)
    try:
        record = manager.start({"template": "countdown", "format": fmt, "fps": 20,
                                "width": 640, "height": 360}, {"template": "countdown"})
        done = wait_until(lambda: (r if (r := manager.get(record["id"]))["status"] in exports.FINISHED else None))
        assert done["status"] == "done", done
        active = [s for s in snapshots if s["status"] == "rendering" and "total_frames" in s]
        values = [s["progress"] for s in active]
        assert values == sorted(values)
        assert {19, 38, 57, 76, 95} <= set(values)
        assert all(v < 100 for v in values)
        assert any(s["time_left"] == "Less than a minute left" for s in active)
        assert any(s["message"] == exports.DRAWING for s in active)
        assert active[-1]["phase"] == "finishing" and active[-1]["message"] == exports.FINISHING
        assert active[-1]["time_left"] is None
        assert done["progress"] == 100 and done["message"] == "Ready" and done["time_left"] is None
        assert done["duration"] == 5
        assert (tmp_path / "exports" / done["filename"]).is_file()
        assert manager.list()[0] == done
    finally:
        manager.shutdown()


def test_protocol_cancellation_and_failure(tmp_path, monkeypatch):
    from executor import ManimExecutor

    started, cancelled = threading.Event(), threading.Event()

    async def cancel(self):
        cancelled.set()

    async def execute(self, command, script, scene, quality, opengl, callback, **kwargs):
        await callback({"type": "log", "message": exports.PROGRESS_PREFIX + json.dumps(
            {"phase": "drawing", "rendered_frames": 10, "total_frames": 100})})
        started.set()
        while not cancelled.is_set():
            await asyncio.sleep(0.01)
        return {"success": False, "status": "cancelled"}

    monkeypatch.setattr(ManimExecutor, "execute", execute)
    monkeypatch.setattr(ManimExecutor, "cancel", cancel)
    runner = ManimVideoRunner()
    job = VideoJob(str(tmp_path), "job.json", str(tmp_path / "media"), 640, 360, 15, "mp4", False, 10)
    result = []

    def render():
        try:
            runner.run(job, lambda *args: None, lambda line: None)
        except Exception as exc:
            result.append(exc)

    thread = threading.Thread(target=render)
    thread.start()
    assert started.wait(5)
    before = time.monotonic()
    runner.cancel()
    thread.join(2)
    assert not thread.is_alive() and time.monotonic() - before < 2
    assert isinstance(result[0], exports.ExportCancelled)

    async def fail(self, command, script, scene, quality, opengl, callback, **kwargs):
        await callback({"type": "log", "message": exports.PROGRESS_PREFIX + "invalid JSON"})
        await callback({"type": "error", "message": "ValueError: frame failed"})
        return {"success": False, "status": "error", "exit_code": 1}

    monkeypatch.setattr(ManimExecutor, "execute", fail)
    with pytest.raises(exports.ExportFailed, match="ValueError: frame failed"):
        ManimVideoRunner().run(job, lambda *args: None, lambda line: None)


def test_png_finishes_before_becoming_ready(tmp_path):
    drawing, finish_draw, finishing, publish = [threading.Event() for _ in range(4)]

    def still(job, width, height, out):
        drawing.set()
        assert finish_draw.wait(5)
        Path(out).write_bytes(valid_bytes(out))

    manager = ExportManager(exports_dir=str(tmp_path / "exports"), work_dir=str(tmp_path / "work"),
                            index_path=str(tmp_path / "index.json"), media_root=str(tmp_path),
                            plan=None, still=still, runner_factory=None)
    original_publish = manager._publish

    def hold_publish(*args):
        finishing.set()
        assert publish.wait(5)
        return original_publish(*args)

    manager._publish = hold_publish
    try:
        job = manager.start({"template": "countdown", "format": "png", "fps": 15,
                             "width": 640, "height": 360}, {})
        assert drawing.wait(5)
        record = manager.get(job["id"])
        assert record["progress"] == 0 and record["message"] == exports.DRAWING
        assert record["total_frames"] == 1 and record["time_left"] is None
        finish_draw.set()
        assert finishing.wait(5)
        record = manager.get(job["id"])
        assert record["status"] == "rendering" and record["progress"] == 95
        assert record["message"] == exports.FINISHING and "url" not in record
        publish.set()
        done = wait_until(lambda: (r if (r := manager.get(job["id"]))["status"] == "done" else None))
        assert done["progress"] == 100 and done["message"] == "Ready"
    finally:
        finish_draw.set()
        publish.set()
        manager.shutdown()


@pytest.fixture
def runner_module(tmp_path):
    manim = pytest.importorskip("manim")
    from studio.kit import runtime

    with manim.tempconfig({"pixel_width": 160, "pixel_height": 90, "frame_rate": 15,
                           "media_dir": str(tmp_path), "progress_bar": "none", "verbosity": "ERROR",
                           "disable_caching": True}):
        runtime.set_job({"template": "countdown", "params": {"seconds": 3}, "mode": "video"})
        try:
            module = runpy.run_path(exports.RUNNER_PATH)
        finally:
            runtime.set_job(None)
    return module


def test_batched_wait_counts_encoded_frames_not_queued_frames(runner_module, monkeypatch):
    clock = SimpleNamespace(now=100.0)
    progress_class = runner_module["FrameProgress"]
    monkeypatch.setitem(progress_class.completed.__globals__, "time", SimpleNamespace(monotonic=lambda: clock.now))

    class AsyncWriter:
        def __init__(self):
            self.queued, self.encoded, self.finished = [], [], False

        def write_frame(self, frame, num_frames=1):
            self.queued.append((frame, num_frames))

        def encode_and_write_frame(self, frame, num_frames):
            clock.now += 0.21
            self.encoded.append(num_frames)

        def finish(self):
            self.finished = True

    writer = AsyncWriter()
    events = []
    progress = progress_class(writer, 12, events.append)
    writer.write_frame("frozen pixels", num_frames=12)
    assert progress.frames == 0 and len(events) == 1
    writer.encode_and_write_frame(*writer.queued[0])
    assert writer.encoded == [1] * 12
    assert [e["rendered_frames"] for e in events] == list(range(13))
    assert events[-1]["phase"] == "finishing" and not writer.finished
    writer.finish()
    assert writer.finished


@pytest.mark.parametrize("fps, expected", [(15, 60), (30, 120), (60, 240)])
@pytest.mark.parametrize("padding", [False, True])
def test_real_frame_count_includes_animated_and_frozen_waits(tmp_path, runner_module, fps, expected, padding):
    """Small in-process real render also verifies the timing pass draws no frames."""
    import manim

    with manim.tempconfig({"pixel_width": 160, "pixel_height": 90, "frame_rate": fps,
                           "media_dir": str(tmp_path), "progress_bar": "none", "verbosity": "ERROR",
                           "disable_caching": True}):

        class MultiSecond(manim.Scene):
            def construct(self):
                square = manim.Square()
                self.play(manim.Create(square), run_time=1.1)
                self.wait(2.3)
                self.play(square.animate.shift(manim.RIGHT), run_time=0.6)
                if padding:
                    self.wait(6 - self.renderer.time)

        total = runner_module["measure_scene"](MultiSecond)
        if not padding:
            assert total == expected
        assert not list(tmp_path.rglob("*.mp4"))  # timing made no movie or poster
        scene = MultiSecond()
        events = []
        progress = runner_module["FrameProgress"](scene.renderer.file_writer, total, events.append)
        # Make every frame observable even on a fast machine.
        original = progress.write_frame

        def write(frame, *args, **kwargs):
            original(frame, *args, **kwargs)
            progress.last_sent = 0

        progress.write_frame = write
        scene.render()
        assert progress.frames == total
        assert [e["rendered_frames"] for e in events] == sorted(e["rendered_frames"] for e in events)
        assert any(0 < e["rendered_frames"] < total for e in events)
        assert events[-1] == {"phase": "finishing", "rendered_frames": total, "total_frames": total}

