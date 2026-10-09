"""Render socket round 3: snapshot at enqueue, disk size cap, per-run config, queue, ids, surrogates."""

import asyncio
import json
import time
from unittest.mock import patch

import pytest

import main

MOCK_BINARIES = {"manim": "/usr/bin/manim", "manim_command": ["/usr/bin/manim"]}
GOOD = "from manim import *\nclass Snap(Scene):\n    def construct(self):\n        pass\n"
CHANGED = "from manim import *\nclass Other(Scene):\n    def construct(self):\n        pass\n"


class Recorder:
    """Executor stand-in: records what Manim would have read, then waits for release()."""

    instances = []

    def __init__(self, workspace_dir, *args, **kwargs):
        self.workspace_dir = workspace_dir
        self.runs = []
        self.gate = None
        self.loop = None
        Recorder.instances.append(self)

    async def execute(self, manim_path, script_name, scene_name, quality, use_opengl, log_callback, output_stem=None, extra_args=None):
        import os

        with open(os.path.join(self.workspace_dir, script_name), encoding="utf-8") as f:
            code = f.read()
        config = None
        if extra_args:
            with open(os.path.join(self.workspace_dir, extra_args[1]), encoding="utf-8") as f:
                config = f.read()
        self.runs.append({"script": script_name, "code": code, "output_stem": output_stem, "extra_args": extra_args, "config": config})
        self.loop = asyncio.get_running_loop()
        self.gate = asyncio.Event()
        await log_callback({"type": "info", "message": f"$ manim {script_name} {scene_name}"})
        await self.gate.wait()
        return {"success": True, "status": "success"}

    async def cancel(self):
        if self.gate is not None:
            self.gate.set()

    def release(self):
        deadline = time.time() + 5
        while self.gate is None or self.gate.is_set():
            if time.time() > deadline:
                raise AssertionError("not rendering")
            time.sleep(0.005)
        self.loop.call_soon_threadsafe(self.gate.set)


@pytest.fixture
def ws_render(tmp_path, monkeypatch):
    Recorder.instances = []
    (tmp_path / "media").mkdir()
    monkeypatch.setattr(main, "_render_slots", None)
    monkeypatch.setattr(main, "_render_waiters", [])
    with patch.object(main, "ManimExecutor", Recorder), patch.object(main, "WORKSPACE_DIR", str(tmp_path)), patch.object(
        main, "MEDIA_DIR", str(tmp_path / "media")
    ), patch.object(main, "get_binary_paths", return_value=MOCK_BINARIES):
        yield tmp_path


def start(render_id, filename="snap.py", scene="Snap", **extra):
    return {"type": "start", "id": render_id, "filename": filename, "scene": scene, "quality": "l", **extra}


def until(ws, predicate, limit=60):
    seen = []
    for _ in range(limit):
        message = ws.receive_json()
        seen.append(message)
        if predicate(message):
            return seen
    pytest.fail(f"never matched: {seen}")


def result_of(render_id):
    return lambda m: m.get("type") == "result" and m.get("render_id") == render_id


def test_queued_render_uses_the_code_checked_at_enqueue(client, ws_render):
    """r2 (PSD #4): the file changed while the render waited, and Manim rendered the new file."""
    (ws_render / "busy.py").write_text(GOOD.replace("Snap", "Busy"))
    (ws_render / "snap.py").write_text(GOOD)
    with client.websocket_connect("/api/render") as first, client.websocket_connect("/api/render") as second:
        first.send_json(start("a", filename="busy.py", scene="Busy"))
        until(first, lambda m: m.get("message", "").startswith("$ manim"))
        second.send_json(start("b"))
        until(second, lambda m: m.get("type") == "queued")
        (ws_render / "snap.py").write_text(CHANGED)  # Snap is gone from the file now
        Recorder.instances[0].release()
        until(first, result_of("a"))
        until(second, lambda m: m.get("message", "").startswith("$ manim"))
        Recorder.instances[1].release()
        received = until(second, result_of("b"))
    run = Recorder.instances[1].runs[0]
    assert run["code"] == GOOD  # the snapshot, not the changed file
    assert run["script"].startswith(main.TEMP_PREFIX)
    assert received[-1]["status"] == "success"
    # The scratch copy and its config are gone afterwards.
    assert [p.name for p in ws_render.iterdir() if p.name.startswith(main.TEMP_PREFIX)] == []


