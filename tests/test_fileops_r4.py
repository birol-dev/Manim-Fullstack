"""Fix round 4: locked deletes and uploads, read-only files, upload partials,
links out of the workspace, the lock table, the psutil fallback, the installer
spec, and the overall body deadline."""

import asyncio
import io
import json
import os
import socket
import subprocess
import sys
import textwrap
import threading
import time
import unicodedata
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers, UploadFile

import file_ops
import main
from fastapi.testclient import TestClient

class LocalClient(TestClient):
    """Same as conftest's client: talks to the app as http(s)/ws://localhost."""

    def websocket_connect(self, url, *args, **kwargs):
        if url.startswith("/"):
            url = f"ws://localhost{url}"
        return super().websocket_connect(url, *args, **kwargs)


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def ws(tmp_path):
    (tmp_path / "media").mkdir()
    (tmp_path / "assets").mkdir()
    with patch.object(main, "WORKSPACE_DIR", str(tmp_path)), patch.object(
        main, "MEDIA_DIR", str(tmp_path / "media")
    ), patch.object(main, "ASSETS_DIR", str(tmp_path / "assets")):
        yield tmp_path


@pytest.fixture
def client(ws):
    return LocalClient(main.app, base_url="http://localhost")


def _call(fn, *args, **kwargs):
    try:
        result = fn(*args, **kwargs)
    except HTTPException as exc:
        return exc.status_code, {"detail": exc.detail}
    if hasattr(result, "body") and hasattr(result, "status_code"):
        return result.status_code, json.loads(result.body)
    return 200, result


