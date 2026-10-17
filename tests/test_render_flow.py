"""Render socket: queueing, cancel at every phase, superseded starts, and one result per start."""

import json
import asyncio
import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import main

MOCK_BINARIES = {"manim": "/usr/bin/manim", "manim_command": ["/usr/bin/manim"]}
SCENE = "class S(Scene):\n    pass\n"


@pytest.fixture(autouse=True)
def fresh_render_slots(monkeypatch):
    # The semaphore binds to the event loop of its first waiter; each test gets its own.
    monkeypatch.setattr(main, "_render_slots", None)
    monkeypatch.setattr(main, "_render_waiters", [])
    with patch.object(main, "get_binary_paths", return_value=MOCK_BINARIES):
        yield


class FakeExecutor:
    """Stands in for ManimExecutor: a render runs until release() or cancel()."""

    instances = []

    def __init__(self, *args, **kwargs):
        self.started = threading.Event()
        self.calls = []
        self.cancels = 0
        self._loop = None
        self._stop = None
        self._running = False
        self._outcome = None
        FakeExecutor.instances.append(self)

    async def execute(self, manim_path, script_name, scene_name, quality, use_opengl, log_callback, **_kwargs):
        self.calls.append(scene_name)
        self._loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        self._outcome = {"success": False, "status": "cancelled"}
        self._running = True
        try:
            await log_callback({"type": "info", "message": f"$ manim {script_name} {scene_name}"})
            self.started.set()
            await self._stop.wait()
            return self._outcome
        finally:
            self._running = False

    async def cancel(self):
        self.cancels += 1
        if self._stop is not None:
            self._outcome = {"success": False, "status": "cancelled"}
            self._stop.set()

    def release(self):
        """Let the render that is running now finish successfully (called from the test thread).

        Waits until a render is inside execute() and not already stopped, so a render
        that is still queued or starting up is not skipped.
        """
        deadline = time.time() + 5
        while not (self._running and self._stop is not None and not self._stop.is_set()):
            if time.time() > deadline:
                raise AssertionError("no render is running")
            time.sleep(0.005)

        def finish():
            self._outcome = {"success": True, "status": "success"}
            self._stop.set()

        self._loop.call_soon_threadsafe(finish)


@pytest.fixture
def fake_executor(tmp_path):
    FakeExecutor.instances = []
    (tmp_path / "media").mkdir()
    (tmp_path / "s.py").write_text(SCENE)
    with patch.object(main, "ManimExecutor", FakeExecutor), patch.object(
        main, "WORKSPACE_DIR", str(tmp_path)
    ), patch.object(main, "MEDIA_DIR", str(tmp_path / "media")):
        yield FakeExecutor


def start(render_id, **extra):
    return {"type": "start", "id": render_id, "filename": "s.py", "scene": "S", "quality": "l", **extra}


def drain(ws, render_id, limit=50):
    received = []
    for _ in range(limit):
        message = ws.receive_json()
        received.append(message)
        if message.get("type") == "result" and message.get("render_id") == render_id:
            return received
    pytest.fail(f"no result for {render_id}: {received}")


def test_cancel_right_after_start_reports_cancelled(client, fake_executor):
    """start + cancel back to back: the cancel lands before or just after Manim starts."""
    with client.websocket_connect("/api/render") as ws:
        ws.send_json(start("a"))
        ws.send_json({"type": "cancel"})
        received = drain(ws, "a")
    assert {"type": "info", "render_id": "a", "message": "Stopping render..."} in received
    assert received[-1]["status"] == "cancelled" and received[-1]["success"] is False
    assert [m for m in received if m["type"] == "result"] == [received[-1]]


def test_cancel_while_rendering_stops_manim_and_echoes_the_id(client, fake_executor):
    with client.websocket_connect("/api/render") as ws:
        ws.send_json(start("r"))
        assert ws.receive_json()["message"].startswith("$ manim")
        ws.send_json({"type": "cancel", "id": "r"})
        received = drain(ws, "r")
    assert received[0] == {"type": "info", "render_id": "r", "message": "Stopping render..."}
    assert received[-1]["status"] == "cancelled"
    assert fake_executor.instances[0].cancels >= 1


def test_cancel_for_another_render_id_does_not_stop_this_one(client, fake_executor):
    with client.websocket_connect("/api/render") as ws:
        ws.send_json(start("live"))
        ws.receive_json()  # "$ manim" line: it is rendering
        ws.send_json({"type": "cancel", "id": "old"})
        assert ws.receive_json() == {"type": "info", "render_id": "old", "message": "That render is not running."}
        fake_executor.instances[0].release()
        received = drain(ws, "live")
    assert received[-1]["status"] == "success"
    assert fake_executor.instances[0].cancels == 0