def test_saved_render_writes_into_the_scripts_own_media_folder(client, ws_render):
    (ws_render / "snap.py").write_text(GOOD)
    with client.websocket_connect("/api/render") as ws:
        ws.send_json(start("c"))
        until(ws, lambda m: m.get("message", "").startswith("$ manim"))
        Recorder.instances[0].release()
        until(ws, result_of("c"))
    run = Recorder.instances[0].runs[0]
    assert run["output_stem"] == "snap"
    assert run["extra_args"][0] == "--config_file" and run["extra_args"][1].endswith(".cfg")
    assert "video_dir = {media_dir}/videos/snap/{quality}" in run["config"]
    assert "images_dir = {media_dir}/images/snap" in run["config"]


def test_percent_in_a_name_is_escaped_for_the_config(client, ws_render):
    (ws_render / "100%.py").write_text(GOOD)
    with client.websocket_connect("/api/render") as ws:
        ws.send_json(start("p", filename="100%.py"))
        until(ws, lambda m: m.get("message", "").startswith("$ manim"))
        Recorder.instances[0].release()
        until(ws, result_of("p"))
    assert "videos/100%%/{quality}" in Recorder.instances[0].runs[0]["config"]


def test_command_echo_shows_the_users_file_name(client, ws_render):
    (ws_render / "snap.py").write_text(GOOD)
    with client.websocket_connect("/api/render") as ws:
        ws.send_json(start("e"))
        echo = until(ws, lambda m: m.get("message", "").startswith("$ manim"))[-1]
        Recorder.instances[0].release()
        until(ws, result_of("e"))
    assert echo["message"].startswith("$ manim snap.py") and main.TEMP_PREFIX not in echo["message"]


def test_oversized_script_on_disk_is_not_rendered(client, ws_render, monkeypatch):
    """r2 (2PSD #2): a 2.16 MB file rendered via Ctrl+Enter because only sent code was capped."""
    monkeypatch.setattr(main, "MAX_CODE_BYTES", 1000)
    (ws_render / "snap.py").write_text(GOOD + "#" + "x" * 2000 + "\n")
    with client.websocket_connect("/api/render") as ws:
        ws.send_json(start("big"))
        received = until(ws, result_of("big"))
    assert received[0]["type"] == "error" and "larger than 1000 bytes" in received[0]["message"]
    assert received[-1]["status"] == "rejected" and received[-1]["details"]["reason"] == "too_large"
    assert Recorder.instances[0].runs == []


class FakeSocket:
    """A render socket driven from one event loop, like uvicorn serves every client.

    (TestClient runs each websocket on its own loop, and one asyncio semaphore
    can't be woken across loops, so multi-client queue tests use this.)
    """

    def __init__(self):
        self.headers = {"host": "localhost"}
        self.client = None
        self.incoming = asyncio.Queue()
        self.sent = []
        self.changed = asyncio.Event()

    async def accept(self):
        pass

    async def close(self, code=1000):
        pass

    async def receive_text(self):
        item = await self.incoming.get()
        if item is None:
            from starlette.websockets import WebSocketDisconnect

            raise WebSocketDisconnect()
        return json.dumps(item)

    async def send_text(self, text):
        self.sent.append(json.loads(text))
        self.changed.set()

    async def wait_for(self, predicate, timeout=5):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            for message in self.sent:
                if predicate(message):
                    return message
            self.changed.clear()
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise AssertionError(f"never matched: {self.sent}")
            try:
                await asyncio.wait_for(self.changed.wait(), remaining)
            except asyncio.TimeoutError:
                pass

    def positions(self):
        return [m["position"] for m in self.sent if m.get("type") == "queued"]


class LoopRecorder(Recorder):
    def release(self):  # same loop: no thread hop
        self.gate.set()


def _started(m):
    return m.get("message", "").startswith("$ manim")


async def _sockets(count):
    sockets = [FakeSocket() for _ in range(count)]
    tasks = [asyncio.create_task(main.websocket_render(s)) for s in sockets]
    return sockets, tasks


async def _close(sockets, tasks):
    for s in sockets:
        s.incoming.put_nowait(None)
    await asyncio.wait_for(asyncio.gather(*tasks), 10)


async def _until_rendering(index):
    for _ in range(500):
        if len(Recorder.instances) > index:
            executor = Recorder.instances[index]
            if executor.gate is not None and not executor.gate.is_set():
                return executor
        await asyncio.sleep(0.01)
    raise AssertionError("render did not start")


@pytest.fixture
def loop_render(ws_render):
    with patch.object(main, "ManimExecutor", LoopRecorder):
        yield ws_render


