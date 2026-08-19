import json
import os
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

import main
from main import (
    ALLOWED_ASSET_EXTENSIONS,
    MAX_ASSET_SIZE_BYTES,
    app,
    get_scene_animations,
    get_scenes_from_code,
)


def test_get_scenes_preserves_source_line_order():
    code = """from manim import *

class AlphaScene(Scene):
    def construct(self):
        pass

class BetaScene(Scene):
    def construct(self):
        pass

class GammaScene(ThreeDScene):
    def construct(self):
        pass

class NotInheritedScene:
    pass

class RegularClass:
    pass
"""
    scenes = get_scenes_from_code(code)
    assert scenes == ["AlphaScene", "BetaScene", "GammaScene", "NotInheritedScene"]


def test_get_scene_animations_handles_all_syntax_forms():
    code = """from manim import *

class DemoScene(Scene):
    async def construct(self):
        self.play(Create(Square()), run_time=2)
        self.wait()
        self.wait(2.5)
        self.wait(duration=3.0)
        self.wait(run_time=4.5)
        self.wait(some_var)
        self.wait(duration="custom_str")
        self.other_func()

class NoConstructScene(Scene):
    def setup(self):
        pass

class EmptyConstruct(Scene):
    def construct(self):
        pass
"""
    anims = get_scene_animations(code)
    assert "DemoScene" in anims
    assert "NoConstructScene" not in anims
    assert "EmptyConstruct" not in anims
    assert len(anims["DemoScene"]) == 7
    assert anims["DemoScene"][0]["type"] == "play"
    assert anims["DemoScene"][1]["type"] == "wait"
    assert anims["DemoScene"][1]["duration"] == 1.0
    assert anims["DemoScene"][2]["duration"] == 2.5
    assert anims["DemoScene"][3]["duration"] == 3.0
    assert anims["DemoScene"][4]["duration"] == 4.5


def test_get_scenes_handles_syntax_errors_gracefully():
    malformed_code = "class IncompleteScene(Scene:\n    def construct(self):"
    assert get_scenes_from_code(malformed_code) == []
    assert get_scene_animations(malformed_code) == {}


def test_get_scene_animations_unparse_fallbacks():
    code = """from manim import *
class RobustScene(Scene):
    def construct(self):
        self.play(Create(Circle()))
        self.wait(1)
"""
    with patch("ast.unparse", side_effect=Exception("Unparse error")):
        anims = get_scene_animations(code)
        assert len(anims["RobustScene"]) == 2
        assert "Play" in anims["RobustScene"][0]["label"]