def test_cancel_with_nothing_running_is_silent(client, fake_executor):
    with client.websocket_connect("/api/render") as ws:
        ws.send_json({"type": "cancel"})
        ws.send_json(start("after"))
        ws.receive_json()
        fake_executor.instances[0].release()
        received = drain(ws, "after")
    assert received[-1]["status"] == "success"


def test_queued_render_reports_position_and_can_be_cancelled(client, fake_executor):
    with client:  # one event loop for both sockets, like a real server
        with client.websocket_connect("/api/render") as first, client.websocket_connect("/api/render") as second:
            first.send_json(start("one"))
            assert first.receive_json()["message"].startswith("$ manim")

            second.send_json(start("two"))
            queued, legacy = second.receive_json(), second.receive_json()
            assert queued["type"] == "queued" and queued["render_id"] == "two" and queued["position"] == 1
            assert "Waiting for another render" in queued["message"]
            assert legacy == {"type": "info", "render_id": "two", "message": queued["message"]}

            second.send_json({"type": "cancel"})
            received = drain(second, "two")
            assert [m["type"] for m in received] == ["info", "result"]
            assert received[-1]["status"] == "cancelled"
            assert main._render_waiters == []

            fake_executor.instances[0].release()
            assert drain(first, "one")[-1]["status"] == "success"

            # Nothing more is ever sent for the cancelled render: the next events on
            # that socket belong to the next render only.
            second.send_json(start("three"))
            assert second.receive_json()["message"].startswith("$ manim")
            fake_executor.instances[1].release()
            after = drain(second, "three")
            assert all(m.get("render_id") == "three" for m in after)
    # The cancelled render never reached Manim.
    assert [len(ex.calls) for ex in fake_executor.instances] == [1, 1]


def test_queued_render_starts_when_the_slot_frees(client, fake_executor):
    with client:
        with client.websocket_connect("/api/render") as first, client.websocket_connect("/api/render") as second:
            first.send_json(start("one"))
            first.receive_json()
            second.send_json(start("two"))
            assert second.receive_json()["type"] == "queued"
            second.receive_json()  # legacy info line

            fake_executor.instances[0].release()
            assert drain(first, "one")[-1]["status"] == "success"

            started = second.receive_json()
            assert started == {"type": "started", "render_id": "two", "waited": True}
            assert second.receive_json()["message"].startswith("$ manim")
            fake_executor.instances[1].release()
            assert drain(second, "two")[-1]["status"] == "success"


def test_queue_positions_count_waiters_in_order():
    a, b = main._RenderState("a"), main._RenderState("b")
    main._render_waiters.extend([a, b])
    try:
        assert main._queue_position(a) == 1 and main._queue_position(b) == 2
        assert main._queue_position(main._RenderState("c")) == 0
    finally:
        main._render_waiters.clear()


def test_every_superseded_start_gets_a_result(client, fake_executor):
    ids = [f"s{i}" for i in range(8)]
    with client.websocket_connect("/api/render") as ws:
        for render_id in ids:
            ws.send_json(start(render_id))
        results = {}
        deadline = time.time() + 10
        while len(results) < len(ids) - 1 and time.time() < deadline:
            message = ws.receive_json()
            if message["type"] == "result":
                results[message["render_id"]] = message
        deadline = time.time() + 10
        while not any(ex.calls for ex in fake_executor.instances) and time.time() < deadline:
            time.sleep(0.01)  # the last start is still taking its snapshot
        last = next(ex for ex in reversed(fake_executor.instances) if ex.calls)
        last.release()
        while ids[-1] not in results:
            message = ws.receive_json()
            if message["type"] == "result":
                results[message["render_id"]] = message
    assert sorted(results) == sorted(ids)
    assert all(results[i]["status"] == "cancelled" for i in ids[:-1])
    assert results[ids[-1]]["status"] == "success"


def test_disconnect_stops_a_running_render(client, fake_executor):
    with client.websocket_connect("/api/render") as ws:
        ws.send_json(start("gone"))
        ws.receive_json()
    executor = fake_executor.instances[0]
    for _ in range(50):
        if executor.cancels:
            break
        time.sleep(0.02)
    assert executor.cancels >= 1


def test_stuck_render_is_cancelled_after_the_grace_period(client, fake_executor, monkeypatch):
    monkeypatch.setattr(main, "STOP_GRACE_SECONDS", 0.05)

    async def ignore_cancel(self):
        self.cancels += 1  # Manim refuses to die

    monkeypatch.setattr(FakeExecutor, "cancel", ignore_cancel)
    with client.websocket_connect("/api/render") as ws:
        ws.send_json(start("stuck"))
        ws.receive_json()
        ws.send_json({"type": "cancel"})
        received = drain(ws, "stuck")
    assert received[-1]["status"] == "cancelled"