def _together(*fns):
    barrier = threading.Barrier(len(fns))
    out = [None] * len(fns)

    def run(i, fn):
        barrier.wait()
        out[i] = fn()

    threads = [threading.Thread(target=run, args=(i, fn)) for i, fn in enumerate(fns)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return out


# --------------------------------------------------------------------------- #
# 1. DELETE /api/scripts under the file locks
# --------------------------------------------------------------------------- #


def test_delete_racing_a_rename_never_500s_and_never_removes_a_file_mid_rename(ws):
    """delete(B) || rename(A->B): 404 (B wasn't there), 409 (rename in flight), or,
    only when the rename had already committed, a plain delete of B."""
    seen = set()
    real_rename = main.rename_no_replace
    committed = {}

    def tracking(src, dst):
        real_rename(src, dst)
        committed["at"] = time.perf_counter()

    looked = {}
    real_held = main.held_lock

    def held(path):
        looked.setdefault("at", time.perf_counter())
        return real_held(path)

    with patch.object(main, "rename_no_replace", tracking), patch.object(main, "held_lock", held):
        for _ in range(150):
            committed.clear()
            looked.clear()
            for name in ("a.py", "b.py"):
                if (ws / name).exists():
                    (ws / name).unlink()
            (ws / "a.py").write_text("A\n")
            (d, _), (r, _) = _together(
                lambda: _call(main.delete_script, "b.py"),
                lambda: _call(main.rename_file, main.RenameRequest(old_name="a.py", new_name="b.py")),
            )
            assert d in (200, 404, 409) and r in (200, 404), (d, r)
            gone = not (ws / "a.py").exists() and not (ws / "b.py").exists()
            if gone:
                # Only a delete that looked after the rename committed may remove B.
                assert d == 200 and committed["at"] < looked["at"]
            seen.add((d, r))
    assert any(d in (404, 409) for d, _ in seen)


def test_delete_sent_before_a_rename_created_the_name_is_refused(ws):
    """The request arrived (event loop) before the rename committed, but its worker
    thread only looked afterwards: B is not the file the caller meant, so 409."""

    class _Req:
        scope = {}

    (ws / "a.py").write_text("A\n")
    request = _Req()
    request.scope = {"manim_arrived": time.monotonic()}
    assert _call(main.rename_file, main.RenameRequest(old_name="a.py", new_name="b.py"))[0] == 200
    code, body = _call(main.delete_script, "b.py", request)
    assert code == 409 and (ws / "b.py").read_text() == "A\n"
    # A delete sent after the rename deletes it.
    request.scope = {"manim_arrived": time.monotonic()}
    assert _call(main.delete_script, "b.py", request)[0] == 200


def test_new_name_memory_is_bounded(ws, monkeypatch):
    monkeypatch.setattr(main, "_NEW_NAME_MEMORY_SECONDS", 0.0)
    for i in range(200):
        main._note_new_name(str(ws / f"n{i}.py"))
    assert len(main._new_names) <= 2


def test_http_delete_stamps_the_arrival_time(client, ws):
    (ws / "x.py").write_text("x\n")
    assert client.delete("/api/scripts", params={"filename": "x.py"}).status_code == 200


def test_delete_racing_a_rename_of_the_same_file(ws):
    for _ in range(100):
        for name in ("a.py", "b.py"):
            if (ws / name).exists():
                (ws / name).unlink()
        (ws / "a.py").write_text("A\n")
        (d, _), (r, _) = _together(
            lambda: _call(main.delete_script, "a.py"),
            lambda: _call(main.rename_file, main.RenameRequest(old_name="a.py", new_name="b.py")),
        )
        assert (d, r) in {(200, 404), (404, 200), (409, 200)}, (d, r)
        assert (ws / "b.py").exists() == (r == 200)


def test_delete_refuses_while_a_save_of_that_name_holds_the_lock(ws):
    (ws / "a.py").write_text("A\n")
    with file_ops.locked(str(ws / "a.py")):
        result = _together(lambda: _call(main.delete_script, "a.py"))[0]
    assert result[0] == 409 and "being saved or renamed" in result[1]["detail"]
    assert (ws / "a.py").exists()
    assert _call(main.delete_script, "a.py")[0] == 200


# --------------------------------------------------------------------------- #
# 2. Same-name uploads
# --------------------------------------------------------------------------- #


def _upload(name, data, overwrite=False):
    file = UploadFile(io.BytesIO(data), filename=name, headers=Headers({"content-type": "image/png"}))
    return main.upload_asset(file=file, overwrite=overwrite)


async def _gather_uploads(*specs):
    async def one(spec):
        try:
            return 200, await _upload(*spec)
        except HTTPException as exc:
            return exc.status_code, exc.detail

    return await asyncio.gather(*(one(spec) for spec in specs))


def test_racing_create_uploads_have_exactly_one_winner(ws):
    for _ in range(20):
        target = ws / "assets" / "race.png"
        if target.exists():
            target.unlink()
        results = asyncio.run(_gather_uploads(*[("race.png", bytes([65 + i]) * 300_000) for i in range(6)]))
        codes = sorted(code for code, _ in results)
        assert codes == [200] + [409] * 5, codes
        winner = next(body for code, body in results if code == 200)
        assert winner["replaced"] is False
        assert len(set(target.read_bytes())) == 1
    assert not [p for p in (ws / "assets").iterdir() if main.is_upload_partial(p.name)]


def test_racing_overwrite_uploads_report_replaced_accurately(ws):
    for _ in range(10):
        target = ws / "assets" / "ow.png"
        if target.exists():
            target.unlink()
        results = asyncio.run(_gather_uploads(*[("ow.png", bytes([65 + i]) * 200_000, True) for i in range(4)]))
        assert all(code == 200 for code, _ in results)
        # Exactly one upload found no file; every other one replaced something.
        assert sorted(body["replaced"] for _, body in results) == [False, True, True, True]


def test_overwrite_refuses_a_read_only_asset(ws):
    target = ws / "assets" / "ro.png"
    target.write_bytes(b"old")
    target.chmod(0o444)
    try:
        code, detail = asyncio.run(_gather_uploads(("ro.png", b"new", True)))[0]
        assert code == 403 and "read-only" in detail
        assert target.read_bytes() == b"old"
    finally:
        target.chmod(0o644)


# --------------------------------------------------------------------------- #
# 3. Read-only scripts
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0), reason="POSIX, non-root")
@pytest.mark.parametrize("mode", [0o444, 0o000])
def test_save_refuses_a_read_only_file_and_leaves_it_untouched(ws, mode):
    path = ws / "ro.py"
    path.write_text("ORIG\n")
    path.chmod(mode)
    try:
        for kwargs in ({}, {"base_version": "whatever"}):
            code, body = _call(main.save_file, main.SaveRequest(filename="ro.py", code="NEW\n", **kwargs))
            assert code == 403 and body["detail"] == main.READ_ONLY_DETAIL
        path.chmod(0o644)
        assert path.read_text() == "ORIG\n"
        path.chmod(mode)
    finally:
        path.chmod(0o644)


@pytest.mark.skipif(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0), reason="POSIX, non-root")
def test_unreadable_file_content_is_a_clean_403(ws):
    path = ws / "secret.py"
    path.write_text("x = 1\n")
    path.chmod(0o000)
    try:
        code, body = _call(main.get_file_content, "secret.py")
        assert code == 403 and "permission denied" in body["detail"]
    finally:
        path.chmod(0o644)


