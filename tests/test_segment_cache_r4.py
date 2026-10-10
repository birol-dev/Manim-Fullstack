"""r4: a cancelled render must not poison Manim's partial-movie cache (2PSD InvalidDataError)."""
import asyncio
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import executor as executor_module  # noqa: E402
from executor import ManimExecutor, mp4_is_complete, purge_incomplete_segments  # noqa: E402


def box(kind: bytes, payload: bytes = b"") -> bytes:
    return (8 + len(payload)).to_bytes(4, "big") + kind + payload


COMPLETE = box(b"ftyp", b"isom" * 4) + box(b"mdat", b"\0" * 64) + box(b"moov", b"\0" * 32)
HEADER_ONLY = box(b"ftyp", b"isom" * 4) + box(b"free", b"\0" * 8) + (0).to_bytes(4, "big") + b"mdat"  # 48-byte kind
TRUNCATED = box(b"ftyp", b"isom" * 4) + (1000).to_bytes(4, "big") + b"mdat" + b"\0" * 100


def seg_dir(root, stem="demo", res="480p15", scene="S"):
    d = root / "media" / "videos" / stem / res / "partial_movie_files" / scene
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.mark.parametrize("data, ok", [(COMPLETE, True), (HEADER_ONLY, False), (TRUNCATED, False), (b"", False), (b"\0\0\0", False)])
def test_mp4_is_complete(tmp_path, data, ok):
    p = tmp_path / "x.mp4"
    p.write_bytes(data)
    assert mp4_is_complete(str(p)) is ok


def test_large_size_box_and_missing_file(tmp_path):
    p = tmp_path / "x.mp4"
    big = (1).to_bytes(4, "big") + b"mdat" + (16 + 4).to_bytes(8, "big") + b"abcd"
    p.write_bytes(box(b"ftyp", b"isom") + big + box(b"moov"))
    assert mp4_is_complete(str(p))
    assert not mp4_is_complete(str(tmp_path / "missing.mp4"))


def test_purge_keeps_good_segments_and_final_outputs(tmp_path):
    d = seg_dir(tmp_path)
    (d / "good.mp4").write_bytes(COMPLETE)
    (d / "bad.mp4").write_bytes(HEADER_ONLY)
    (d / "partial_movie_file_list.txt").write_text("x")
    final = d.parent.parent / "S.mp4"
    final.write_bytes(HEADER_ONLY)  # not a cache segment: left alone
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(HEADER_ONLY)
    (d / "link.mp4").symlink_to(outside)
    removed = purge_incomplete_segments(str(tmp_path / "media" / "videos" / "demo"))
    assert [os.path.basename(p) for p in removed] == ["bad.mp4"]
    assert (d / "good.mp4").exists() and final.exists() and outside.exists()


def _proc(stdout=b""):
    class P:
        pid = 4242
        returncode = None

        def __init__(self):
            self.stdout = asyncio.StreamReader()
            self.stderr = asyncio.StreamReader()
            self.stdout.feed_data(stdout)
            self.stdout.feed_eof()
            self.stderr.feed_eof()

        async def wait(self):
            self.returncode = 1
            return 1
    return P()


@pytest.mark.asyncio
async def test_render_drops_a_poisoned_segment_before_manim_starts(tmp_path):
    d = seg_dir(tmp_path)
    (d / "bad.mp4").write_bytes(HEADER_ONLY)
    (d / "good.mp4").write_bytes(COMPLETE)
    seen = {}
    events = []

    async def spawn(*cmd, **kw):
        seen["bad_at_spawn"] = (d / "bad.mp4").exists()
        return _proc()

    async def cb(e):
        events.append(e)

    with patch("asyncio.create_subprocess_exec", side_effect=spawn):
        await ManimExecutor(str(tmp_path)).execute(["manim"], "demo.py", "S", "l", False, cb)
    assert seen["bad_at_spawn"] is False
    assert (d / "good.mp4").exists()
    assert any("unfinished cached segment" in (e.get("message") or "") for e in events)


@pytest.mark.asyncio
async def test_failed_render_cleans_the_segment_it_left(tmp_path):
    d = seg_dir(tmp_path)

    async def spawn(*cmd, **kw):
        (d / "half.mp4").write_bytes(TRUNCATED)  # Manim killed mid-segment
        return _proc()

    async def cb(e):
        pass

    with patch("asyncio.create_subprocess_exec", side_effect=spawn):
        result = await ManimExecutor(str(tmp_path)).execute(["manim"], "demo.py", "S", "l", False, cb)
    assert result["status"] == "failed"
    assert not (d / "half.mp4").exists()


@pytest.mark.asyncio
async def test_no_purge_while_another_render_of_the_stem_is_in_flight(tmp_path, monkeypatch):
    d = seg_dir(tmp_path)
    (d / "writing.mp4").write_bytes(HEADER_ONLY)  # the other render's open segment
    monkeypatch.setitem(executor_module._stems_in_flight, "demo", 1)

    async def spawn(*cmd, **kw):
        return _proc()

    async def cb(e):
        pass

    with patch("asyncio.create_subprocess_exec", side_effect=spawn):
        await ManimExecutor(str(tmp_path)).execute(["manim"], "demo.py", "S", "l", False, cb)
    assert (d / "writing.mp4").exists()
    assert executor_module._stems_in_flight["demo"] == 1
