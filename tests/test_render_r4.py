"""r4 render fixes: staged outputs, Manim dies with the backend, glued-path redaction,
render ids on every error, and saving through a workspace symlink."""
import asyncio
import json
import os
import signal
import subprocess
import sys
import textwrap
import time

import pytest

import main
import executor as executor_module
from executor import (
    STAGE_PREFIX,
    ManimExecutor,
    StagedOutputError,
    media_file_is_complete,
    parent_guard,
    promote_staged_outputs,
    redact_host_paths,
)
from tests.media_bytes import GIF, MP4, MP4_BROKEN, PNG, WEBM, write_media


def tagged(tag: bytes) -> bytes:
    """A complete MP4 that differs by *tag* (in a free box)."""
    return MP4 + (8 + len(tag)).to_bytes(4, "big") + b"free" + tag

STAGE = STAGE_PREFIX + "abcd1234"


# ---- 2. validity check -----------------------------------------------------------

@pytest.mark.parametrize("name, data, ok", [
    ("a.mp4", MP4, True), ("a.mp4", MP4_BROKEN, False), ("a.mov", MP4, True),
    ("a.png", PNG, True), ("a.png", PNG[:-12], False), ("a.gif", GIF, True), ("a.gif", GIF[:-1], False),
    ("a.webm", WEBM, True), ("a.webm", b"nope" * 30, False), ("a.mp4", b"", False),
])
def test_media_file_is_complete(tmp_path, name, data, ok):
    p = tmp_path / name
    p.write_bytes(data)
    assert media_file_is_complete(str(p)) is ok


def test_media_file_is_complete_rejects_links_and_missing(tmp_path):
    real = write_media(tmp_path / "real.mp4")
    (tmp_path / "link.mp4").symlink_to(real)
    assert not media_file_is_complete(str(tmp_path / "link.mp4"))
    assert not media_file_is_complete(str(tmp_path / "missing.mp4"))


# ---- 2. promotion ------------------------------------------------------------------

def test_promote_moves_every_staged_output_over_the_old_one(tmp_path):
    media = tmp_path / "media"
    old = write_media(media / "videos" / "demo" / "480p15" / "S.mp4", data=tagged(b"old"))
    write_media(media / "videos" / "demo" / STAGE / "480p15" / "S.mp4", data=tagged(b"new"))
    (media / "videos" / "demo" / STAGE / "480p15" / "S.srt").write_text("1")
    write_media(media / "images" / "demo" / STAGE / "S_ManimCE_v0.22.0.png")
    moved = promote_staged_outputs(str(media), "demo", STAGE)
    assert old.read_bytes() == tagged(b"new")
    assert (media / "videos" / "demo" / "480p15" / "S.srt").exists()
    assert (media / "images" / "demo" / "S_ManimCE_v0.22.0.png").exists()
    assert len(moved) == 3 and all(STAGE not in dst for dst in moved.values())


def test_promote_moves_nothing_when_an_output_is_broken(tmp_path):
    media = tmp_path / "media"
    old = write_media(media / "videos" / "demo" / "480p15" / "S.mp4", data=tagged(b"old"))
    write_media(media / "images" / "demo" / STAGE / "S_ManimCE_v0.22.0.png")
    write_media(media / "videos" / "demo" / STAGE / "480p15" / "S.mp4", data=MP4_BROKEN)
    with pytest.raises(StagedOutputError):
        promote_staged_outputs(str(media), "demo", STAGE)
    assert old.read_bytes() == tagged(b"old")
    assert not (media / "images" / "demo" / "S_ManimCE_v0.22.0.png").exists()


def test_promote_refuses_to_replace_a_read_only_render(tmp_path):
    media = tmp_path / "media"
    old = write_media(media / "videos" / "demo" / "480p15" / "S.mp4", data=tagged(b"old"))
    os.chmod(old, 0o444)
    write_media(media / "videos" / "demo" / STAGE / "480p15" / "S.mp4")
    try:
        with pytest.raises(OSError):
            promote_staged_outputs(str(media), "demo", STAGE)
        assert old.read_bytes() == tagged(b"old")
    finally:
        os.chmod(old, 0o644)


# ---- 2. the executor stages, validates, and announces the final path --------------

