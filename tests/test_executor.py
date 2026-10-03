import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from executor import ManimExecutor


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/tmp/workspace/media/videos/demo/clip.mp4", "media/videos/demo/clip.mp4"),
        ("/home/media/workspace/media/videos/demo/clip.mp4", "media/videos/demo/clip.mp4"),
        ("media/videos/test.mp4", "media/videos/test.mp4"),
        ("/var/log/render.mp4", "render.mp4"),
    ],
)
def test_media_rel_path_extraction(path, expected):
    assert ManimExecutor._to_media_rel_path(path) == expected


def test_find_latest_render_nonexistent_workspace():
    executor = ManimExecutor("/nonexistent/workspace")
    assert executor._find_latest_render("script.py", "Scene") is None


def test_find_latest_render_empty_media_videos(tmp_path):
    videos = tmp_path / "media" / "videos" / "empty_script"
    videos.mkdir(parents=True)
    executor = ManimExecutor(str(tmp_path))
    assert executor._find_latest_render("empty_script.py", "Scene") is None


def test_find_latest_render_does_not_match_scene_prefix(tmp_path):
    videos = tmp_path / "media" / "videos" / "script"
    videos.mkdir(parents=True)
    decoy = videos / "SceneExtra.mp4"
    target = videos / "Scene.mp4"
    decoy.write_text("decoy", encoding="utf-8")
    target.write_text("target", encoding="utf-8")
    os.utime(str(decoy), (3, 3))
    os.utime(str(target), (2, 2))

    executor = ManimExecutor(str(tmp_path))
    latest = executor._find_latest_render("script.py", "Scene")
    assert os.path.basename(latest) == "Scene.mp4"


def test_find_latest_render_ignores_partial_movie_files(tmp_path):
    videos = tmp_path / "media" / "videos" / "script" / "1080p60"
    partial = videos / "partial_movie_files" / "Scene"
    partial.mkdir(parents=True)
    chunk = partial / "Scene.mp4"
    final = videos / "Scene.mp4"
    final.write_text("final", encoding="utf-8")
    chunk.write_text("chunk", encoding="utf-8")
    os.utime(str(final), (2, 2))
    os.utime(str(chunk), (5, 5))

    executor = ManimExecutor(str(tmp_path))
    latest = executor._find_latest_render("script.py", "Scene")
    assert latest == str(final)


def test_find_latest_render_mov_support(tmp_path):
    videos = tmp_path / "media" / "videos" / "script"
    videos.mkdir(parents=True)
    mov = videos / "Scene.mov"
    mov.write_text("mov", encoding="utf-8")

    executor = ManimExecutor(str(tmp_path))
    assert executor._find_latest_render("script.py", "Scene") == str(mov)


@pytest.mark.asyncio
async def test_stream_reader_extracts_progress_and_file_ready():
    executor = ManimExecutor("/workspace")
    events = []

    async def log_cb(evt):
        events.append(evt)

    stream = asyncio.StreamReader()
    stream.feed_data(
        b"Rendering Scene: [ 50%] 30/60\r\n"
        b"File ready at 'media/videos/demo/Scene.mp4'\r\n"
        b"LaTeX Error: dvisvgm failed\r\n"
    )
    stream.feed_eof()

    await executor._read_stream(stream, "stdout", log_cb)

    progress_events = [e for e in events if e.get("type") == "progress"]
    assert len(progress_events) == 1
    assert progress_events[0]["percent"] == 50

    file_events = [e for e in events if e.get("type") == "file_ready"]
    assert len(file_events) == 1
    assert file_events[0]["filename"] == "Scene.mp4"

    latex_events = [e for e in events if e.get("type") == "latex_error_warning"]
    assert len(latex_events) == 1


@pytest.mark.asyncio
async def test_stream_reader_handles_latin1_fallback():
    executor = ManimExecutor("/workspace")
    events = []

    async def log_cb(evt):
        events.append(evt)

    stream = asyncio.StreamReader()
    stream.feed_data(b"Non-utf8 \xe9\xe8\xe0 characters\n")
    stream.feed_eof()

    await executor._read_stream(stream, "stderr", log_cb)
    assert len(events) == 1
    assert events[0]["type"] == "log"