def test_queue_positions_are_resent_as_the_queue_moves(loop_render):
    """r2 (2PSD #9): the position was sent once and never updated."""
    (loop_render / "snap.py").write_text(GOOD)

    async def run():
        sockets, tasks = await _sockets(4)
        sockets[0].incoming.put_nowait(start("r0"))
        await sockets[0].wait_for(_started)
        for i in (1, 2, 3):
            sockets[i].incoming.put_nowait(start(f"r{i}"))
            await sockets[i].wait_for(lambda m: m.get("type") == "queued")
        for i in range(4):
            (await _until_rendering(i)).release()
            await sockets[i].wait_for(result_of(f"r{i}"))
        await _close(sockets, tasks)
        return [s.positions() for s in sockets]

    assert asyncio.run(run()) == [[], [1], [2, 1], [3, 2, 1]]


def test_cancelled_waiter_moves_the_queue_up(loop_render):
    (loop_render / "snap.py").write_text(GOOD)

    async def run():
        (a, b, c), tasks = await _sockets(3)
        a.incoming.put_nowait(start("a"))
        await a.wait_for(_started)
        b.incoming.put_nowait(start("b"))
        await b.wait_for(lambda m: m.get("type") == "queued")
        c.incoming.put_nowait(start("c"))
        await c.wait_for(lambda m: m.get("type") == "queued")
        b.incoming.put_nowait({"type": "cancel"})
        cancelled = await b.wait_for(result_of("b"))
        await c.wait_for(lambda m: m.get("type") == "queued" and m["position"] == 1)
        (await _until_rendering(0)).release()
        await a.wait_for(result_of("a"))
        (await _until_rendering(2)).release()
        done = await c.wait_for(result_of("c"))
        await _close([a, b, c], tasks)
        return cancelled, done, c.positions()

    cancelled, done, positions = asyncio.run(run())
    assert cancelled["status"] == "cancelled" and done["status"] == "success"
    assert positions == [2, 1]


def test_queue_cap_rejects_with_a_clear_result(loop_render, monkeypatch):
    monkeypatch.setattr(main, "MAX_QUEUED_RENDERS", 1)
    (loop_render / "snap.py").write_text(GOOD)

    async def run():
        (a, b, c), tasks = await _sockets(3)
        a.incoming.put_nowait(start("a"))
        await a.wait_for(_started)
        b.incoming.put_nowait(start("b"))
        await b.wait_for(lambda m: m.get("type") == "queued")
        c.incoming.put_nowait(start("c"))
        rejected = await c.wait_for(result_of("c"))
        error = next(m for m in c.sent if m.get("type") == "error")
        (await _until_rendering(0)).release()
        await a.wait_for(result_of("a"))
        (await _until_rendering(1)).release()
        await b.wait_for(result_of("b"))
        await _close([a, b, c], tasks)
        return rejected, error

    rejected, error = asyncio.run(run())
    assert "queue is full (1 waiting)" in error["message"]
    assert rejected["status"] == "rejected" and rejected["details"]["reason"] == "queue_full"
    # The rejected render left no scratch files behind.
    assert [p.name for p in loop_render.iterdir() if p.name.startswith(main.TEMP_PREFIX)] == []


def test_queued_render_uses_the_snapshot_with_one_loop(loop_render):
    """Snapshot at enqueue, with both clients on one loop as in production."""
    (loop_render / "busy.py").write_text(GOOD.replace("Snap", "Busy"))
    (loop_render / "snap.py").write_text(GOOD)

    async def run():
        (a, b), tasks = await _sockets(2)
        a.incoming.put_nowait(start("a", filename="busy.py", scene="Busy"))
        await a.wait_for(_started)
        b.incoming.put_nowait(start("b"))
        await b.wait_for(lambda m: m.get("type") == "queued")
        (loop_render / "snap.py").write_text(CHANGED)
        (await _until_rendering(0)).release()
        await a.wait_for(result_of("a"))
        (await _until_rendering(1)).release()
        done = await b.wait_for(result_of("b"))
        await _close([a, b], tasks)
        return done

    assert asyncio.run(run())["status"] == "success"
    assert Recorder.instances[1].runs[0]["code"] == GOOD


@pytest.mark.parametrize("bad_id", ["i" * 129, ["list"], {"a": 1}, True, 10**19])
def test_bad_render_ids_are_refused_not_echoed(client, ws_render, bad_id):
    (ws_render / "snap.py").write_text(GOOD)
    with client.websocket_connect("/api/render") as ws:
        ws.send_json(start(bad_id))
        error, result = ws.receive_json(), ws.receive_json()
    assert error["type"] == "error" and error["render_id"] is None and "Render id" in error["message"]
    assert result == {"type": "result", "render_id": None, "success": False, "status": "rejected"}


