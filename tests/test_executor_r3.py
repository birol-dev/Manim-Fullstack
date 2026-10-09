"""Executor round 3: trusted "File ready at", redaction gaps, wrapped boxes, long lines, box widths."""

import asyncio
import os
import time
from unittest.mock import MagicMock, patch

import pytest

import executor as executor_module
from executor import ManimExecutor, cell_len, keep_box_width, redact_host_paths


async def _read(executor, data: bytes, stream_name="stderr"):
    events = []

    async def log_cb(evt):
        events.append(evt)

    stream = asyncio.StreamReader()
    stream.feed_data(data)
    stream.feed_eof()
    await executor._read_stream(stream, stream_name, log_cb)
    return events


def _logs(events):
    return [e["message"] for e in events if e["type"] == "log"]


def _fake_process(stdout: bytes):
    process = MagicMock()
    process.returncode = None
    out, err = asyncio.StreamReader(), asyncio.StreamReader()
    out.feed_data(stdout)
    out.feed_eof()
    err.feed_eof()
    process.stdout, process.stderr = out, err

    async def wait():
        process.returncode = 0
        return 0

    process.wait = wait
    return process


async def _run(executor, stdout_for, script="demo.py", scene="S", **kw):
    events = []

    async def cb(evt):
        events.append(evt)

    async def spawn(*cmd, **kwargs):
        return _fake_process(stdout_for(cmd))

    with patch("asyncio.create_subprocess_exec", side_effect=spawn):
        result = await executor.execute(["manim"], script, scene, "l", False, cb, **kw)
    return result, events


# --------------------------------------------------------------------------- #
# "File ready at" spoofing
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_spoofed_file_ready_for_an_old_video_is_ignored(tmp_path):
    """r2 (Fixer): user code printed "File ready at <old video>" and the render 'succeeded'."""
    old = tmp_path / "media" / "videos" / "demo" / "480p15" / "S.mp4"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"old")
    os.utime(old, (time.time() - 3600, time.time() - 3600))
    result, events = await _run(ManimExecutor(str(tmp_path)), lambda cmd: f"File ready at '{old}'\n".encode())
    assert result["status"] == "failed"
    assert not [e for e in events if e["type"] == "file_ready"]


@pytest.mark.asyncio
async def test_file_ready_outside_this_scripts_media_folder_is_ignored(tmp_path):
    other = tmp_path / "media" / "videos" / "other" / "480p15" / "S.mp4"

    def out(cmd):
        other.parent.mkdir(parents=True, exist_ok=True)
        other.write_bytes(b"fresh but someone else's")
        return f"File ready at '{other}'\n".encode()

    result, events = await _run(ManimExecutor(str(tmp_path)), out)
    assert result["status"] == "failed" and not [e for e in events if e["type"] == "file_ready"]


@pytest.mark.asyncio
async def test_file_ready_through_a_symlink_out_of_the_folder_is_ignored(tmp_path):
    outside = tmp_path / "outside.mp4"
    link_dir = tmp_path / "media" / "videos" / "demo"
    link_dir.mkdir(parents=True)

    def out(cmd):
        outside.write_bytes(b"x")
        (link_dir / "S.mp4").symlink_to(outside)
        return f"File ready at '{link_dir / 'S.mp4'}'\n".encode()

    result, _ = await _run(ManimExecutor(str(tmp_path)), out)
    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_real_output_written_during_the_run_is_announced(tmp_path):
    fresh = tmp_path / "media" / "videos" / "demo" / "480p15" / "S.mp4"

    def out(cmd):
        fresh.parent.mkdir(parents=True, exist_ok=True)
        fresh.write_bytes(b"new")
        return f"File ready at '{fresh}'\n".encode()

    result, events = await _run(ManimExecutor(str(tmp_path)), out)
    assert result["status"] == "success"
    assert [e["rel_path"] for e in events if e["type"] == "file_ready"] == ["media/videos/demo/480p15/S.mp4"]


