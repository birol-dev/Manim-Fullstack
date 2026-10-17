"""Round 5 (Windows CI): code paths that only run on Windows, simulated on any OS.

On Windows a file that another handle has open can't be replaced or unlinked for
a moment (ERROR_SHARING_VIOLATION 32), and a file being replaced can't be opened
(ERROR_ACCESS_DENIED 5). file_ops retries those briefly instead of failing a save
with 500 or a read with 403.
"""

import os
import time

import pytest

import file_ops
import main


def _busy(winerror):
    exc = PermissionError(13, "busy")
    exc.winerror = winerror  # set by the OS on Windows only
    return exc


def _crt_busy():
    """What the built-in open() raises on Windows for a busy file: the C runtime
    maps sharing violations and pending deletes to EACCES and sets no winerror."""
    return PermissionError(13, "Permission denied")


@pytest.fixture
def windows(monkeypatch):
    monkeypatch.setattr(file_ops, "_WINDOWS", True)
    monkeypatch.setattr(file_ops, "WINDOWS_RETRY_SECONDS", 0.5)


def _flaky(fails, winerror, result="ok"):
    calls = {"n": 0}

    def fn(*_args):
        calls["n"] += 1
        if calls["n"] <= fails:
            raise _busy(winerror)
        return result

    return fn, calls


@pytest.mark.parametrize("winerror", [5, 32])
def test_busy_file_is_retried_on_windows(windows, winerror):
    fn, calls = _flaky(3, winerror)
    assert file_ops._retry_if_busy(fn, "x") == "ok" and calls["n"] == 4


def test_other_permission_errors_are_not_retried(windows):
    fn, calls = _flaky(1, 1314)  # e.g. a privilege error
    with pytest.raises(PermissionError):
        file_ops._retry_if_busy(fn)
    assert calls["n"] == 1


def test_open_style_eacces_without_winerror_is_retried(windows):
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] <= 3:
            raise _crt_busy()
        return "ok"

    assert file_ops._retry_if_busy(fn) == "ok" and calls["n"] == 4


def test_eperm_without_winerror_is_not_retried(windows):
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise PermissionError(1, "Operation not permitted")

    with pytest.raises(PermissionError):
        file_ops._retry_if_busy(fn)
    assert calls["n"] == 1


def test_retry_gives_up_after_the_deadline(windows):
    fn, calls = _flaky(10_000, 32)
    started = time.monotonic()
    with pytest.raises(PermissionError):
        file_ops._retry_if_busy(fn)
    assert 0.4 <= time.monotonic() - started < 2 and calls["n"] > 3


def test_posix_never_retries(monkeypatch):
    monkeypatch.setattr(file_ops, "_WINDOWS", False)
    fn, calls = _flaky(1, 32)
    with pytest.raises(PermissionError):
        file_ops._retry_if_busy(fn)
    assert calls["n"] == 1


def test_atomic_write_and_read_survive_a_busy_target(windows, tmp_path, monkeypatch):
    target = tmp_path / "a.py"
    target.write_bytes(b"old")
    real_replace, real_open = os.replace, open
    state = {"replace": 0, "open": 0}

    def replace(src, dst):
        state["replace"] += 1
        if state["replace"] <= 2:
            raise _busy(32)  # a reader still has it open
        real_replace(src, dst)

    monkeypatch.setattr(file_ops.os, "replace", replace)
    file_ops.atomic_write(str(target), b"new")
    assert target.read_bytes() == b"new" and state["replace"] == 3
    assert [p.name for p in tmp_path.iterdir()] == ["a.py"]

    def opener(path, *args, **kwargs):
        state["open"] += 1
        if state["open"] <= 2:
            raise _crt_busy()  # mid-replace, as open() reports it
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", opener)
    assert file_ops.read_bytes(str(target)) == b"new"


def test_sweep_with_min_age_zero_takes_files_written_this_instant(tmp_path, monkeypatch):
    """Windows' time.time() can lag a file's mtime; age 0 must still mean "all"."""
    (tmp_path / "media" / "videos" / "_temp_run_abc" / "480p15").mkdir(parents=True)
    (tmp_path / "assets").mkdir()
    video = tmp_path / "media" / "videos" / "_temp_run_abc" / "480p15" / "S.mp4"
    video.write_bytes(b"x")
    scratch = tmp_path / "_temp_run_abc.py"
    scratch.write_bytes(b"x")
    future = time.time() + 5
    os.utime(video, (future, future))
    os.utime(scratch, (future, future))
    monkeypatch.setattr(main, "WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setattr(main, "MEDIA_DIR", str(tmp_path / "media"))
    monkeypatch.setattr(main, "ASSETS_DIR", str(tmp_path / "assets"))
    main._sweep_temp_renders(min_age=0)
    assert not scratch.exists() and not video.exists()


def test_body_deadline_message_does_not_depend_on_rereading_the_clock(monkeypatch):
    """The deadline-vs-idle choice is made before waiting (coarse Windows clock)."""
    import asyncio

    monkeypatch.setattr(main, "BODY_DEADLINE_SECONDS", 0.2)
    monkeypatch.setattr(main, "BODY_READ_TIMEOUT_SECONDS", 5)
    real = time.monotonic
    first = {"at": None}

    def clock():
        # After the timeout fires, a coarse clock still reads just before the deadline.
        if first["at"] is None:
            first["at"] = real()
            return first["at"]
        return first["at"] + 0.2 - 0.004

    class CoarseTime:
        monotonic = staticmethod(clock)

        def __getattr__(self, name):
            return getattr(time, name)

    sent = []

    async def receive():
        await asyncio.sleep(10)

    async def send(message):
        sent.append(message)

    async def app(scope, receive_, send_):
        await receive_()
        await send_({"type": "http.response.start", "status": 200, "headers": []})
        await send_({"type": "http.response.body", "body": b""})

    monkeypatch.setattr(main, "time", CoarseTime())  # only main's view of the clock
    asyncio.run(main.RequestBodyLimitMiddleware(app)({"type": "http", "path": "/api/save", "method": "POST", "headers": []}, receive, send))
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    assert b"did not finish arriving within 0.2 seconds" in body
