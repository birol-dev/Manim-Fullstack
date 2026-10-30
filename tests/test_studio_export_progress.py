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


def test_find_output_accepts_the_versioned_gif_name(tmp_path):
    """Manim 0.22 suffixes a default-named GIF with its version."""
    videos = tmp_path / "videos" / "runner" / "854x480 15fps"
    segments = videos / "partial_movie_files" / "StudioRender"
    segments.mkdir(parents=True)
    (segments / "StudioRender_1.mp4").write_bytes(b"segment")
    (videos / "Unrelated.gif").write_bytes(b"GIF89a")
    gif = videos / "StudioRender_ManimCE_v0.22.1.gif"
    gif.write_bytes(b"GIF89a")
    assert exports.find_output(str(tmp_path)) == str(gif)


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


def _export_manager(tmp_path, **kwargs):
    options = {"exports_dir": str(tmp_path / "exports"), "work_dir": str(tmp_path / "work"),
               "index_path": str(tmp_path / "index.json"), "media_root": str(tmp_path),
               "plan": None, "still": None, "runner_factory": None}
    return ExportManager(**{**options, **kwargs})


def test_history_trimming_never_drops_a_finished_file(tmp_path):
    manager = _export_manager(tmp_path, max_records=0)
    manager._ensure_loaded()
    exports = tmp_path / "exports"
    exports.mkdir()
    (exports / "kept.mp4").write_bytes(b"video")
    with manager._lock:
        manager._records = {"aaaaaaaaaaaa": {"id": "aaaaaaaaaaaa", "status": "done", "created": "1",
                                             "filename": "kept.mp4"}}
        manager._save_locked()
    assert [record["id"] for record in manager.list()] == ["aaaaaaaaaaaa"]
    assert (exports / "kept.mp4").read_bytes() == b"video"


def test_history_trimming_drops_only_old_prunable_records(tmp_path):
    manager = _export_manager(tmp_path, max_records=2)
    manager._ensure_loaded()
    exports = tmp_path / "exports"
    exports.mkdir()
    (exports / "kept.mp4").write_bytes(b"video")
    with manager._lock:
        manager._records = {
            "aaaaaaaaaaaa": {"id": "aaaaaaaaaaaa", "status": "done", "created": "5", "filename": "kept.mp4"},
            "bbbbbbbbbbbb": {"id": "bbbbbbbbbbbb", "status": "failed", "created": "4"},
            "cccccccccccc": {"id": "cccccccccccc", "status": "cancelled", "created": "3"},
            "dddddddddddd": {"id": "dddddddddddd", "status": "failed", "created": "2"},
            "eeeeeeeeeeee": {"id": "eeeeeeeeeeee", "status": "done", "created": "1", "filename": "gone.mp4"},
        }
        manager._save_locked()
    # Newest first: the finished file stays, and only two prunable records fit the cap.
    assert [record["id"] for record in manager.list()] == ["aaaaaaaaaaaa", "bbbbbbbbbbbb", "cccccccccccc"]
    assert (exports / "kept.mp4").read_bytes() == b"video"


def test_history_trimming_keeps_active_exports(tmp_path):
    manager = _export_manager(tmp_path, max_records=2)
    manager._ensure_loaded()
    with manager._lock:
        manager._records = {
            "aaaaaaaaaaaa": {"id": "aaaaaaaaaaaa", "status": "rendering", "created": "1"},
            "bbbbbbbbbbbb": {"id": "bbbbbbbbbbbb", "status": "queued", "created": "2"},
            "cccccccccccc": {"id": "cccccccccccc", "status": "failed", "created": "3"},
            "dddddddddddd": {"id": "dddddddddddd", "status": "cancelled", "created": "4"},
            "eeeeeeeeeeee": {"id": "eeeeeeeeeeee", "status": "failed", "created": "5"},
            "ffffffffffff": {"id": "ffffffffffff", "status": "failed", "created": "6"},
        }
        manager._save_locked()
    # The two newest prunable records fill the cap; the running and waiting exports stay
    # even though older history pushes them past it.
    assert {record["id"] for record in manager.list()} == {
        "aaaaaaaaaaaa", "bbbbbbbbbbbb", "eeeeeeeeeeee", "ffffffffffff",
    }


