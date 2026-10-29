"""Studio previews and an export with a real Manim install (skipped without Manim, as in CI)."""

import asyncio
import importlib.util
import json
import shutil
import subprocess
import time

import pytest

from executor import media_file_is_complete
from studio.service import StudioService
from studio.storage import png_size

pytestmark = pytest.mark.skipif(importlib.util.find_spec("manim") is None, reason="Manim CE is not installed")

SHORT = {"seconds": 3, "title": "", "style": "big", "finish_text": "Go!", "confetti": False}


def run(coro):
    return asyncio.run(coro)


def test_real_motion_is_capped_silent_and_playable(tmp_path):
    svc = StudioService(str(tmp_path / "motion"))
    try:
        for params, aspect in [({"seconds": 300, "confetti": False}, "16:9"), (SHORT, "9:16")]:
            job = run(svc.start_motion("editor", "countdown", params, {"aspect": aspect, "sound": {"effects": False}}))
            deadline = time.monotonic() + 150
            while time.monotonic() < deadline:
                result = run(svc.get_motion(job["id"]))
                if result["status"] in ("done", "failed"):
                    break
                time.sleep(0.1)
            assert result["status"] == "done", result
            assert result["duration"] <= 20.1
            assert result["truncated"] == (params["seconds"] == 300)
            path = tmp_path / "motion" / "media" / "studio" / "previews" / result["url"].rsplit("/", 1)[-1]
            assert media_file_is_complete(str(path))
            if shutil.which("ffprobe"):
                probe = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)],
                                       capture_output=True, text=True, timeout=30, check=True)
                streams = json.loads(probe.stdout)["streams"]
                assert len(streams) == 1 and streams[0]["codec_type"] == "video"
                assert streams[0]["r_frame_rate"] == "15/1"
                assert max(streams[0]["width"], streams[0]["height"]) == 720
                assert float(streams[0]["duration"]) <= 20.1
    finally:
        svc.shutdown_sync()


def test_real_previews_and_export(tmp_path):
    svc = StudioService(str(tmp_path / "ws"))
    # Other work may be adding bundled fonts or icons meanwhile; keep cache keys still.
    svc._kit_fingerprint = svc._icons_fingerprint = lambda: "frozen"
    try:
        started = time.perf_counter()
        poster = run(svc.preview("countdown", SHORT, {"aspect": "16:9", "theme": "pop"}))
        assert poster["cached"] is False and png_size(poster["path"]) == (640, 360)
        again = run(svc.preview("countdown", SHORT, {"aspect": "16:9", "theme": "pop"}))
        assert again["cached"] is True and again["path"] == poster["path"]
        warm = run(svc.preview("countdown", {**SHORT, "finish_text": "Now"}, {"aspect": "1:1", "theme": "pop"}))
        assert warm["cached"] is False and warm["ms"] < 10_000
        print(f"cold poster {poster['ms']} ms (with worker start), warm poster {warm['ms']} ms")

        board = run(svc.preview("countdown", SHORT, {"aspect": "9:16", "theme": "pop"}, mode="storyboard"))
        assert board["storyboard"]["plays"] >= 4 and board["storyboard"]["length"] > 3
        print(f"storyboard {board['ms']} ms")
        export_started = time.perf_counter()

        export = run(svc.start_export("countdown", SHORT, {"aspect": "16:9", "theme": "pop"},
                                      format="mp4", quality="draft", title="Real render"))
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            export = run(svc.get_export(export["id"]))
            if export["status"] in ("done", "failed", "cancelled"):
                break
            time.sleep(0.25)
        assert export["status"] == "done", export
        print(f"draft export {time.perf_counter() - export_started:.1f} s; total {time.perf_counter() - started:.1f} s")
        path = tmp_path / "ws" / "media" / "studio" / "exports" / export["filename"]
        assert export["filename"].startswith("real-render-") and media_file_is_complete(str(path))
        if shutil.which("ffprobe"):
            probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height,r_frame_rate",
                                    "-of", "json", str(path)], capture_output=True, text=True, timeout=30)
            stream = json.loads(probe.stdout)["streams"][0]
            assert (stream["width"], stream["height"], stream["r_frame_rate"]) == (854, 480, "15/1")
    finally:
        svc.shutdown_sync()