def test_status_and_health_endpoints(client):
    res_status = client.get("/api/status")
    assert res_status.status_code == 200
    assert res_status.json()["status"] == "online"

    res_health = client.get("/api/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "online"


def test_read_root_endpoint(client):
    res = client.get("/")
    assert res.status_code == 200


def test_diagnostics_endpoint(client):
    response = client.get("/api/diagnostics")
    assert response.status_code == 200
    data = response.json()
    assert "profile" in data
    assert "hardware" in data
    assert "dependencies" in data


def test_files_list_endpoint_and_default_generation(client, tmp_path):
    media_dir = tmp_path / "media"
    videos_dir = media_dir / "videos" / "scene_a"
    assets_dir = tmp_path / "assets"
    videos_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    with patch.object(main, "WORKSPACE_DIR", str(tmp_path)):
        with patch.object(main, "MEDIA_DIR", str(media_dir)):
            with patch.object(main, "ASSETS_DIR", str(assets_dir)):
                # Empty workspace auto-generates example.py
                res_empty = client.get("/api/files")
                assert res_empty.status_code == 200
                data_empty = res_empty.json()
                assert any(f["name"] == "example.py" for f in data_empty["scripts"])

                (tmp_path / "scene_a.py").write_text("class SceneA(Scene): pass", encoding="utf-8")
                (assets_dir / "logo.svg").write_text("<svg></svg>", encoding="utf-8")
                (videos_dir / "render.mp4").write_text("video", encoding="utf-8")

                res = client.get("/api/files")
                assert res.status_code == 200
                data = res.json()
                assert any(f["name"] == "scene_a.py" for f in data["scripts"])
                assert any(f["name"] == "logo.svg" for f in data["assets"])
                assert any(f["name"] == "render.mp4" for f in data["media"])


def test_file_content_endpoint_success_and_errors(client, tmp_path):
    with patch.object(main, "WORKSPACE_DIR", str(tmp_path)):
        (tmp_path / "demo.py").write_text("class MyDemo(Scene):\n    pass\n", encoding="utf-8")

        res = client.get("/api/file-content?filename=demo.py")
        assert res.status_code == 200
        data = res.json()
        assert data["filename"] == "demo.py"
        assert "MyDemo" in data["scenes"]

        res_404 = client.get("/api/file-content?filename=missing.py")
        assert res_404.status_code == 404

        res_400 = client.get("/api/file-content?filename=../secret.py")
        assert res_400.status_code == 400

        with patch("builtins.open", side_effect=OSError("Disk read error")):
            res_500 = client.get("/api/file-content?filename=demo.py")
            assert res_500.status_code == 500


def test_save_file_endpoint_success_and_errors(client, tmp_path):
    with patch.object(main, "WORKSPACE_DIR", str(tmp_path)):
        payload = {"filename": "created", "code": "class CreatedScene(Scene):\n    pass\n"}
        res = client.post("/api/save", json=payload)
        assert res.status_code == 200
        assert res.json()["success"] is True
        assert (tmp_path / "created.py").exists()

        res_unsafe = client.post("/api/save", json={"filename": "../evil.py", "code": "pass"})
        assert res_unsafe.status_code == 400

        with patch("builtins.open", side_effect=OSError("Disk write error")):
            res_err = client.post("/api/save", json=payload)
            assert res_err.status_code == 500


def test_rename_file_endpoint_success_and_errors(client, tmp_path):
    with patch.object(main, "WORKSPACE_DIR", str(tmp_path)):
        (tmp_path / "old.py").write_text("code", encoding="utf-8")

        res = client.post("/api/rename", json={"old_name": "old.py", "new_name": "new.py"})
        assert res.status_code == 200
        assert not (tmp_path / "old.py").exists()
        assert (tmp_path / "new.py").exists()

        # Case-only rename
        res_case = client.post("/api/rename", json={"old_name": "new.py", "new_name": "NEW.py"})
        assert res_case.status_code == 200

        res_missing = client.post("/api/rename", json={"old_name": "not_exist.py", "new_name": "new2.py"})
        assert res_missing.status_code == 404

        (tmp_path / "existing.py").write_text("x", encoding="utf-8")
        res_conflict = client.post("/api/rename", json={"old_name": "NEW.py", "new_name": "existing.py"})
        assert res_conflict.status_code == 400

        res_unsafe = client.post("/api/rename", json={"old_name": "../old.py", "new_name": "new.py"})
        assert res_unsafe.status_code == 400

        with patch("os.rename", side_effect=OSError("Rename error")):
            res_500 = client.post("/api/rename", json={"old_name": "NEW.py", "new_name": "brand_new.py"})
            assert res_500.status_code == 500


def test_upload_asset_endpoint(client, tmp_path):
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    with patch.object(main, "ASSETS_DIR", str(assets_dir)):
        file_content = b"<svg>test</svg>"
        res = client.post(
            "/api/upload-asset",
            files={"file": ("icon.svg", file_content, "image/svg+xml")},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["filename"] == "icon.svg"

        res_bad_ext = client.post(
            "/api/upload-asset",
            files={"file": ("malicious.exe", b"binary", "application/octet-stream")},
        )
        assert res_bad_ext.status_code == 400

        oversized_data = b"x" * (MAX_ASSET_SIZE_BYTES + 1024)
        res_oversized = client.post(
            "/api/upload-asset",
            files={"file": ("huge.png", oversized_data, "image/png")},
        )
        assert res_oversized.status_code == 413

        with patch("builtins.open", side_effect=OSError("Disk upload error")):
            res_500 = client.post(
                "/api/upload-asset",
                files={"file": ("valid.png", b"data", "image/png")},
            )
            assert res_500.status_code == 500


def test_parse_code_endpoint(client):
    code = "class LiveScene(Scene):\n    def construct(self):\n        self.play(Create(Square()))\n"
    res = client.post("/api/parse-code", json={"code": code})
    assert res.status_code == 200
    data = res.json()
    assert "LiveScene" in data["scenes"]
    assert len(data["animations"]["LiveScene"]) == 1


def test_download_temp_endpoint(client, tmp_path):
    media_dir = tmp_path / "media"
    temp_dir = media_dir / "_temp_run_12345"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_clip = temp_dir / "clip.mp4"
    temp_clip.write_text("videocontent", encoding="utf-8")

    with patch.object(main, "MEDIA_DIR", str(media_dir)):
        res = client.get(f"/api/download-temp?path=_temp_run_12345/clip.mp4")
        assert res.status_code == 200
        assert res.text == "videocontent"

        res_404 = client.get("/api/download-temp?path=nonexistent.mp4")
        assert res_404.status_code == 404

        res_unsafe = client.get("/api/download-temp?path=../secret.mp4")
        assert res_unsafe.status_code == 400


def test_install_endpoints_success_and_failures(client):
    with patch("shutil.which", return_value="winget.exe"):
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock()

            res_latex = client.post("/api/install-latex")
            assert res_latex.status_code == 200
            assert res_latex.json()["success"] is True

            res_ffmpeg = client.post("/api/install-ffmpeg")
            assert res_ffmpeg.status_code == 200
            assert res_ffmpeg.json()["success"] is True

            res_manim = client.post("/api/install-manim")
            assert res_manim.status_code == 200
            assert res_manim.json()["success"] is True

    with patch("shutil.which", return_value=None):
        with patch("os.path.exists", return_value=False):
            res_no_winget = client.post("/api/install-latex")
            assert res_no_winget.status_code == 400


def test_websocket_render_lifecycle_success(client, tmp_path):
    media_dir = tmp_path / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    with patch.object(main, "WORKSPACE_DIR", str(tmp_path)):
        with patch.object(main, "MEDIA_DIR", str(media_dir)):
            (tmp_path / "script.py").write_text("class MyScene(Scene): pass", encoding="utf-8")

            async def mock_execute(manim_path, script_name, scene_name, quality, use_opengl, log_callback):
                await log_callback({
                    "type": "file_ready",
                    "abs_path": str(media_dir / "MyScene.mp4"),
                    "rel_path": "media/MyScene.mp4",
                    "filename": "MyScene.mp4",
                })
                await log_callback({"type": "status", "status": "success", "message": "Rendering completed."})
                return {"success": True, "status": "success"}

            with patch.object(main.executor, "execute", side_effect=mock_execute):
                with client.websocket_connect("/api/render") as ws:
                    ws.send_json({
                        "type": "start",
                        "filename": "script.py",
                        "scene": "MyScene",
                        "quality": "l",
                        "use_opengl": False,
                    })

                    received = []
                    while True:
                        msg = ws.receive_json()
                        received.append(msg)
                        if msg.get("type") == "result":
                            break

                    msg_types = [m["type"] for m in received]
                    assert "file_ready" in msg_types
                    assert "result" in msg_types
                    assert received[-1]["success"] is True


def test_websocket_render_with_download_only_and_temp_code(client, tmp_path):
    media_dir = tmp_path / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    with patch.object(main, "WORKSPACE_DIR", str(tmp_path)):
        with patch.object(main, "MEDIA_DIR", str(media_dir)):
            async def mock_execute(manim_path, script_name, scene_name, quality, use_opengl, log_callback):
                await log_callback({
                    "type": "file_ready",
                    "abs_path": str(media_dir / "TempScene.mp4"),
                    "rel_path": "media/videos/TempScene.mp4",
                    "filename": "TempScene.mp4",
                })
                return {"success": True, "status": "success"}

            with patch.object(main.executor, "execute", side_effect=mock_execute):
                with client.websocket_connect("/api/render") as ws:
                    ws.send_json({
                        "type": "start",
                        "filename": "adhoc.py",
                        "scene": "TempScene",
                        "download_only": True,
                        "code": "class TempScene(Scene): pass",
                    })

                    received = []
                    while True:
                        msg = ws.receive_json()
                        received.append(msg)
                        if msg.get("type") == "result":
                            break

                    file_ready_msg = next(m for m in received if m.get("type") == "file_ready")
                    assert file_ready_msg.get("is_temp_download") is True
                    assert "api/download-temp" in file_ready_msg.get("rel_path")


def test_websocket_render_validation_errors(client):
    with patch.object(main, "get_binary_paths", return_value={"manim": "Not Found"}):
        with client.websocket_connect("/api/render") as ws:
            ws.send_text("not json")
            msg = ws.receive_json()
            assert msg["type"] == "error"

            ws.send_text("12345")
            msg2 = ws.receive_json()
            assert msg2["type"] == "error"

            ws.send_json({"type": "start", "filename": "test.py"})
            msg3 = ws.receive_json()
            assert msg3["type"] == "error"

            ws.send_json({"type": "start", "filename": "test.py", "scene": "123_invalid_id"})
            msg4 = ws.receive_json()
            assert msg4["type"] == "error"

            ws.send_json({"type": "start", "filename": "../secret.py", "scene": "Scene"})
            msg5 = ws.receive_json()
            assert msg5["type"] == "error"

            ws.send_json({"type": "start", "filename": "test.py", "scene": "Scene"})
            msg6 = ws.receive_json()
            assert msg6["type"] == "error"
            assert "Manim executable not found" in msg6["message"]


def test_websocket_render_cancellation(client, tmp_path):
    media_dir = tmp_path / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    with patch.object(main, "WORKSPACE_DIR", str(tmp_path)):
        with patch.object(main, "MEDIA_DIR", str(media_dir)):
            (tmp_path / "cancel_scene.py").write_text("class CancelScene(Scene): pass", encoding="utf-8")

            async def mock_execute(manim_path, script_name, scene_name, quality, use_opengl, log_callback):
                await log_callback({"type": "status", "status": "cancelled", "message": "Cancelled"})
                return {"success": False, "status": "cancelled"}

            with patch.object(main.executor, "execute", side_effect=mock_execute):
                with client.websocket_connect("/api/render") as ws:
                    ws.send_json({
                        "type": "start",
                        "filename": "cancel_scene.py",
                        "scene": "CancelScene",
                    })
                    ws.send_json({"type": "cancel"})

                    received = []
                    while True:
                        msg = ws.receive_json()
                        received.append(msg)
                        if msg.get("type") == "result":
                            break

                    assert received[-1]["type"] == "result"
                    assert received[-1]["success"] is False
                    assert received[-1]["status"] == "cancelled"