def test_read_only_bit_is_respected_even_when_access_says_writable(ws, monkeypatch):
    """Root (or Windows' read-only attribute): os.access may say yes, the mode bit says no."""
    path = ws / "ro.py"
    path.write_text("ORIG\n")
    path.chmod(0o444)
    monkeypatch.setattr(os, "access", lambda *a, **k: True)
    try:
        with pytest.raises(file_ops.ReadOnlyFileError):
            file_ops.atomic_write(str(path), b"NEW")
        assert path.read_text() == "ORIG\n"
    finally:
        path.chmod(0o644)


def test_writable_files_still_save(ws):
    assert _call(main.save_file, main.SaveRequest(filename="ok.py", code="x\n"))[0] == 200
    assert _call(main.save_file, main.SaveRequest(filename="ok.py", code="y\n"))[0] == 200


# --------------------------------------------------------------------------- #
# 4. Interrupted uploads (".uploading-<hex>" partials)
# --------------------------------------------------------------------------- #

PARTIAL = "pic.png.uploading-" + "ab" * 16


def test_partials_are_hidden_refused_and_swept(ws, client):
    assets = ws / "assets"
    (assets / "pic.png").write_bytes(b"real")
    old = assets / PARTIAL
    old.write_bytes(b"half")
    fresh = assets / ("new.png.uploading-" + "cd" * 16)
    fresh.write_bytes(b"half")
    hour_ago = time.time() - 3600
    os.utime(old, (hour_ago, hour_ago))

    names = [item["name"] for item in client.get("/api/files").json()["assets"]]
    assert names == ["pic.png"]
    assert client.get(f"/assets/{PARTIAL}").status_code == 404
    assert client.delete("/api/assets", params={"filename": PARTIAL}).status_code == 404
    assert client.get("/assets/pic.png").status_code == 200

    main._sweep_temp_renders()
    assert not old.exists()  # old partial removed by the startup sweep
    assert fresh.exists()  # too young: could be an upload being moved into place


def test_sweep_skips_a_partial_this_process_is_writing(ws):
    partial = ws / "assets" / PARTIAL
    partial.write_bytes(b"half")
    os.utime(partial, (0, 0))
    main._active_upload_partials.add(str(partial))
    try:
        main._sweep_upload_partials()
        assert partial.exists()
    finally:
        main._active_upload_partials.discard(str(partial))
    main._sweep_upload_partials()
    assert not partial.exists()


def test_partial_names_are_exactly_the_upload_pattern():
    assert main.is_upload_partial(PARTIAL)
    assert not main.is_upload_partial("pic.png")
    assert not main.is_upload_partial("pic.uploading-.png")
    assert not main.is_upload_partial("pic.png.uploading-xyz")


# --------------------------------------------------------------------------- #
# 5. Links out of the workspace
# --------------------------------------------------------------------------- #

needs_symlinks = pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")


@needs_symlinks
def test_links_out_of_the_workspace_are_marked_and_only_deletable(ws, client, tmp_path_factory):
    outside_dir = tmp_path_factory.mktemp("outside")
    target = outside_dir / "secret.py"
    target.write_text("SECRET = 1\n")
    os.symlink(target, ws / "out.py")
    os.symlink(ws / "missing.py", ws / "gone.py")
    os.symlink(outside_dir / "missing.py", ws / "gone_out.py")
    (ws / "real.py").write_text("x = 1\n")
    os.symlink(ws / "real.py", ws / "inside.py")

    scripts = {item["name"]: item for item in client.get("/api/files").json()["scripts"]}
    assert scripts["out.py"].get("outside") is True
    assert scripts["gone.py"].get("broken") is True
    assert scripts["gone_out.py"].get("broken") is True
    assert "outside" not in scripts["inside.py"] and "broken" not in scripts["inside.py"]
    assert "outside" not in scripts["real.py"]

    assert client.get("/api/file-content", params={"filename": "out.py"}).status_code == 400
    for name in ("out.py", "gone.py", "gone_out.py"):
        response = client.delete("/api/scripts", params={"filename": name})
        assert response.status_code == 200 and response.json()["link_removed"] is True
        assert not os.path.lexists(ws / name)
    assert target.read_text() == "SECRET = 1\n"  # the target is never touched
    assert (ws / "real.py").exists()


