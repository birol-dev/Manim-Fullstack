import asyncio
import os
import subprocess
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