def test_export_request_is_saved_and_survives_a_reload(tmp_path):
    def still(job, width, height, out):
        Path(out).write_bytes(b"poster")

    first = _export_manager(tmp_path, still=still)
    try:
        record = first.start({"template": "countdown", "title": "Timer", "format": "png", "quality": "720p",
                              "width": 360, "height": 640, "fps": 15},
                             {"template": "countdown", "params": {"seconds": 7},
                              "settings": {"theme": "dark"}, "assets_dir": str(tmp_path)})
        expected = {"template": "countdown", "params": {"seconds": 7}, "settings": {"theme": "dark"},
                    "format": "png", "quality": "720p", "title": "Timer"}
        assert record["request"] == expected
        done = wait_until(lambda: (r if (r := first.get(record["id"]))["status"] == "done" else None))
        assert done["request"] == expected
    finally:
        first.shutdown()

    again = _export_manager(tmp_path, still=still)
    try:
        assert again.get(record["id"])["request"] == expected
    finally:
        again.shutdown()


def test_a_saved_request_rebuilds_its_job_or_says_why_not():
    assert exports.job_from_request({"request": {"template": "countdown", "params": {"seconds": 3},
                                                 "settings": {"theme": "pop"}}}) == {
        "template": "countdown", "params": {"seconds": 3}, "settings": {"theme": "pop"}}
    assert exports.job_from_request({"request": {"template": "countdown"}}) == {
        "template": "countdown", "params": {}, "settings": {}}
    for record in ({}, {"request": None}, {"request": {}},
                   {"request": {"template": "countdown", "params": []}},
                   {"request": {"template": "countdown", "settings": "dark"}}):
        with pytest.raises(ValueError):
            exports.job_from_request(record)


def test_shutdown_hands_the_export_back_before_waiting(tmp_path):
    """A stop that is killed mid-wait still leaves a complete index to resume from."""
    started, release = threading.Event(), threading.Event()

    class StuckRunner:
        def run(self, job, on_progress, on_log):
            started.set()
            release.wait(5)
            raise exports.ExportCancelled()

        def cancel(self):
            pass  # still winding down; the index must not depend on this

    manager = _export_manager(tmp_path, runner_factory=StuckRunner)
    manager.start({"template": "countdown", "format": "mp4", "fps": 15, "width": 640, "height": 360},
                  {"template": "countdown", "params": {}, "settings": {}})
    assert started.wait(5)
    began = time.monotonic()
    manager.shutdown(timeout=0.1)
    assert time.monotonic() - began < 5
    saved = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))["exports"]
    assert saved[0]["status"] == "queued" and saved[0]["resume"] is True
    assert saved[0]["progress"] is None and saved[0]["message"] == exports.RESUMING
    assert not any(key.startswith("_") for key in saved[0])
    release.set()
    manager._thread.join(5)


def test_records_without_a_request_still_load(tmp_path):
    index = tmp_path / "index.json"
    index.write_text(json.dumps({"version": 1, "exports": [
        {"id": "abcdef000001", "status": "failed", "created": "1", "message": "Export failed"},
    ]}), encoding="utf-8")
    manager = _export_manager(tmp_path)
    try:
        record = manager.get("abcdef000001")
        assert record["status"] == "failed" and "request" not in record
    finally:
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


def test_segment_encoders_count_repeat_only_after_encoding(runner_module):
    """0.22 uses concurrent per-segment encoders, not writer.write_frame."""
    class Encoder:
        def __init__(self):
            self.written = []

        def write_frame(self, frame, *, repeat=1):
            if frame == "bad":
                raise ValueError("encoding failed")
            self.written.append(repeat)

    class Writer:
        def _create_segment_encoder(self, target):
            return Encoder()

        def finish(self):
            pass

    writer = Writer()
    events = []
    progress = runner_module["FrameProgress"](writer, 30, events.append)
    first = writer._create_segment_encoder("first.webm")
    second = writer._create_segment_encoder("second.webm")
    assert progress.frames == 0  # creating/queueing a segment is not encoding it
    progress.last_sent = 0
    threads = [threading.Thread(target=encoder.write_frame, args=("pixels",), kwargs={"repeat": 15})
               for encoder in (first, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert first.written == second.written == [1] * 15
    assert progress.frames == 30
    assert [e["rendered_frames"] for e in events] == sorted(e["rendered_frames"] for e in events)
    assert events[-1] == {"phase": "finishing", "rendered_frames": 30, "total_frames": 30}
    with pytest.raises(ValueError, match="encoding failed"):
        first.write_frame("bad", repeat=8)
    assert progress.frames == 30


def test_finishing_waits_for_outstanding_segment_frames(runner_module):
    class Writer:
        def write_frame(self, frame):
            pass

        def finish(self):
            assert events[-1]["phase"] == "drawing"
            self.write_frame("last frame")

    writer = Writer()
    events = []
    progress = runner_module["FrameProgress"](writer, 1, events.append)
    writer.finish()
    assert progress.frames == 1
    assert events[-1] == {"phase": "finishing", "rendered_frames": 1, "total_frames": 1}


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