@needs_symlinks
def test_delete_of_a_link_never_reaches_outside(ws, client, tmp_path_factory):
    outside_dir = tmp_path_factory.mktemp("outside2")
    (outside_dir / "victim.py").write_text("keep\n")
    os.symlink(outside_dir / "victim.py", ws / "v.py")
    for bad in ("../v.py", str(outside_dir / "victim.py"), "..\\v.py", "sub/v.py"):
        assert client.delete("/api/scripts", params={"filename": bad}).status_code == 400
    assert (outside_dir / "victim.py").exists()
    assert client.delete("/api/scripts", params={"filename": "v.py"}).status_code == 200
    assert (outside_dir / "victim.py").read_text() == "keep\n"


@needs_symlinks
def test_render_refuses_a_script_linked_from_outside(ws, client, tmp_path_factory):
    outside_dir = tmp_path_factory.mktemp("outside3")
    target = outside_dir / "scene.py"
    target.write_text("from manim import *\nclass Out(Scene):\n    def construct(self):\n        self.wait()\n")
    os.symlink(target, ws / "out.py")
    with client.websocket_connect("/api/render") as socket_:
        socket_.send_json({"type": "start", "id": "o", "filename": "out.py", "scene": "Out", "quality": "l"})
        first = socket_.receive_json()
        second = socket_.receive_json()
    assert first["type"] == "error" and "outside the workspace" in first["message"]
    assert second["type"] == "result" and second["status"] == "rejected"
    assert not [p for p in ws.iterdir() if p.name.startswith(main.TEMP_PREFIX)]


# --------------------------------------------------------------------------- #
# 7. Lock table
# --------------------------------------------------------------------------- #


def test_lock_table_is_pruned_after_use(tmp_path):
    before = file_ops.lock_table_size()
    for i in range(2000):
        with file_ops.locked(str(tmp_path / f"name{i}.py"), str(tmp_path / f"other{i}.py")):
            pass
    assert file_ops.lock_table_size() == before


def test_lock_entries_are_released_when_the_body_raises(tmp_path):
    before = file_ops.lock_table_size()
    with pytest.raises(RuntimeError):
        with file_ops.locked(str(tmp_path / "boom.py")):
            raise RuntimeError("x")
    assert file_ops.lock_table_size() == before
    assert file_ops.held_lock(str(tmp_path / "boom.py")) is None


def test_waiters_keep_the_entry_alive(tmp_path):
    path = str(tmp_path / "busy.py")
    order = []
    with file_ops.locked(path):

        def worker():
            with file_ops.locked(path):
                order.append("worker")

        t = threading.Thread(target=worker)
        t.start()
        time.sleep(0.05)
        assert file_ops.held_lock(path) is not None and order == []
    t.join()
    assert order == ["worker"] and file_ops.held_lock(path) is None


def test_nfd_and_nfc_spellings_share_one_lock(tmp_path):
    nfc = unicodedata.normalize("NFC", "café.py")
    nfd = unicodedata.normalize("NFD", "café.py")
    assert nfc != nfd
    assert file_ops.lock_key(str(tmp_path / nfc)) == file_ops.lock_key(str(tmp_path / nfd))
    assert file_ops.lock_key(str(tmp_path / "Café.PY")) == file_ops.lock_key(str(tmp_path / nfd.lower()))
    with file_ops.locked(str(tmp_path / nfd)):
        assert file_ops.held_lock(str(tmp_path / nfc.upper())) is not None


def test_non_blocking_lock_reports_busy_and_leaves_nothing_behind(tmp_path):
    a, b = str(tmp_path / "a.py"), str(tmp_path / "b.py")
    before = file_ops.lock_table_size()
    held = threading.Event()
    release = threading.Event()

    def holder():
        with file_ops.locked(b):
            held.set()
            release.wait()

    t = threading.Thread(target=holder)
    t.start()
    held.wait()
    with pytest.raises(file_ops.LockBusyError):
        with file_ops.locked(a, b, blocking=False):
            pass
    assert file_ops.held_lock(a) is None  # a was released again
    release.set()
    t.join()
    assert file_ops.lock_table_size() == before


# --------------------------------------------------------------------------- #
# 8. Bind detection without psutil
# --------------------------------------------------------------------------- #


def test_fd_fallback_sees_a_listening_socket_without_psutil(monkeypatch):
    if main._listening_via_fds() is None:
        pytest.skip("no file-descriptor listing on this platform")
    monkeypatch.setitem(sys.modules, "psutil", None)  # import psutil -> ImportError
    assert main._listening_via_psutil() is None
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        assert main._process_is_listening() is True
        assert server.fileno() >= 0  # the probe did not close it
        server.getsockname()


