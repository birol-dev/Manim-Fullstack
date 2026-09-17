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



def test_get_scenes_ignores_non_scene_base_classes():
    """Helper / model classes with bases must not pollute the scene dropdown.

    Prefer Scene-like bases; name fallback is exact ``Scene`` / ``*Scene`` only
    (no substring-anywhere), and never overrides a non-Scene base list.
    """
    code = """from manim import *

class Config(BaseModel):
    pass

class Helper(dict):
    pass

class Boom(Exception):
    pass

class NotAScene(dict):
    pass

class ScenicHelper:
    pass

class MyScene(Scene):
    def construct(self):
        pass

class MyThreeDScene(ThreeDScene):
    def construct(self):
        pass

class CameraDemo(MovingCameraScene):
    def construct(self):
        pass

class AttrScene(manim.Scene):
    def construct(self):
        pass

class NameOnlyScene:
    pass
"""
    scenes = get_scenes_from_code(code)
    assert scenes == ["MyScene", "MyThreeDScene", "CameraDemo", "AttrScene", "NameOnlyScene"]
    assert "Config" not in scenes
    assert "Helper" not in scenes
    assert "Boom" not in scenes
    assert "NotAScene" not in scenes
    assert "ScenicHelper" not in scenes


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


def test_parse_code_rejects_oversized_payload(client):
    limit = 64
    with patch.object(main, "MAX_CODE_BYTES", limit):
        oversized = "x" * (limit + 1)
        res = client.post("/api/parse-code", json={"code": oversized})
        assert res.status_code == 413
        detail = res.json()["detail"]
        assert "maximum size" in detail
        assert str(limit) in detail


def test_save_rejects_oversized_payload(client, tmp_path):
    limit = 64
    with patch.object(main, "WORKSPACE_DIR", str(tmp_path)), patch.object(
        main, "MAX_CODE_BYTES", limit
    ):
        oversized = "x" * (limit + 1)
        res = client.post(
            "/api/save",
            json={"filename": "huge.py", "code": oversized},
        )
        assert res.status_code == 413
        detail = res.json()["detail"]
        assert "maximum size" in detail
        assert not (tmp_path / "huge.py").exists()


def test_spa_assets_not_shadowed_by_workspace_uploads(client, tmp_path, monkeypatch):
    """Vite bundles under /assets/*.js must win over workspace/assets uploads."""
    import main as main_mod

    frontend_assets = tmp_path / "frontend" / "dist" / "assets"
    frontend_assets.mkdir(parents=True)
    bundle = frontend_assets / "index-testbundle.js"
    bundle.write_text("console.log('spa')", encoding="utf-8")

    workspace_assets = tmp_path / "workspace" / "assets"
    workspace_assets.mkdir(parents=True)
    # Conflicting name would previously be served from workspace (or 404 if empty)
    (workspace_assets / "other.txt").write_text("upload", encoding="utf-8")

    monkeypatch.setattr(main_mod, "FRONTEND_DIR", str(tmp_path / "frontend" / "dist"))
    monkeypatch.setattr(main_mod, "FRONTEND_ASSETS_DIR", str(frontend_assets))
    monkeypatch.setattr(main_mod, "ASSETS_DIR", str(workspace_assets))

    res = client.get("/assets/index-testbundle.js")
    assert res.status_code == 200
    assert b"spa" in res.content

    res_upload = client.get("/assets/other.txt")
    assert res_upload.status_code == 200
    assert res_upload.content == b"upload"

    assert client.get("/assets/missing-file.js").status_code == 404


def test_download_temp_endpoint(client, tmp_path):
    media_dir = tmp_path / "media"
    temp_dir = media_dir / "_temp_run_12345"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_clip = temp_dir / "clip.mp4"
    temp_clip.write_text("videocontent", encoding="utf-8")

    permanent_dir = media_dir / "videos" / "scene_a"
    permanent_dir.mkdir(parents=True, exist_ok=True)
    permanent_clip = permanent_dir / "render.mp4"
    permanent_clip.write_text("keepme", encoding="utf-8")

    with patch.object(main, "MEDIA_DIR", str(media_dir)):
        res = client.get(f"/api/download-temp?path=_temp_run_12345/clip.mp4")
        assert res.status_code == 200
        assert res.text == "videocontent"

        # Permanent media must not be served (or deleted) via download-temp
        res_perm = client.get("/api/download-temp?path=videos/scene_a/render.mp4")
        assert res_perm.status_code == 400
        assert permanent_clip.exists()
        assert permanent_clip.read_text(encoding="utf-8") == "keepme"

        res_404 = client.get("/api/download-temp?path=_temp_run_missing/clip.mp4")
        assert res_404.status_code == 404

        res_unsafe = client.get("/api/download-temp?path=../secret.mp4")
        assert res_unsafe.status_code == 400


