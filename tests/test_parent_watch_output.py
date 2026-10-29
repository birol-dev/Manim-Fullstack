"""parent_watch.py must hand the child's output to the backend (Windows std handles)."""

import asyncio
import os
import subprocess
import sys

import pytest

from executor import PARENT_WATCH_SCRIPT, ManimExecutor, parent_guard

CHILD = (
    "import sys; "
    "print('hello out', flush=True); "
    "print('hello err', file=sys.stderr, flush=True); "
    "raise SystemExit(3)"
)


def _watch_command(source):
    return [sys.executable, PARENT_WATCH_SCRIPT, str(os.getpid()), "--", sys.executable, "-c", source]


def _windows_flags():
    if os.name != "nt":
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def test_output_reaches_the_parent_and_exit_code_is_passed_through():
    """Manim's stdout/stderr are lost on Windows when Popen gets no std handles."""
    result = subprocess.run(
        _watch_command(CHILD),
        capture_output=True,
        stdin=subprocess.DEVNULL,
        timeout=30,
        **_windows_flags(),
    )
    assert result.stdout.strip() == b"hello out"
    assert result.stderr.strip() == b"hello err"
    assert result.returncode == 3


def test_wrapped_child_without_output_still_exits_with_its_code():
    result = subprocess.run(
        _watch_command("raise SystemExit(4)"),
        capture_output=True,
        stdin=subprocess.DEVNULL,
        timeout=30,
        **_windows_flags(),
    )
    assert (result.stdout, result.stderr, result.returncode) == (b"", b"", 4)


@pytest.mark.asyncio
async def test_executor_reads_a_line_printed_through_the_watcher(monkeypatch):
    """A line the wrapped child prints arrives as a ``log`` event, not silence."""
    monkeypatch.setenv("MANIM_PARENT_WATCH", "watcher")
    executor = ManimExecutor(os.getcwd())
    events = []

    async def log_cb(event):
        events.append(event)

    cmd, preexec = parent_guard([sys.executable, "-c", "print('progress through the watcher', flush=True)"])
    kwargs = {
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.PIPE,
        "stdin": asyncio.subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True
        if preexec is not None:
            kwargs["preexec_fn"] = preexec

    process = await asyncio.create_subprocess_exec(*cmd, **kwargs)
    try:
        await asyncio.wait_for(
            asyncio.gather(
                executor._read_stream(process.stdout, "stdout", log_cb),
                executor._read_stream(process.stderr, "stderr", log_cb),
            ),
            timeout=30,
        )
        assert await process.wait() == 0
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()

    assert {
        "type": "log",
        "stream": "stdout",
        "message": "progress through the watcher",
    } in events