@pytest.mark.parametrize("good_id", ["i" * 128, 7, 2.5, None])
def test_normal_render_ids_still_work(client, ws_render, good_id):
    (ws_render / "snap.py").write_text(GOOD)
    with client.websocket_connect("/api/render") as ws:
        ws.send_json(start(good_id))
        until(ws, lambda m: m.get("message", "").startswith("$ manim"))
        Recorder.instances[0].release()
        received = until(ws, lambda m: m.get("type") == "result")
    assert received[-1]["render_id"] == good_id and received[-1]["status"] == "success"


def test_cancel_with_a_huge_id_is_not_echoed(client, ws_render):
    (ws_render / "snap.py").write_text(GOOD)
    with client.websocket_connect("/api/render") as ws:
        ws.send_json(start("x"))
        until(ws, lambda m: m.get("message", "").startswith("$ manim"))
        ws.send_json({"type": "cancel", "id": "z" * 100_000})
        info = until(ws, lambda m: m.get("message") == "That render is not running.")[-1]
        assert info["render_id"] is None
        Recorder.instances[0].release()
        until(ws, result_of("x"))


def test_lone_surrogate_in_ws_code_is_an_error_event(client, ws_render):
    with client.websocket_connect("/api/render") as ws:
        ws.send_text('{"type":"start","id":"s","filename":"a.py","scene":"A","code":"x = \\"\\udc80\\""}')
        error, result = ws.receive_json(), ws.receive_json()
        assert error["type"] == "error" and "unpaired surrogate" in error["message"]
        assert result["status"] == "rejected" and result["render_id"] == "s"
        # The socket is still usable.
        ws.send_text('{"type":"start","id":"t","filename":"a\\udc80.py","scene":"A","code":"x=1"}')
        error, result = ws.receive_json(), ws.receive_json()
        assert "unpaired surrogate" in error["message"] and result["status"] == "rejected"
        ws.send_text('{"type":"start","id":"\\ud800","filename":"a.py","scene":"A","code":"x=1"}')
        error, result = ws.receive_json(), ws.receive_json()
        assert "Render id" in error["message"] and result["render_id"] is None


def test_lone_surrogate_from_manim_output_is_still_sent(client, ws_render):
    """A log line with an unpaired surrogate is escaped instead of killing the socket."""

    class Noisy(Recorder):
        async def execute(self, manim_path, script_name, scene_name, quality, use_opengl, log_callback, **kw):
            await log_callback({"type": "log", "stream": "stdout", "message": "bad \udc80 byte"})
            return {"success": False, "status": "failed"}

    (ws_render / "snap.py").write_text(GOOD)
    with patch.object(main, "ManimExecutor", Noisy):
        with client.websocket_connect("/api/render") as ws:
            ws.send_json(start("n"))
            received = until(ws, result_of("n"))
    log = next(m for m in received if m["type"] == "log")
    assert log["message"] == "bad \udc80 byte"


def test_oversized_ws_message_gets_error_and_rejected_result(client, ws_render, monkeypatch):
    monkeypatch.setattr(main, "MAX_REQUEST_BODY_BYTES", 1000)
    with client.websocket_connect("/api/render") as ws:
        ws.send_text(json.dumps(start("huge", code="#" + "x" * 5000)))
        error, result = ws.receive_json(), ws.receive_json()
    assert error["render_id"] == "huge" and "exceeds maximum size" in error["message"]
    assert result["status"] == "rejected"


def test_uvicorn_ws_limit_is_above_the_app_cap():
    """Messages between the app cap and the protocol limit get a result, not a bare 1009 close."""
    assert main.ws_max_message_bytes() >= 2 * main.MAX_REQUEST_BODY_BYTES
    assert main.ws_max_message_bytes() > 17 * 1024 * 1024


def test_config_safe_stems():
    assert main._config_safe_stem("scene")
    assert main._config_safe_stem("my scene-1")
    assert not main._config_safe_stem("a{b}")
    assert not main._config_safe_stem("trailing ")
    assert main._output_config("50%").count("50%%") == 2


def test_announce_is_safe_with_no_listener(monkeypatch):
    state = main._RenderState("x")
    monkeypatch.setattr(main, "_render_waiters", [state])
    main._announce_queue_positions()  # no notify set: nothing happens
    assert state.position == 0