FAKE_MANIM = textwrap.dedent('''
    import os, sys, time
    mode = os.environ["FAKE_MODE"]; out = os.environ["FAKE_OUT"]
    os.makedirs(os.path.dirname(out), exist_ok=True)
    data = bytes.fromhex(os.environ["FAKE_BYTES"])
    if mode == "sleep":
        open(out, "wb").write(data[:20]); print("rendering", flush=True); time.sleep(30)
    open(out, "wb").write(data)
    print("INFO     File ready at '%s'" % out, flush=True)
    sys.exit(0 if mode in ("ok", "broken") else 1)
''')


def _run_fake(tmp_path, mode, data=MP4, stage=STAGE, cancel_after=None):
    ws = tmp_path / "ws"
    (ws / "media").mkdir(parents=True, exist_ok=True)
    (ws / "demo.py").write_text("x")
    fake = tmp_path / "fake_manim.py"
    fake.write_text(FAKE_MANIM)
    out = ws / "media" / "videos" / "demo" / (stage or "") / "480p15" / "S.mp4"
    env = {"FAKE_MODE": mode, "FAKE_OUT": str(out), "FAKE_BYTES": data.hex()}
    events = []

    async def cb(event):
        events.append(event)

    async def go():
        ex = ManimExecutor(str(ws))
        old_env = dict(os.environ)
        os.environ.update(env)
        try:
            task = asyncio.create_task(ex.execute([sys.executable, str(fake)], "demo.py", "S", "l", False, cb, stage=stage))
            if cancel_after is not None:
                await asyncio.sleep(cancel_after)
                await ex.cancel()
            return await task
        finally:
            os.environ.clear()
            os.environ.update(old_env)

    result = asyncio.run(go())
    return ws, result, events


def _final(ws):
    return ws / "media" / "videos" / "demo" / "480p15" / "S.mp4"


def _stages(ws):
    return [d for sub in ("videos", "images") for d in (ws / "media" / sub / "demo").glob(STAGE_PREFIX + "*")]


def test_successful_render_is_moved_into_place_and_announced_there(tmp_path):
    ws, result, events = _run_fake(tmp_path, "ok", data=tagged(b"new"))
    assert result["success"]
    ready = [e for e in events if e["type"] == "file_ready"]
    assert [e["rel_path"] for e in ready] == ["media/videos/demo/480p15/S.mp4"]
    assert _final(ws).read_bytes() == tagged(b"new")
    assert _stages(ws) == []


@pytest.mark.parametrize("mode, data", [("fail", MP4), ("broken", MP4_BROKEN)])
def test_failed_or_broken_render_keeps_the_previous_video(tmp_path, mode, data):
    write_media(_final(tmp_path / "ws"), data=tagged(b"old"))
    ws, result, events = _run_fake(tmp_path, mode, data=data)
    assert not result["success"]
    assert not [e for e in events if e["type"] == "file_ready"]
    assert _final(ws).read_bytes() == tagged(b"old")
    assert _stages(ws) == []
    if mode == "broken":
        assert any("previous render was kept" in e.get("message", "") for e in events if e["type"] == "error")


def test_cancelled_render_keeps_the_previous_video(tmp_path):
    write_media(_final(tmp_path / "ws"), data=tagged(b"old"))
    ws, result, events = _run_fake(tmp_path, "sleep", cancel_after=1.0)
    assert result["status"] == "cancelled"
    assert _final(ws).read_bytes() == tagged(b"old")
    assert _stages(ws) == []


def test_unstaged_runs_still_announce_directly(tmp_path):
    ws, result, events = _run_fake(tmp_path, "ok", stage=None)
    assert result["success"] and [e["rel_path"] for e in events if e["type"] == "file_ready"] == ["media/videos/demo/480p15/S.mp4"]


# ---- 2. renders listing and the sweep ----------------------------------------------

@pytest.fixture
def media_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "MEDIA_DIR", str(tmp_path / "media"))
    return tmp_path / "media"


def test_listing_skips_broken_files_and_staging_folders(media_dir):
    write_media(media_dir / "videos" / "demo" / "480p15" / "Good.mp4")
    write_media(media_dir / "videos" / "demo" / "480p15" / "Broken.mp4", data=MP4_BROKEN)
    write_media(media_dir / "images" / "demo" / "Cut_ManimCE_v0.22.0.png", data=PNG[:-12])
    write_media(media_dir / "videos" / "demo" / STAGE / "480p15" / "Good.mp4")
    write_media(media_dir / "images" / "demo" / STAGE / "Still_ManimCE_v0.22.0.png")
    assert [item["path"] for item in main._list_media()] == ["videos/demo/480p15/Good.mp4"]