@pytest.mark.asyncio
async def test_stream_reader_cancelled_silently():
    executor = ManimExecutor("/workspace")
    stream = asyncio.StreamReader()
    task = asyncio.create_task(executor._read_stream(stream, "stdout", AsyncMock()))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_kill_process_windows():
    executor = ManimExecutor("/workspace")
    mock_proc = MagicMock()
    mock_proc.pid = 1234
    mock_proc.returncode = None
    executor.current_process = mock_proc

    with patch("platform.system", return_value="Windows"):
        with patch("subprocess.run") as mock_run:
            await executor.cancel()
            assert mock_run.call_count == 1
            cmd = mock_run.call_args[0][0]
            assert cmd == ["taskkill", "/F", "/T", "/PID", "1234"]


@pytest.mark.asyncio
async def test_kill_process_posix():
    executor = ManimExecutor("/workspace")
    mock_proc = MagicMock()
    mock_proc.pid = 5678
    mock_proc.returncode = None
    mock_proc.wait = AsyncMock(return_value=0)
    executor.current_process = mock_proc

    with patch("platform.system", return_value="Linux"):
        with patch("os.killpg", create=True) as mock_killpg:
            with patch("os.getpgid", return_value=5678, create=True):
                await executor.cancel()
                assert mock_killpg.call_count >= 1


@pytest.mark.asyncio
async def test_execute_success_and_fallback_render_finder(tmp_path):
    executor = ManimExecutor(str(tmp_path))
    videos_dir = tmp_path / "media" / "videos" / "script"
    videos_dir.mkdir(parents=True)
    render_file = videos_dir / "Scene.mp4"
    render_file.write_text("mp4", encoding="utf-8")

    mock_process = MagicMock()
    mock_process.pid = 1010
    mock_process.stdout = asyncio.StreamReader()
    # Output without "File ready at" line to trigger _find_latest_render fallback
    mock_process.stdout.feed_data(b"Render complete\n")
    mock_process.stdout.feed_eof()
    mock_process.stderr = asyncio.StreamReader()
    mock_process.stderr.feed_eof()
    mock_process.wait = AsyncMock(return_value=0)

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            res = await executor.execute(
                manim_path="/usr/bin/manim",
                script_name="script.py",
                scene_name="Scene",
                quality="custom_unsupported",
                use_opengl=False,
                log_callback=AsyncMock(),
            )
            assert res["success"] is True
            assert res["status"] == "success"


@pytest.mark.asyncio
async def test_execute_cancels_running_process_before_starting_new(tmp_path):
    executor = ManimExecutor(str(tmp_path))
    old_proc = MagicMock()
    old_proc.returncode = None
    executor.current_process = old_proc

    new_proc = MagicMock()
    new_proc.pid = 4040
    new_proc.stdout = asyncio.StreamReader()
    new_proc.stdout.feed_eof()
    new_proc.stderr = asyncio.StreamReader()
    new_proc.stderr.feed_eof()
    new_proc.wait = AsyncMock(return_value=0)

    with patch.object(executor, "cancel", new_callable=AsyncMock) as mock_cancel:
        with patch("asyncio.create_subprocess_exec", return_value=new_proc):
            res = await executor.execute(
                manim_path="/usr/bin/manim",
                script_name="script.py",
                scene_name="Scene",
                quality="h",
                use_opengl=True,
                log_callback=AsyncMock(),
            )
            mock_cancel.assert_called()
            assert res["success"] is True


@pytest.mark.asyncio
async def test_execute_handles_failure_exit_code(tmp_path):
    executor = ManimExecutor(str(tmp_path))
    mock_process = MagicMock()
    mock_process.pid = 2020
    mock_process.stdout = asyncio.StreamReader()
    mock_process.stdout.feed_eof()
    mock_process.stderr = asyncio.StreamReader()
    mock_process.stderr.feed_data(b"Fatal rendering crash\n")
    mock_process.stderr.feed_eof()
    mock_process.wait = AsyncMock(return_value=1)

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        res = await executor.execute(
            manim_path="/usr/bin/manim",
            script_name="script.py",
            scene_name="Scene",
            quality="l",
            use_opengl=True,
            log_callback=AsyncMock(),
        )
        assert res["success"] is False
        assert res["status"] == "failed"
        assert res["exit_code"] == 1


@pytest.mark.asyncio
async def test_execute_cancellation_during_run(tmp_path):
    executor = ManimExecutor(str(tmp_path))
    mock_process = MagicMock()
    mock_process.pid = 3030
    mock_process.returncode = None
    mock_process.stdout = asyncio.StreamReader()
    mock_process.stdout.feed_eof()
    mock_process.stderr = asyncio.StreamReader()
    mock_process.stderr.feed_eof()
    mock_process.wait = AsyncMock(side_effect=RuntimeError("Subprocess failed"))

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        with patch.object(executor, "cancel", new_callable=AsyncMock) as mock_cancel:
            res = await executor.execute(
                manim_path="/usr/bin/manim",
                script_name="script.py",
                scene_name="Scene",
                quality="l",
                use_opengl=False,
                log_callback=AsyncMock(),
            )
            assert res["success"] is False
            assert res["status"] == "error"
            mock_cancel.assert_called()