def test_oversized_messages_are_rejected_with_their_id(client, monkeypatch):
    monkeypatch.setattr(main, "MAX_REQUEST_BODY_BYTES", 100)
    with client.websocket_connect("/api/render") as ws:
        ws.send_json(start("big", code="#" * 9000))
        error, result = ws.receive_json(), ws.receive_json()
        assert error["type"] == "error" and error["render_id"] == "big"
        assert "exceeds maximum size" in error["message"]
        assert result == {"type": "result", "render_id": "big", "success": False, "status": "rejected"}

        ws.send_text("x" * 9000)  # not JSON: an error, and no result to wait for
        error = ws.receive_json()
        assert error["type"] == "error" and error["render_id"] is None

        ws.send_json({"type": "cancel", "pad": "#" * 9000})
        assert ws.receive_json()["render_id"] is None


def test_render_rejected_by_the_scene_check_reports_rejected(client, fake_executor):
    with client.websocket_connect("/api/render") as ws:
        ws.send_json(start("nope", scene="Missing"))
        received = drain(ws, "nope")
    assert received[0]["type"] == "error" and "Missing" in received[0]["message"]
    assert received[-1]["status"] == "rejected"


def test_missing_saved_script_is_rejected(client, fake_executor):
    with client.websocket_connect("/api/render") as ws:
        ws.send_json(start("gone", filename="nothere.py"))
        received = drain(ws, "gone")
    assert received[0]["message"] == "Python script not found."
    assert received[-1]["status"] == "rejected"


def test_send_failure_cancels_the_render():
    """A client that vanished mid-render gets its Manim process stopped."""
    executor = MagicMock()
    executor.cancel = AsyncMock()

    async def execute(manim_path, script_name, scene_name, quality, use_opengl, log_callback, **_kwargs):
        await log_callback({"type": "log", "message": "hello"})
        return {"success": False, "status": "cancelled"}

    executor.execute = AsyncMock(side_effect=execute)
    websocket = MagicMock()
    websocket.headers = {"host": "localhost"}
    websocket.client = None
    websocket.accept = AsyncMock()
    messages = [
        '{"type": "start", "id": "x", "filename": "s.py", "scene": "S", "code": "class S(Scene):\\n    pass\\n"}'
    ]

    async def receive_text():
        if messages:
            return messages.pop()
        await asyncio.sleep(0.2)
        from starlette.websockets import WebSocketDisconnect

        raise WebSocketDisconnect()

    websocket.receive_text = receive_text
    websocket.send_text = AsyncMock(side_effect=RuntimeError("closed"))
    with patch.object(main, "ManimExecutor", return_value=executor):
        asyncio.run(main.websocket_render(websocket))
    assert executor.cancel.await_count >= 1


def test_unexpected_socket_error_stops_the_render_and_reports(monkeypatch):
    websocket = MagicMock()
    websocket.headers = {"host": "localhost"}
    websocket.client = None
    websocket.accept = AsyncMock()
    websocket.receive_text = AsyncMock(side_effect=KeyError("boom"))
    websocket.send_text = AsyncMock()
    asyncio.run(main.websocket_render(websocket))
    sent = json.loads(websocket.send_text.await_args.args[0])
    assert sent["type"] == "error" and "Server WebSocket error" in sent["message"]


def test_scratch_name_swap_keeps_traceback_box_width(client, tmp_path):
    """Swapping _temp_run_xxxxxxxx.py for the user's shorter name keeps Rich's right border aligned."""
    (tmp_path / "media").mkdir()

    async def execute(manim_path, script_name, scene_name, quality, use_opengl, log_callback, **_kwargs):
        await log_callback({"type": "log", "message": f"│ {script_name}:5 in construct" + " " * 8 + "│"})
        return {"success": False, "status": "failed"}

    instance = MagicMock()
    instance.execute = AsyncMock(side_effect=execute)
    instance.cancel = AsyncMock()
    with patch.object(main, "WORKSPACE_DIR", str(tmp_path)), patch.object(
        main, "MEDIA_DIR", str(tmp_path / "media")
    ), patch.object(main, "ManimExecutor", return_value=instance):
        with client.websocket_connect("/api/render") as ws:
            ws.send_json(start("box", filename="ne.py", code=SCENE))
            received = drain(ws, "box")
    line = next(m["message"] for m in received if m["type"] == "log")
    assert line.startswith("│ ne.py:5 in construct") and line.endswith("│")
    assert len(line) == len("│ _temp_run_12345678.py:5 in construct" + " " * 8 + "│")