def test_sweep_removes_only_old_staging_folders(media_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(main, "WORKSPACE_DIR", str(tmp_path))
    old = write_media(media_dir / "videos" / "demo" / (STAGE_PREFIX + "00000001") / "480p15" / "S.mp4", mtime=1000)
    os.utime(old.parent, (1000, 1000)); os.utime(old.parent.parent, (1000, 1000))
    fresh = write_media(media_dir / "videos" / "demo" / (STAGE_PREFIX + "00000002") / "480p15" / "S.mp4")
    live = write_media(media_dir / "images" / "demo" / (STAGE_PREFIX + "00000003") / "S.png", mtime=1000)
    os.utime(live.parent, (1000, 1000))
    monkeypatch.setattr(main, "_active_temp_stems", {main.TEMP_PREFIX + "00000003"})
    keep = write_media(media_dir / "videos" / "demo" / "480p15" / "S.mp4", mtime=1000)
    main._sweep_temp_renders(min_age=60)
    assert not old.parent.parent.exists()
    assert fresh.exists() and live.exists() and keep.exists()


def test_output_config_stages_outputs_but_not_the_cache():
    cfg = main._output_config("my 100%", STAGE)
    assert f"video_dir = {{media_dir}}/videos/my 100%%/{STAGE}/{{quality}}" in cfg
    assert f"images_dir = {{media_dir}}/images/my 100%%/{STAGE}" in cfg
    assert "partial_movie_dir = {media_dir}/videos/my 100%%/{quality}/partial_movie_files/{scene_name}" in cfg
    assert "partial_movie_dir" not in main._output_config("demo")


# ---- 3. Manim dies with the backend ------------------------------------------------

PARENT = textwrap.dedent('''
    import os, subprocess, sys, time
    sys.path.insert(0, sys.argv[1])
    os.environ["MANIM_PARENT_WATCH"] = sys.argv[2]
    os.environ["MANIM_PARENT_WATCH_POLL"] = "0.1"
    from executor import parent_guard
    cmd, preexec = parent_guard([sys.executable, "-c", "import time; print('child up', flush=True); time.sleep(60)"])
    child = subprocess.Popen(cmd, preexec_fn=preexec, start_new_session=True, stdout=subprocess.PIPE)
    child.stdout.readline()
    print(child.pid, flush=True)
    time.sleep(60)
''')


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A zombie that init has not reaped yet counts as gone.
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().split(")")[-1].split()[0] != "Z"
    except OSError:
        return True


def _pgroup_members(pgid):
    out = subprocess.run(["ps", "-o", "pid=,stat=", "-g", str(pgid)], capture_output=True, text=True).stdout
    return [line.split()[0] for line in out.splitlines() if line.split() and not line.split()[1].startswith("Z")]


@pytest.mark.skipif(os.name == "nt", reason="POSIX signals")
@pytest.mark.parametrize("mode", [
    pytest.param("pdeathsig", marks=pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux only")),
    "watcher",
])
def test_render_process_dies_when_the_backend_is_killed(tmp_path, mode):
    script = tmp_path / "parent.py"
    script.write_text(PARENT)
    backend_dir = os.path.dirname(executor_module.__file__)
    parent = subprocess.Popen([sys.executable, str(script), backend_dir, mode], stdout=subprocess.PIPE, text=True)
    child_pid = int(parent.stdout.readline())
    pgid = os.getpgid(child_pid)
    assert _alive(child_pid) and _pgroup_members(pgid)
    os.kill(parent.pid, signal.SIGKILL)
    parent.wait()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and _pgroup_members(pgid):
        time.sleep(0.05)
    assert _pgroup_members(pgid) == []  # Manim (and, with the watcher, the watcher too) is gone


def test_parent_guard_modes(monkeypatch):
    monkeypatch.setenv("MANIM_PARENT_WATCH", "off")
    assert parent_guard(["m"]) == (["m"], None)
    monkeypatch.setenv("MANIM_PARENT_WATCH", "watcher")
    cmd, preexec = parent_guard(["m", "x"])
    assert preexec is None and cmd[1].endswith("parent_watch.py") and cmd[2] == str(os.getpid()) and cmd[3:] == ["--", "m", "x"]
    if sys.platform.startswith("linux"):
        monkeypatch.setenv("MANIM_PARENT_WATCH", "auto")
        cmd, preexec = parent_guard(["m"])
        assert cmd == ["m"] and callable(preexec)


@pytest.mark.skipif(os.name == "nt", reason="POSIX signals")
def test_watcher_passes_exit_code_and_group_signals_still_work(tmp_path):
    watch = os.path.join(os.path.dirname(executor_module.__file__), "parent_watch.py")
    code = subprocess.run([sys.executable, watch, str(os.getpid()), "--", sys.executable, "-c", "raise SystemExit(3)"]).returncode
    assert code == 3
    p = subprocess.Popen([sys.executable, watch, str(os.getpid()), "--", sys.executable, "-c", "import time; time.sleep(60)"],
                         start_new_session=True)
    time.sleep(0.5)
    os.killpg(p.pid, signal.SIGTERM)  # what ManimExecutor.cancel() does
    assert p.wait(timeout=5) != 0
    assert _pgroup_members(p.pid) == []


# ---- 4. glued host paths -----------------------------------------------------------

@pytest.fixture
def deep_ws(tmp_path):
    ws = tmp_path / "proj" / "app" / "workspace"
    ws.mkdir(parents=True)
    return str(ws)


def test_path_glued_to_a_word_is_redacted(deep_ws):
    assert redact_host_paths(f"id{deep_ws}/scene.py", deep_ws) == f"id<workspace>{os.sep}scene.py"
    assert redact_host_paths(f"id{deep_ws}", deep_ws) == "id<workspace>"
    assert redact_host_paths(f"print: x_{deep_ws}/a", deep_ws) == f"print: x_<workspace>{os.sep}a"
    assert deep_ws not in redact_host_paths(f'"abc{deep_ws}/media/x.mp4"', deep_ws)


def test_glued_redaction_leaves_longer_paths_and_urls_alone(deep_ws):
    for text in (f"https://example.com{deep_ws}/x", f"src{deep_ws}x", f"build/sub{deep_ws}/y"):
        if text == f"src{deep_ws}x":
            assert redact_host_paths(text, deep_ws) == text  # the name goes on: not this path
            continue
        assert redact_host_paths(text, deep_ws) == text, text
    # Unchanged from before r4: a drive-style "C:" prefix is not a word glue.
    assert redact_host_paths(f"C:{deep_ws}", deep_ws) == "C:<workspace>"
    tmp = os.path.realpath(os.environ.get("TMPDIR", "/tmp"))
    # Short paths (fewer than three components) are never cut out of a word.
    assert redact_host_paths("data/tmp/cache and footmp", deep_ws) == "data/tmp/cache and footmp"
    assert redact_host_paths(f"word{tmp}", deep_ws) == f"word{tmp}" or len(tmp.strip("/").split("/")) >= 3


def test_unglued_redaction_is_unchanged(deep_ws):
    assert redact_host_paths(f"at {deep_ws}/scene.py:3", deep_ws) == "at scene.py:3"
    assert redact_host_paths(f"/srv{deep_ws}/x", deep_ws) == f"/srv{deep_ws}/x"


# ---- 5. render ids on errors -------------------------------------------------------

def test_invalid_json_error_carries_the_id_it_names(client):
    with client.websocket_connect("/api/render") as ws:
        ws.send_text('{"type": "start", "id": "r-9", "filename": ')
        assert ws.receive_json() == {"type": "error", "render_id": "r-9", "message": "Invalid JSON message."}
        ws.send_text("not json")
        assert ws.receive_json()["render_id"] is None
        ws.send_text("[1, 2]")
        event = ws.receive_json()
        assert event["type"] == "error" and "render_id" in event and event["render_id"] is None


def test_oversized_broken_json_still_gets_its_id_and_result(client, monkeypatch):
    monkeypatch.setattr(main, "MAX_REQUEST_BODY_BYTES", 200)
    with client.websocket_connect("/api/render") as ws:
        ws.send_text('{"type": "start", "id": 77, "code": "' + "x" * 400)
        error, result = ws.receive_json(), ws.receive_json()
        assert error["type"] == "error" and error["render_id"] == 77
        assert result == {"type": "result", "render_id": 77, "success": False, "status": "rejected"}


def test_sniffed_ids_are_cleaned():
    assert main._sniff_render_id('{"id": "a\\"b", x') == 'a"b'
    assert main._sniff_render_id('{"id": "' + "x" * (main.MAX_RENDER_ID_CHARS + 1) + '"') is None
    assert main._sniff_render_id('{"id": 12345678901234567890}') is None
    assert main._sniff_render_id("garbage") is None


def test_server_error_names_the_render_it_stopped(client, tmp_path, monkeypatch):
    monkeypatch.setattr(main, "WORKSPACE_DIR", str(tmp_path))
    (tmp_path / "snap.py").write_text("from manim import *\nclass Snap(Scene):\n    def construct(self):\n        self.wait()\n")

    gate = {}

    class Slow:
        """Like ManimExecutor: cancel() stops the run, which then returns "cancelled"."""

        def __init__(self, *a, **k):
            self.stop = None

        is_running = False

        async def execute(self, *a, log_callback=None, **k):
            self.stop = asyncio.Event()
            gate["started"] = True
            await self.stop.wait()
            return {"success": False, "status": "cancelled"}

        async def cancel(self):
            if self.stop is not None:
                self.stop.set()

    real_loads = json.loads

    def flaky_loads(data, *a, **k):
        if isinstance(data, str) and '"boom"' in data:
            raise RuntimeError("socket broke")
        return real_loads(data, *a, **k)

    monkeypatch.setattr(main, "ManimExecutor", Slow)
    monkeypatch.setattr(main, "_manim_command", lambda paths: ["manim"])
    with client.websocket_connect("/api/render") as ws:
        ws.send_json({"type": "start", "id": "live", "filename": "snap.py", "scene": "Snap", "quality": "l"})
        deadline = time.monotonic() + 5
        while not gate.get("started") and time.monotonic() < deadline:
            time.sleep(0.02)
        monkeypatch.setattr(main.json, "loads", flaky_loads)
        ws.send_text('{"type": "boom"}')
        events = []
        while True:
            event = ws.receive_json()
            events.append(event)
            if event["type"] == "error" and "Server WebSocket error" in event.get("message", ""):
                break
    assert events[-1]["render_id"] == "live", events
    assert [e for e in events if e["type"] == "result"] == [
        {"type": "result", "render_id": "live", "success": False, "status": "cancelled", "details": {"success": False, "status": "cancelled"}}
    ]


# ---- extra: saving through a symlink -------------------------------------------------

@pytest.fixture
def ws_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "WORKSPACE_DIR", str(tmp_path))
    return tmp_path


def test_save_through_a_workspace_symlink_updates_the_target_and_keeps_the_link(client, ws_dir):
    (ws_dir / "lib").mkdir()
    target = ws_dir / "lib" / "real.py"
    target.write_text("old = 1\n")
    (ws_dir / "alias.py").symlink_to(target)
    res = client.post("/api/save", json={"filename": "alias.py", "code": "new = 2\n"})
    assert res.status_code == 200, res.text
    assert os.path.islink(ws_dir / "alias.py")
    assert target.read_text() == "new = 2\n"
    loaded = client.get("/api/file-content", params={"filename": "alias.py"}).json()
    assert loaded["code"] == "new = 2\n" and loaded["version"] == res.json()["version"]
    again = client.post("/api/save", json={"filename": "alias.py", "code": "x = 3\n", "base_version": res.json()["version"]})
    assert again.status_code == 200 and target.read_text() == "x = 3\n" and os.path.islink(ws_dir / "alias.py")


def test_save_refuses_links_that_leave_the_workspace_or_dangle(client, ws_dir, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "evil.py"
    outside.write_text("keep\n")
    (ws_dir / "out.py").symlink_to(outside)
    (ws_dir / "dangling.py").symlink_to(ws_dir / "nothing.py")
    for name in ("out.py", "dangling.py"):
        res = client.post("/api/save", json={"filename": name, "code": "x\n"})
        assert res.status_code in (400, 403, 404), (name, res.status_code)
        assert os.path.islink(ws_dir / name)
    assert outside.read_text() == "keep\n"
    assert not (ws_dir / "nothing.py").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX signals")
def test_parent_watch_main_in_process(monkeypatch):
    import parent_watch

    saved = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        assert parent_watch.main(["pw"]) == 2
        assert parent_watch.main(["pw", str(os.getppid() + 999999), "--", "true"]) == 1  # parent already gone
        code = parent_watch.main(["pw", str(os.getppid()), "--", sys.executable, "-c", "raise SystemExit(3)"])
        assert code == 3
        killed = []
        monkeypatch.setattr(parent_watch, "POLL_SECONDS", 0.05)
        alive = iter([True, False])
        monkeypatch.setattr(parent_watch, "_parent_alive", lambda pid, started: next(alive, False))
        monkeypatch.setattr(parent_watch, "_kill", lambda child: (killed.append(child.pid), child.kill()))
        assert parent_watch.main(["pw", "1", "--", sys.executable, "-c", "import time; time.sleep(30)"]) == 137
        assert killed
    finally:
        for sig, handler in saved.items():
            signal.signal(sig, handler)
