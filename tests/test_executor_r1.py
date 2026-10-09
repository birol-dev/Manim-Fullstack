"""Executor round-1 fixes: path redaction, stale outputs, dash names, wrapped "File ready"."""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from executor import ManimExecutor


async def _read(executor, data: bytes, stream_name="stderr"):
    """Feed *data* through the executor's stream reader and collect its events."""
    events = []

    async def log_cb(evt):
        events.append(evt)

    stream = asyncio.StreamReader()
    stream.feed_data(data)
    stream.feed_eof()
    await executor._read_stream(stream, stream_name, log_cb)
    return events


# --------------------------------------------------------------------------- #
# Log redaction keeps the user's backslashes
# --------------------------------------------------------------------------- #


def test_redaction_hides_host_paths_but_keeps_backslashes(tmp_path, monkeypatch):
    import tempfile

    home = tmp_path / "home" / "box"
    monkeypatch.setenv("HOME", str(home))
    workspace = home / "proj" / "workspace"
    executor = ManimExecutor(str(workspace))
    import sysconfig

    site = os.path.join(sysconfig.get_paths()["purelib"], "manim", "scene.py")
    line = (
        rf"LaTeX \frac{{a}}{{b}} \t C:\Users\me in {workspace}/demo.py:5, "
        rf"{site}:12, {tempfile.gettempdir()}/Tex/abc.tex, {home}/notes"
    )
    out = executor._redact_paths(line)
    assert r"\frac{a}{b} \t C:\Users\me" in out
    assert " demo.py:5" in out and "/demo.py" not in out  # relative, like #9
    assert "<site-packages>/manim/scene.py:12" in out
    assert "<tmp>/Tex/abc.tex" in out or str(tmp_path) not in out
    assert "~/notes" in out
    assert str(workspace) not in out and str(home) not in out


def test_redaction_matches_whole_paths_only(tmp_path):
    workspace = tmp_path / "ws"
    executor = ManimExecutor(str(workspace))
    # A longer sibling name and a path that merely ends with the workspace stay as they are.
    sibling = f"{workspace}er/file.py"
    nested = f"/srv{workspace}/file.py"
    assert executor._redact_paths(sibling).endswith("/wser/file.py")  # temp dir hidden, workspace not
    assert executor._redact_paths(nested) == nested
    assert executor._redact_paths(f"'{workspace}/a.py'") == "'a.py'"
    assert executor._redact_paths(f"{workspace}") == ""


def test_redaction_skips_root_like_prefixes(monkeypatch):
    import tempfile

    monkeypatch.setattr(tempfile, "gettempdir", lambda: "/")
    monkeypatch.setenv("HOME", "/")
    executor = ManimExecutor("/")
    executor._redaction = None
    line = r"/usr/lib \alpha"
    out = executor._redact_paths(line)
    # "/" as workspace, home, or temp would strip every slash; those rules are skipped,
    # and a system prefix such as /usr is never redacted as a whole.
    assert out == line


def test_redaction_with_nothing_to_hide(monkeypatch):
    executor = ManimExecutor("/w")
    executor._redaction = (None, {})
    assert executor._redact_paths(r"a\b") == r"a\b"


@pytest.mark.asyncio
async def test_logged_lines_keep_latex_backslashes(tmp_path):
    executor = ManimExecutor(str(tmp_path))
    events = await _read(executor, rb"! Undefined control sequence. l.7 \fracc{1}{2}" + b"\n", stream_name="stderr")
    assert events[0]["message"] == r"! Undefined control sequence. l.7 \fracc{1}{2}"


# --------------------------------------------------------------------------- #
# Disk-scan fallback ignores outputs from earlier runs
# --------------------------------------------------------------------------- #


def _fake_process(stdout=b""):
    process = MagicMock()
    process.pid = 2020
    process.returncode = None
    process.stdout = asyncio.StreamReader()
    if stdout:
        process.stdout.feed_data(stdout)
    process.stdout.feed_eof()
    process.stderr = asyncio.StreamReader()
    process.stderr.feed_eof()
    process.wait = AsyncMock(return_value=0)
    return process


@pytest.mark.asyncio
async def test_run_that_writes_nothing_does_not_report_the_previous_video(tmp_path):
    """Like os._exit(0) in construct(): exit code 0, no "File ready", no new file."""
    executor = ManimExecutor(str(tmp_path))
    old = tmp_path / "media" / "videos" / "demo" / "480p15" / "S.mp4"
    old.parent.mkdir(parents=True)
    old.write_text("previous run")
    events = []

    async def log(event):
        events.append(event)

    with patch("asyncio.create_subprocess_exec", return_value=_fake_process()):
        result = await executor.execute("/usr/bin/manim", "demo.py", "S", "l", False, log)

    assert result == {"success": False, "status": "failed", "exit_code": 0}
    assert not any(e["type"] == "file_ready" for e in events)
    assert events[-1]["message"] == "Rendering produced no output."