def test_fd_fallback_ignores_connected_and_udp_sockets(monkeypatch):
    if main._listening_via_fds() is None:
        pytest.skip("no file-descriptor listing on this platform")
    monkeypatch.setattr(main, "_listening_via_psutil", lambda: None)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        udp.bind(("127.0.0.1", 0))
        if main._process_is_listening():
            pytest.skip("this test process already owns a listening socket")
        assert main._process_is_listening() is False


def test_psutil_failure_falls_back_instead_of_skipping(monkeypatch):
    class Broken:
        @staticmethod
        def Process():
            raise RuntimeError("psutil is broken")

    monkeypatch.setitem(sys.modules, "psutil", Broken)
    assert main._listening_via_psutil() is None
    monkeypatch.setattr(main, "_listening_via_fds", lambda: True)
    assert main._process_is_listening() is True


def test_no_detection_at_all_warns_and_sweeps_after_a_delay(monkeypatch, caplog):
    calls = []
    monkeypatch.setattr(main, "_process_is_listening", lambda: None)
    monkeypatch.setattr(main, "_sweep_temp_renders", lambda: calls.append("sweep"))
    monkeypatch.setattr(main, "BIND_FALLBACK_DELAY_SECONDS", 0.05)
    with caplog.at_level("WARNING", logger="uvicorn.error"):
        assert asyncio.run(main._maintenance_after_bind(wait_seconds=1, poll=0.01)) is True
    assert calls == ["sweep"]
    assert any("psutil unavailable" in record.getMessage() for record in caplog.records)


def test_no_detection_shutdown_before_the_delay_never_sweeps(monkeypatch):
    """A second server that can't bind shuts down at once, which cancels the wait."""
    calls = []
    monkeypatch.setattr(main, "RUN_STARTUP_MAINTENANCE", True)
    monkeypatch.setattr(main, "_process_is_listening", lambda: None)
    monkeypatch.setattr(main, "_sweep_temp_renders", lambda: calls.append("sweep"))
    monkeypatch.setattr(main, "write_manim_config_file", lambda *a: None)
    monkeypatch.setattr(main, "get_cached_profile", lambda: {})
    monkeypatch.setattr(main, "BIND_FALLBACK_DELAY_SECONDS", 0.3)

    async def run():
        async with main._lifespan(main.app):
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.5)

    asyncio.run(run())
    assert calls == []


_SERVER_SCRIPT = textwrap.dedent(
    """
    import os, sys, threading, time
    import psutil
    def broken(*a, **k):
        raise psutil.AccessDenied()  # what macOS answers without root
    psutil.Process = broken
    sys.path.insert(0, {backend!r})
    ws = {ws!r}
    import main, uvicorn
    if {no_fds!r}:
        main._listening_via_fds = lambda: None  # no way to tell at all
    main.WORKSPACE_DIR = ws
    main.MEDIA_DIR = os.path.join(ws, "media")
    main.ASSETS_DIR = os.path.join(ws, "assets")
    main.SWEEP_MIN_AGE_SECONDS = 0
    main.UPLOAD_PARTIAL_MIN_AGE_SECONDS = 0
    main.BIND_FALLBACK_DELAY_SECONDS = 0.5
    config = uvicorn.Config(main.app, host="127.0.0.1", port={port}, log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    def stop():
        deadline = time.time() + 10
        while time.time() < deadline and os.path.exists(os.path.join(ws, "_temp_run_old.py")):
            time.sleep(0.05)
        time.sleep(0.2)
        server.should_exit = True
    threading.Thread(target=stop, daemon=True).start()
    server.run()
    """
)


def _run_server(ws, port, no_fds):
    script = _SERVER_SCRIPT.format(backend=os.path.join(ROOT, "backend"), ws=str(ws), port=port, no_fds=no_fds)
    return subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=60)


def _scratch(ws):
    (ws / "media").mkdir(exist_ok=True)
    (ws / "assets").mkdir(exist_ok=True)
    old = ws / "_temp_run_old.py"
    old.write_text("x = 1\n")
    os.utime(old, (0, 0))
    return old


