"""End-to-end renders through the WebSocket with a real Manim install.

Skipped when Manim is not available (CI installs only the API dependencies).
"""

import time
from unittest.mock import patch

import pytest

import main
from diagnostics import get_binary_paths

pytestmark = pytest.mark.skipif(
    main._manim_command(get_binary_paths()) is None, reason="Manim CE is not installed"
)

ANIMATED = """from manim import *

class Dot1(Scene):
    def construct(self):
        self.play(FadeIn(Dot()), run_time=0.3)
"""

STATIC = """from manim import *

class Still(Scene):
    def construct(self):
        self.add(Circle())
"""

SLOW = """from manim import *

class Slow(Scene):
    def construct(self):
        self.play(Create(Circle()), run_time=60)
"""

BROKEN = """from manim import *

class Broken(Scene):
    def construct(self):
        self.play(Create(Circle()))
        undefined_name()
"""


@pytest.fixture
def isolated_workspace(tmp_path):
    media = tmp_path / "media"
    assets = tmp_path / "assets"
    media.mkdir()
    assets.mkdir()
    with patch.object(main, "WORKSPACE_DIR", str(tmp_path)), patch.object(
        main, "MEDIA_DIR", str(media)
    ), patch.object(main, "ASSETS_DIR", str(assets)):
        yield tmp_path


def _collect(ws, render_id, timeout=150):
    events = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = ws.receive_json()
        if msg.get("render_id") != render_id:
            continue
        events.append(msg)
        if msg["type"] == "result":
            return events
    pytest.fail("render did not finish in time")


def test_unsaved_code_render_lands_in_script_media_folder(client, isolated_workspace):
    with client.websocket_connect("/api/render") as ws:
        ws.send_json({"type": "start", "id": "r1", "filename": "demo.py", "scene": "Dot1", "quality": "l", "code": ANIMATED})
        events = _collect(ws, "r1")

    result = events[-1]
    assert result["success"] is True, events
    ready = [e for e in events if e["type"] == "file_ready"]
    assert len(ready) == 1
    assert ready[0]["kind"] == "video"
    assert ready[0]["url"] == "/media/videos/demo/480p15/Dot1.mp4"
    assert (isolated_workspace / "media" / "videos" / "demo" / "480p15" / "Dot1.mp4").is_file()
    assert any(e["type"] == "progress" for e in events)

    # Scratch script and scratch media are cleaned up; logs never mention them.
    leftovers = [p for p in isolated_workspace.rglob("*") if main.TEMP_PREFIX in p.name]
    assert leftovers == []
    assert not any(main.TEMP_PREFIX in (e.get("message") or "") for e in events), [e for e in events if main.TEMP_PREFIX in (e.get("message") or "")]


def test_static_scene_produces_image(client, isolated_workspace):
    (isolated_workspace / "still.py").write_text(STATIC, encoding="utf-8")
    with client.websocket_connect("/api/render") as ws:
        ws.send_json({"type": "start", "id": "img", "filename": "still.py", "scene": "Still", "quality": "l"})
        events = _collect(ws, "img")

    assert events[-1]["success"] is True, events
    ready = next(e for e in events if e["type"] == "file_ready")
    assert ready["kind"] == "image"
    assert ready["url"].startswith("/media/images/still/Still")

    listed = main.get_files()["media"]
    assert listed and listed[0]["type"] == "image" and listed[0]["scene"] == "Still"


def test_cancel_reports_cancelled_result(client, isolated_workspace):
    (isolated_workspace / "slow.py").write_text(SLOW, encoding="utf-8")
    with client.websocket_connect("/api/render") as ws:
        ws.send_json({"type": "start", "id": "c1", "filename": "slow.py", "scene": "Slow", "quality": "l"})
        # Wait until Manim is actually rendering frames before cancelling.
        while True:
            msg = ws.receive_json()
            if msg.get("type") == "progress":
                break
        ws.send_json({"type": "cancel"})
        events = _collect(ws, "c1", timeout=30)

    assert events[-1]["status"] == "cancelled"
    assert events[-1]["success"] is False


def test_script_error_reports_user_line(client, isolated_workspace):
    with client.websocket_connect("/api/render") as ws:
        ws.send_json({"type": "start", "id": "e1", "filename": "broken.py", "scene": "Broken", "quality": "l", "code": BROKEN})
        events = _collect(ws, "e1")

    assert events[-1]["status"] == "failed"
    log_text = "\n".join(e.get("message") or "" for e in events)
    assert "broken.py" in log_text
    assert "undefined_name" in log_text