@pytest.mark.asyncio
async def test_fallback_accepts_an_output_rewritten_by_this_run(tmp_path):
    executor = ManimExecutor(str(tmp_path))
    old = tmp_path / "media" / "videos" / "demo" / "480p15" / "S.mp4"
    other = tmp_path / "media" / "videos" / "demo" / "720p30" / "S.mp4"
    old.parent.mkdir(parents=True)
    other.parent.mkdir(parents=True)
    old.write_text("previous run")
    other.write_text("untouched")
    os.utime(other, (10, 10))
    events = []

    async def log(event):
        events.append(event)

    async def spawn(*args, **kwargs):
        old.write_text("this run, longer content")
        return _fake_process()

    with patch("asyncio.create_subprocess_exec", side_effect=spawn):
        result = await executor.execute("/usr/bin/manim", "demo.py", "S", "l", False, log)

    assert result["success"] is True
    ready = [e for e in events if e["type"] == "file_ready"]
    assert [e["abs_path"] for e in ready] == [str(old)]


def test_output_snapshot_and_previous_filter(tmp_path):
    executor = ManimExecutor(str(tmp_path))
    video = tmp_path / "media" / "videos" / "demo" / "480p15" / "S.mp4"
    video.parent.mkdir(parents=True)
    video.write_text("v")
    snapshot = executor._output_snapshot("demo.py", "S")
    assert list(snapshot) == [str(video)]
    assert executor._find_latest_render("demo.py", "S", snapshot) is None
    assert executor._find_latest_render("demo.py", "S") == str(video)
    assert ManimExecutor._newest_matching_file(str(video.parent), "S", (".mp4",)) == str(video)
    assert ManimExecutor._newest_matching_file(str(tmp_path / "nope"), "S", (".mp4",)) is None


def test_matching_files_skips_files_that_vanish(tmp_path):
    root = tmp_path / "videos" / "demo"
    root.mkdir(parents=True)
    (root / "S.mp4").write_text("v")
    with patch("os.stat", side_effect=OSError("gone")):
        assert ManimExecutor._matching_files(str(root), "S", (".mp4",)) == []
    with patch("os.walk", side_effect=OSError("unreadable")):
        assert ManimExecutor._matching_files(str(root), "S", (".mp4",)) == []


# --------------------------------------------------------------------------- #
# Script names that look like options
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name", ["-ql.py", "--help.py", "-.py"])
def test_dash_script_names_are_passed_as_paths(name):
    args = ManimExecutor.build_args(name, "S", "l", False)
    assert args[0] == f"./{name}"
    assert args[1:] == ["S", "-ql", "--progress_bar=display"]


@pytest.mark.asyncio
async def test_dash_script_name_reaches_manim_as_a_path(tmp_path):
    executor = ManimExecutor(str(tmp_path))
    spawned = {}

    async def spawn(*cmd, **kwargs):
        spawned["cmd"] = cmd
        return _fake_process(b"File ready at '/x/media/videos/-ql/480p15/S.mp4'\n")

    with patch("asyncio.create_subprocess_exec", side_effect=spawn):
        result = await executor.execute(["py", "-m", "manim"], "-ql.py", "S", "l", False, AsyncMock())
    assert spawned["cmd"][:5] == ("py", "-m", "manim", "./-ql.py", "S")
    assert result["success"] is True


# --------------------------------------------------------------------------- #
# Wrapped "File ready at" lines (TERM=dumb or narrow terminals)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_wrapped_file_ready_path_is_rejoined(tmp_path):
    executor = ManimExecutor(str(tmp_path))
    data = (
        "INFO     File ready at \n"
        "'/w/media/videos/demo/480p15/\n"
        "Intro.mp4'\n"
    ).encode()
    events = await _read(executor, data, stream_name="stdout")
    ready = [e for e in events if e["type"] == "file_ready"]
    assert len(ready) == 1 and ready[0]["rel_path"] == "media/videos/demo/480p15/Intro.mp4"


@pytest.mark.asyncio
async def test_wrapped_file_ready_split_mid_word_is_rejoined(tmp_path):
    executor = ManimExecutor(str(tmp_path))
    data = b"File ready at '/w/media/videos/demo/480p15/Int\nro.mp4'\n"
    events = await _read(executor, data, stream_name="stdout")
    ready = [e for e in events if e["type"] == "file_ready"]
    assert ready and ready[0]["filename"] == "Intro.mp4"


def test_keep_box_width_only_pads_boxed_lines():
    from executor import keep_box_width

    assert keep_box_width("│ long/path.py │", "│ p.py │") == "│ p.py " + " " * 8 + "│"
    assert keep_box_width("plain long line", "plain") == "plain"
    assert keep_box_width("│ a │", "│ a │") == "│ a │"