@pytest.mark.asyncio
async def test_output_stem_and_extra_args(tmp_path):
    """A snapshot run (_temp_run_x.py + --config_file) writes into the target script's folder."""
    target = tmp_path / "media" / "videos" / "demo" / "480p15" / "S.mp4"
    seen = {}

    def out(cmd):
        seen["cmd"] = cmd
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"new")
        return f"File ready at '{target}'\n".encode()

    executor = ManimExecutor(str(tmp_path))
    result, events = await _run(
        executor, out, script="_temp_run_ab.py", output_stem="demo", extra_args=["--config_file", "_temp_run_ab.cfg"]
    )
    assert result["status"] == "success"
    assert seen["cmd"][-2:] == ("--config_file", "_temp_run_ab.cfg")
    echo = next(e for e in events if e["type"] == "info")["message"]
    assert "--config_file" not in echo  # internal detail, not shown


@pytest.mark.asyncio
async def test_disk_fallback_uses_the_output_stem(tmp_path):
    target = tmp_path / "media" / "videos" / "demo" / "480p15" / "S.mp4"

    def out(cmd):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"new")
        return b"no file ready line\n"

    result, events = await _run(ManimExecutor(str(tmp_path)), out, script="_temp_run_ab.py", output_stem="demo")
    assert result["status"] == "success"
    assert [e["rel_path"] for e in events if e["type"] == "file_ready"] == ["media/videos/demo/480p15/S.mp4"]


# --------------------------------------------------------------------------- #
# Redaction gaps
# --------------------------------------------------------------------------- #


@pytest.fixture
def ws(tmp_path):
    workspace = tmp_path / "app" / "workspace"
    workspace.mkdir(parents=True)
    return workspace


def test_file_uris_are_redacted(ws):
    out = redact_host_paths(f"see file://{ws}/x.py and file://{ws.parent}/backend/main.py", str(ws), str(ws.parent))
    assert out == "see file://<workspace>/x.py and file://<app>/backend/main.py"


def test_trailing_dot_after_a_path(ws):
    assert redact_host_paths(f"saved in {ws}.", str(ws)) == "saved in <workspace>."
    assert redact_host_paths(f"saved in {ws}, ok", str(ws)) == "saved in <workspace>, ok"
    # A longer name is still a different path.
    assert str(ws) in redact_host_paths(f"{ws}.bak/x", str(ws)) or "workspace.bak" in redact_host_paths(f"{ws}.bak/x", str(ws))


def test_bare_workspace_is_named_not_erased(ws):
    assert redact_host_paths(f"cwd is {ws}", str(ws)) == "cwd is <workspace>"
    assert redact_host_paths(f"{ws}/a.py:3", str(ws)) == "a.py:3"


def test_repo_root_is_redacted(ws):
    root = ws.parent
    assert redact_host_paths(f"{root}/backend/main.py", str(ws), str(root)) == "<app>/backend/main.py"
    # The workspace (longer) still wins over the app root.
    assert redact_host_paths(f"{ws}/s.py", str(ws), str(root)) == "s.py"


def test_quoted_source_lines_in_a_traceback_are_left_as_written(ws):
    executor = ManimExecutor(str(ws))
    line = '│ ❱ 14 │   │   x = "/tmp/literal" + "~"                                   │'
    assert executor._redact_paths(line) == line
    line2 = '│   13 │   path = "' + str(ws) + '/a.py"   │'
    assert executor._redact_paths(line2) == line2
    # A frame header (path, not code) is still redacted.
    assert executor._redact_paths(f"│ {ws}/a.py:14 in construct │").startswith("│ a.py:14 in construct")


def test_keep_box_width_with_a_longer_replacement():
    original = "│ /u/x.py:1 in f              │"
    longer = "│ <site-packages>/x.py:1 in f              │"
    fixed = keep_box_width(original, longer)
    assert cell_len(fixed) == cell_len(original) and fixed.endswith(" │")