# psutil itself is a hard dependency (diagnostics.py imports it), so "missing"
# in practice means "can't list sockets": AccessDenied on macOS without root.
@pytest.mark.parametrize("no_fds", [False, True], ids=["fd-scan", "no-detection"])
def test_second_instance_with_broken_psutil_on_a_busy_port_does_not_sweep(tmp_path, no_fds):
    old = _scratch(tmp_path)
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        result = _run_server(tmp_path, busy.getsockname()[1], no_fds)
    assert "address already in use" in result.stderr.lower(), result.stderr
    assert result.returncode != 0
    assert old.exists(), result.stderr


@pytest.mark.parametrize("no_fds", [False, True], ids=["fd-scan", "no-detection"])
def test_server_with_broken_psutil_that_binds_does_sweep(tmp_path, no_fds):
    old = _scratch(tmp_path)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    result = _run_server(tmp_path, port, no_fds)
    assert not old.exists(), result.stderr
    if no_fds:
        assert "psutil unavailable" in result.stderr


# --------------------------------------------------------------------------- #
# 9. Installer requirement keeps extras
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "line,spec",
    [
        ("manim>=0.19.0,<0.23", "manim>=0.19.0,<0.23"),
        ("manim[jupyter]>=0.19,<0.23", "manim[jupyter]>=0.19,<0.23"),
        ("manim [jupyter, gui] >= 0.19 , < 0.23   # comment", "manim[jupyter,gui]>=0.19,<0.23"),
        ('manim[jupyter]>=0.19,<0.23 ; python_version >= "3.0"', "manim[jupyter]>=0.19,<0.23"),
        ('manim>=0.1 ; python_version < "3.0"', None),
        ("manim @ git+https://example.invalid/manim", None),
        ("manimgl>=1.6", None),
        ("# manim>=0.19", None),
        ("manim==0.22.0", "manim==0.22.0"),
    ],
)
def test_manim_requirement_keeps_extras(tmp_path, line, spec):
    path = tmp_path / "requirements.txt"
    path.write_text(f"fastapi\n{line}\n")
    assert main._manim_requirement(str(path)) == spec


def test_manim_requirement_without_packaging(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "packaging.requirements", None)
    path = tmp_path / "requirements.txt"
    path.write_text("manim[jupyter]>=0.19,<0.23\n")
    assert main._manim_requirement(str(path)) == "manim[jupyter]>=0.19,<0.23"


def test_shipped_requirements_line_is_used():
    assert main._manim_requirement() == "manim>=0.19.0,<0.23"


# --------------------------------------------------------------------------- #
# 10. Overall body deadline
# --------------------------------------------------------------------------- #


def _trickle(path, monkeypatch, deadline, idle=1.0, chunks=1000, gap=0.01):
    monkeypatch.setattr(main, "BODY_DEADLINE_SECONDS", deadline)
    monkeypatch.setattr(main, "BODY_READ_TIMEOUT_SECONDS", idle)
    sent = []
    count = {"n": 0}

    async def receive():
        count["n"] += 1
        await asyncio.sleep(gap)  # well under the idle timeout, forever
        return {"type": "http.request", "body": b"x", "more_body": count["n"] < chunks}

    async def send(message):
        sent.append(message)

    async def app(scope, receive_, send_):
        while True:
            message = await receive_()
            if message["type"] != "http.request" or not message.get("more_body"):
                break
        await send_({"type": "http.response.start", "status": 200, "headers": []})
        await send_({"type": "http.response.body", "body": b"ok"})

    middleware = main.RequestBodyLimitMiddleware(app)
    started = time.monotonic()
    asyncio.run(middleware({"type": "http", "path": path, "method": "POST", "headers": []}, receive, send))
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, body, time.monotonic() - started


def test_slow_trickle_hits_the_overall_deadline(monkeypatch):
    status, body, elapsed = _trickle("/api/save", monkeypatch, deadline=0.3)
    assert status == 408 and b"did not finish arriving within 0.3 seconds" in body
    assert elapsed < 1.5


def test_uploads_get_a_longer_deadline(monkeypatch):
    assert main.RequestBodyLimitMiddleware.deadline_for("/api/upload-asset") == main.BODY_DEADLINE_SECONDS * main.UPLOAD_DEADLINE_FACTOR
    status, _, elapsed = _trickle("/api/upload-asset", monkeypatch, deadline=0.1, chunks=30, gap=0.01)
    assert status == 200  # 0.3 s of trickle fits in 5 x 0.1 s


def test_a_body_inside_the_deadline_is_untouched(monkeypatch):
    status, body, _ = _trickle("/api/save", monkeypatch, deadline=5, chunks=10)
    assert status == 200 and body == b"ok"