@pytest.mark.asyncio
async def test_execute_times_out(tmp_path):
    """Hung manim stdout should not block forever when render_timeout is set."""
    executor = ManimExecutor(str(tmp_path), render_timeout=0.05)

    mock_process = MagicMock()
    mock_process.pid = 9090
    mock_process.returncode = None
    # Never EOF — simulates a hung process
    mock_process.stdout = asyncio.StreamReader()
    mock_process.stderr = asyncio.StreamReader()
    mock_process.wait = AsyncMock(return_value=0)

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        with patch.object(executor, "cancel", new_callable=AsyncMock) as mock_cancel:
            res = await executor.execute(
                manim_path="/usr/bin/manim",
                script_name="script.py",
                scene_name="Scene",
                quality="l",
                use_opengl=False,
                log_callback=AsyncMock(),
            )
            assert res["success"] is False
            assert res["status"] == "timeout"
            mock_cancel.assert_called()


async def _read(executor, data: bytes, stream_name="stderr", chunks=1):
    events = []

    async def log_cb(evt):
        events.append(evt)

    stream = asyncio.StreamReader()
    size = max(1, len(data) // chunks)
    for i in range(0, len(data), size):
        stream.feed_data(data[i:i + size])
    stream.feed_eof()
    await executor._read_stream(stream, stream_name, log_cb)
    return events


@pytest.mark.asyncio
async def test_tqdm_carriage_return_progress_streams_live():
    executor = ManimExecutor("/workspace")
    bar = (
        "\rAnimation 0: Create(Circle()):   0%|          | 0/15 [00:00<?, ?it/s]"
        "\rAnimation 0: Create(Circle()):  40%|####      | 6/15 [00:00<00:00]"
        "\rAnimation 0: Create(Circle()):  40%|####      | 6/15 [00:00<00:00]"
        "\rAnimation 1: Write(Text('Hi: there')): 100%|##########| 15/15"
        "\r                                                  \r"
    ).encode()
    # Split across many chunks, including mid-character boundaries.
    events = await _read(executor, bar, chunks=17)

    assert [e["type"] for e in events] == ["progress", "progress", "progress"]
    assert [(e["animation"], e["percent"]) for e in events] == [(0, 0), (0, 40), (1, 100)]
    assert events[0]["label"] == "Create(Circle())"
    assert events[2]["label"] == "Write(Text('Hi: there'))"


@pytest.mark.asyncio
async def test_utf8_split_across_chunks_and_ansi_is_stripped():
    executor = ManimExecutor("/workspace")
    data = "\x1b[32mINFO\x1b[0m  Rendered ✓ scène\n".encode("utf-8")
    events = await _read(executor, data, stream_name="stdout", chunks=len(data))
    assert events == [{"type": "log", "stream": "stdout", "message": "INFO  Rendered ✓ scène"}]


@pytest.mark.asyncio
async def test_unterminated_output_is_flushed_and_capped():
    executor = ManimExecutor("/workspace")
    huge = b"x" * (200 * 1024)
    events = await _read(executor, huge, chunks=40)
    assert sum(len(e["message"]) for e in events) == len(huge)
    assert all(len(e["message"]) <= 64 * 1024 + 8192 for e in events)


@pytest.mark.asyncio
async def test_image_output_and_single_latex_hint(tmp_path):
    executor = ManimExecutor(str(tmp_path))
    data = (
        b"File ready at '/w/media/images/demo/Still_ManimCE_v0.21.0.png'\n"
        b"FileNotFoundError: No such file or directory: 'latex'\n"
        b"LaTeX compilation error again\n"
    )
    events = await _read(executor, data, stream_name="stdout")
    ready = [e for e in events if e["type"] == "file_ready"]
    assert ready[0]["kind"] == "image"
    assert ready[0]["rel_path"] == "media/images/demo/Still_ManimCE_v0.21.0.png"
    assert len([e for e in events if e["type"] == "latex_error_warning"]) == 1


def test_find_latest_render_falls_back_to_images(tmp_path):
    images = tmp_path / "media" / "images" / "demo"
    images.mkdir(parents=True)
    png = images / "Still_ManimCE_v0.21.0.png"
    png.write_text("png", encoding="utf-8")
    (images / "StillLife_ManimCE_v0.21.0.png").write_text("other", encoding="utf-8")
    executor = ManimExecutor(str(tmp_path))
    assert executor._find_latest_render("demo.py", "Still") == str(png)


def test_build_args_and_subprocess_env():
    assert ManimExecutor.build_args("a.py", "S", "h", False) == ["a.py", "S", "-qh", "--progress_bar=display"]
    assert ManimExecutor.build_args("a.py", "S", "zz", True) == [
        "a.py", "S", "-qm", "--renderer=opengl", "--write_to_movie", "--progress_bar=display",
    ]
    env = ManimExecutor("/w")._subprocess_env()
    assert env["COLUMNS"] == "400"
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"


@pytest.mark.asyncio
async def test_execute_accepts_command_prefix(tmp_path):
    executor = ManimExecutor(str(tmp_path))
    proc = MagicMock()
    proc.pid = 1
    proc.returncode = None
    proc.stdout = asyncio.StreamReader()
    proc.stdout.feed_eof()
    proc.stderr = asyncio.StreamReader()
    proc.stderr.feed_eof()
    proc.wait = AsyncMock(return_value=0)
    log = AsyncMock()
    with patch("asyncio.create_subprocess_exec", return_value=proc) as spawn:
        await executor.execute(["py", "-m", "manim"], "a.py", "S", "l", False, log)
    assert spawn.call_args[0][:5] == ("py", "-m", "manim", "a.py", "S")
    assert log.call_args_list[0][0][0] == {"type": "info", "message": "$ manim a.py S -ql --progress_bar=display"}


@pytest.mark.asyncio
async def test_cancel_mid_render_reports_cancelled_not_error(tmp_path):
    """cancel() drops the process handle; execute() must still finish cleanly."""
    executor = ManimExecutor(str(tmp_path))
    proc = MagicMock()
    proc.pid = 4242
    proc.returncode = None
    proc.stdout = asyncio.StreamReader()
    proc.stderr = asyncio.StreamReader()
    proc.wait = AsyncMock(return_value=-15)
    events = []

    async def log_cb(evt):
        events.append(evt)

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        with patch("platform.system", return_value="Linux"):
            with patch("os.killpg", create=True), patch("os.getpgid", return_value=4242, create=True):
                task = asyncio.create_task(executor.execute("/bin/manim", "a.py", "S", "l", False, log_cb))
                await asyncio.sleep(0.01)
                assert executor.is_running
                await executor.cancel()
                assert executor.current_process is None
                proc.stdout.feed_eof()
                proc.stderr.feed_eof()
                result = await task

    assert result == {"success": False, "status": "cancelled"}
    assert not any(e["type"] == "error" for e in events)


@pytest.mark.asyncio
async def test_rich_source_column_is_stripped():
    executor = ManimExecutor("/workspace")
    data = (
        "INFO     Combining to Movie file.                                   scene_file_writer.py:952\n"
        "INFO                                                               scene_file_writer.py:1103\n"
        "         File ready at '/w/media/videos/demo/480p15/Intro.mp4'\n"
        "NameError: name 'x' is not defined\n"
    ).encode()
    events = await _read(executor, data, stream_name="stdout")
    messages = [e["message"] for e in events if e["type"] == "log"]
    assert messages == [
        "INFO     Combining to Movie file.",
        "         File ready at '/w/media/videos/demo/480p15/Intro.mp4'",
        "NameError: name 'x' is not defined",
    ]
    assert any(e["type"] == "file_ready" for e in events)


@pytest.mark.asyncio
async def test_cancel_during_spawn_is_not_lost(tmp_path):
    """A cancel that arrives before the process exists stops it as soon as it starts."""
    executor = ManimExecutor(str(tmp_path))
    proc = MagicMock()
    proc.pid = 77
    proc.returncode = None
    proc.stdout = asyncio.StreamReader()
    proc.stdout.feed_eof()
    proc.stderr = asyncio.StreamReader()
    proc.stderr.feed_eof()
    proc.wait = AsyncMock(return_value=-15)

    async def spawn(*args, **kwargs):
        await executor.cancel()  # user pressed Cancel while Manim was starting
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=spawn):
        with patch("platform.system", return_value="Linux"):
            with patch("os.killpg", create=True) as killpg, patch("os.getpgid", return_value=77, create=True):
                result = await executor.execute("/bin/manim", "a.py", "S", "l", False, AsyncMock())

    assert result == {"success": False, "status": "cancelled"}
    killpg.assert_called()
    # Outside a render, cancel() is a no-op and leaves no pending state behind.
    await executor.cancel()
    assert executor._cancel_pending is False