def test_keep_box_width_counts_cjk_as_two_cells():
    original = "│ 漢字 /very/long/host/path/a.py │"
    shorter = "│ 漢字 a.py │"
    fixed = keep_box_width(original, shorter)
    assert cell_len(fixed) == cell_len(original)


def test_cell_len_without_rich(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def no_rich(name, *args, **kwargs):
        if name.startswith("rich"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_rich)
    assert cell_len("ab漢") == 4
    assert cell_len("e\u0301") == 1


@pytest.mark.asyncio
async def test_path_wrapped_across_box_lines_is_redacted(tmp_path):
    """r2 (PSD): Rich folds a long frame path over several boxed lines; each half slipped past."""
    ws = tmp_path / ("deep_" + "w" * 60) / ("workspace_" + "v" * 40)
    executor = ManimExecutor(str(ws))
    path = f"{ws}/wrapped.py:5 in construct"
    width = 96
    pieces = [path[i:i + width] for i in range(0, len(path), width)]
    pieces[-1] = pieces[-1].ljust(width)
    assert " " not in pieces[0]
    lines = [f"│ {p} │" for p in pieces]
    assert len(lines) >= 2 and all(len(line) == 100 for line in lines)
    events = await _read(executor, ("\n".join(lines) + "\n│ next line" + " " * 86 + " │\n").encode())
    logs = _logs(events)
    assert not any("www" in line or "vvv" in line for line in logs), logs
    assert logs[0].startswith("│ wrapped.py:5") and len(logs[0]) == 100
    assert " in construct" in " ".join(logs[:2]) and logs[-1].startswith("│ next line")
    assert logs[-1].startswith("│ next line")


@pytest.mark.asyncio
async def test_function_name_after_a_folded_path_keeps_its_own_line(tmp_path):
    ws = tmp_path / ("w" * 120)
    executor = ManimExecutor(str(ws))
    path = f"{ws}/s.py:122"
    lines = [f"│ {path[i:i + 96]} │" for i in range(0, len(path), 96)]
    lines[-1] = "│ " + path[96 * (len(lines) - 1):].ljust(96) + " │"
    lines.append("│ " + "in render".ljust(96) + " │")
    # Make every line but the last two full (a fold), as Rich prints it.
    lines = [line for line in lines if line.strip("│ ")]
    events = await _read(executor, ("\n".join(lines) + "\n").encode())
    logs = _logs(events)
    assert not any("www" in line for line in logs)
    assert any(line.startswith("│ in render") for line in logs)


@pytest.mark.asyncio
async def test_full_box_lines_that_are_not_paths_are_untouched(tmp_path):
    executor = ManimExecutor(str(tmp_path / "ws"))
    lines = ["│ " + "x" * 20 + " │", "│ " + "y" * 20 + " │", "│ tail" + " " * 16 + " │"]
    events = await _read(executor, ("\n".join(lines) + "\n").encode())
    assert _logs(events) == lines


@pytest.mark.asyncio
async def test_wrapped_box_at_end_of_stream_is_flushed(tmp_path):
    executor = ManimExecutor(str(tmp_path / "ws"))
    events = await _read(executor, "│ abcdef │".encode())
    assert _logs(events) == ["│ abcdef │"]


@pytest.mark.asyncio
async def test_endless_line_is_cut_at_a_space_not_inside_a_path(tmp_path, monkeypatch):
    """r2 (PSD): a >64 KiB line was cut at a fixed size, splitting a path in two."""
    monkeypatch.setattr(executor_module, "MAX_PENDING_LINE_CHARS", 1000)
    ws = tmp_path / "ws"
    executor = ManimExecutor(str(ws))
    payload = (("y" * 50 + " " + f"{ws}/x.py ") * 200).encode()  # arrives without a newline for a while
    events = await _read(executor, payload, "stdout")  # no newline: only the length limit splits it
    logs = _logs(events)
    assert len(logs) > 1
    joined = "".join(logs)
    assert str(ws) not in joined and "/ws/" not in joined
    assert all(len(line) <= 1000 for line in logs[:-1])


@pytest.mark.asyncio
async def test_endless_line_without_spaces_is_still_cut(tmp_path, monkeypatch):
    monkeypatch.setattr(executor_module, "MAX_PENDING_LINE_CHARS", 100)
    executor = ManimExecutor(str(tmp_path / "ws"))
    events = await _read(executor, b"z" * 350, "stdout")
    assert [len(m) for m in _logs(events)] == [100, 100, 100, 50]


def test_diagnostics_hide_the_venv_and_app_paths(client, monkeypatch):
    import sys

    import main

    fake = {
        "manim": os.path.join(sys.prefix, "bin", "manim"),
        "manim_command": [os.path.join(sys.prefix, "bin", "manim")],
        "ffmpeg": "/usr/bin/ffmpeg",
        "latex": "Not Found",
        "dvisvgm": os.path.join(main.BASE_DIR, "tools", "dvisvgm"),
        "latex_available": False,
    }
    monkeypatch.setattr(main, "get_binary_paths", lambda: fake)
    deps = client.get("/api/diagnostics").json()["dependencies"]
    assert main.BASE_DIR not in str(deps)
    assert deps["ffmpeg"] == "/usr/bin/ffmpeg" and deps["latex"] == "Not Found"
    assert deps["latex_available"] is False
    assert deps["dvisvgm"] == "<app>/tools/dvisvgm"
    assert deps["manim"].endswith("/bin/manim") and isinstance(deps["manim_command"], list)


def test_renders_still_get_the_real_manim_path(monkeypatch):
    """Redaction is for the response only; the render socket uses the real command."""
    import main

    monkeypatch.setattr(main, "get_binary_paths", lambda: {"manim": "/real/venv/bin/manim", "manim_command": ["/real/venv/bin/manim"]})
    assert main._manim_command(main.get_binary_paths()) == ["/real/venv/bin/manim"]


@pytest.mark.asyncio
async def test_per_run_config_file_is_not_echoed(tmp_path):
    out = tmp_path / "media" / "videos" / "demo" / "480p15" / "S.mp4"

    def lines(cmd):
        assert "--config_file" in cmd
        out.parent.mkdir(parents=True)
        out.write_bytes(b"x")
        return (b"INFO     Reading config file: _temp_run_ab.cfg\n"
                + f"File ready at '{out}'\n".encode())

    result, events = await _run(ManimExecutor(str(tmp_path)), lines,
                                output_stem="demo", extra_args=["--config_file", "_temp_run_ab.cfg"])
    assert result["status"] == "success"
    assert not any("_temp_run_ab" in (e.get("message") or "") for e in events)


def test_folded_path_followed_by_words_wraps_at_a_space(tmp_path):
    ws = tmp_path / ("d" * 120)
    executor = ManimExecutor(str(ws))
    text = f"{ws}/helper.py:2 in boom"
    first, rest = text[:96], text[96:]
    lines = [f"│ {first} │", f"│ {rest.ljust(96)} │"]
    out = executor._rejoin_box_lines(lines)
    assert out == ["│ " + "helper.py:2 in boom".ljust(96) + " │"]
    long_ws = tmp_path / ("e" * 150)
    executor = ManimExecutor(str(long_ws))
    name = "h" * 90
    text = f"{long_ws}/{name}.py:2 in boom"
    lines = [f"│ {text[i:i + 96].ljust(96)} │" for i in range(0, len(text), 96)]
    out = executor._rejoin_box_lines(lines)
    assert all(len(line) == 100 for line in out)
    assert " ".join(line[2:-2].strip() for line in out) == f"{name}.py:2 in boom"  # no word cut in half