def test_install_endpoints_success_and_failures(client):
    with patch.dict("os.environ", {"RUNNING_IN_DOCKER": "", "RENDER": "", "MANIM_ALLOW_INSTALLS": "1"}, clear=False):
        # Clear docker/cloud markers for the success path
        with patch.object(main, "_installers_allowed", return_value=None):
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

    with patch.object(main, "_installers_allowed", return_value="disabled in docker"):
        res_blocked = client.post("/api/install-manim")
        assert res_blocked.status_code == 403


MOCK_BINARIES = {
    "manim": "/usr/local/bin/manim",
    "ffmpeg": "/usr/local/bin/ffmpeg",
    "latex": "/usr/local/bin/latex",
    "dvisvgm": "/usr/local/bin/dvisvgm",
    "latex_available": True,
}


def _patch_conn_executor(mock_execute):
    """Patch ManimExecutor so each websocket gets a controllable instance."""
    instance = MagicMock()
    instance.execute = AsyncMock(side_effect=mock_execute)
    instance.cancel = AsyncMock()
    return patch.object(main, "ManimExecutor", return_value=instance)


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

            with patch.object(main, "get_binary_paths", return_value=MOCK_BINARIES):
                with _patch_conn_executor(mock_execute):
                    with client.websocket_connect("/api/render") as ws:
                        ws.send_json({
                            "type": "start",
                            "filename": "script.py",
                            "scene": "MyScene",
                            "quality": "l",
                            "use_opengl": False,
                        })

                        received = []
                        for _ in range(20):
                            msg = ws.receive_json()
                            received.append(msg)
                            if msg.get("type") == "result":
                                break
                            if msg.get("type") == "error":
                                pytest.fail(f"Unexpected websocket error: {msg.get('message')}")
                        else:
                            pytest.fail("Websocket render did not produce a 'result' message within expected steps.")

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

            with patch.object(main, "get_binary_paths", return_value=MOCK_BINARIES):
                with _patch_conn_executor(mock_execute):
                    with client.websocket_connect("/api/render") as ws:
                        ws.send_json({
                            "type": "start",
                            "filename": "adhoc.py",
                            "scene": "TempScene",
                            "download_only": True,
                            "code": "class TempScene(Scene): pass",
                        })

                        received = []
                        for _ in range(20):
                            msg = ws.receive_json()
                            received.append(msg)
                            if msg.get("type") == "result":
                                break
                            if msg.get("type") == "error":
                                pytest.fail(f"Unexpected websocket error: {msg.get('message')}")
                        else:
                            pytest.fail("Websocket render did not produce a 'result' message within expected steps.")

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

            with patch.object(main, "get_binary_paths", return_value=MOCK_BINARIES):
                with _patch_conn_executor(mock_execute):
                    with client.websocket_connect("/api/render") as ws:
                        ws.send_json({
                            "type": "start",
                            "filename": "cancel_scene.py",
                            "scene": "CancelScene",
                        })
                        ws.send_json({"type": "cancel"})

                        received = []
                        for _ in range(20):
                            msg = ws.receive_json()
                            received.append(msg)
                            if msg.get("type") == "result":
                                break
                            if msg.get("type") == "error":
                                pytest.fail(f"Unexpected websocket error: {msg.get('message')}")
                        else:
                            pytest.fail("Websocket render did not produce a 'result' message within expected steps.")

                        assert received[-1]["type"] == "result"
                        assert received[-1]["success"] is False
                        assert received[-1]["status"] == "cancelled"


def test_is_temp_media_relpath_helper():
    assert main._is_temp_media_relpath("_temp_run_abc/clip.mp4") is True
    assert main._is_temp_media_relpath("videos/_temp_run_abc/1080p60/Scene.mp4") is True
    assert main._is_temp_media_relpath("videos/scene_a/render.mp4") is False
    assert main._is_temp_media_relpath("media/_temp_run_x/a.mp4") is True


def test_installers_allowed_cloud_and_env(monkeypatch):
    monkeypatch.delenv("RUNNING_IN_DOCKER", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("MANIM_ALLOW_INSTALLS", raising=False)
    assert main._installers_allowed() is None

    monkeypatch.setenv("RUNNING_IN_DOCKER", "true")
    assert main._installers_allowed() is not None

    monkeypatch.delenv("RUNNING_IN_DOCKER", raising=False)
    monkeypatch.setenv("MANIM_ALLOW_INSTALLS", "false")
    assert main._installers_allowed() is not None
