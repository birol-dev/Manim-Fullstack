import os
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

import main
from main import (
    MAX_ASSET_SIZE_BYTES,
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
        assert anims["RobustScene"][0]["type"] == "play"
        assert anims["RobustScene"][0]["label"] == "animation"


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
        res = client.get("/api/download-temp?path=_temp_run_12345/clip.mp4")
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
                stem = script_name[:-3]
                await log_callback({"type": "log", "message": f"Traceback in /w/{script_name}:3; output in videos/{stem}/"})
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

                        log_msg = next(m for m in received if m.get("type") == "log")["message"]
                        # The script name is the user's; the folder really is a scratch one.
                        assert "/w/adhoc.py:3" in log_msg
                        assert "videos/_temp_run_" in log_msg

                        file_ready_msg = next(m for m in received if m.get("type") == "file_ready")
                        assert file_ready_msg.get("is_temp_download") is True
                        assert "api/download-temp" in file_ready_msg.get("rel_path")


def test_websocket_render_validation_errors(client):
    def rejected(ws):
        error, result = ws.receive_json(), ws.receive_json()
        assert error["type"] == "error"
        assert result == {"type": "result", "render_id": None, "success": False, "status": "rejected"}
        return error

    with patch.object(main, "get_binary_paths", return_value={"manim": "Not Found"}):
        with client.websocket_connect("/api/render") as ws:
            ws.send_text("not json")
            assert ws.receive_json()["type"] == "error"

            ws.send_text("12345")
            assert ws.receive_json()["type"] == "error"

            ws.send_json({"type": "start", "filename": "test.py"})
            rejected(ws)

            ws.send_json({"type": "start", "filename": "test.py", "scene": "123_invalid_id"})
            rejected(ws)

            ws.send_json({"type": "start", "filename": "../secret.py", "scene": "Scene"})
            rejected(ws)

            ws.send_json({"type": "start", "filename": "test.py", "scene": "Scene"})
            assert "Manim executable not found" in rejected(ws)["message"]


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


# --------------------------------------------------------------------------- #
# Scene parsing extras
# --------------------------------------------------------------------------- #


def test_subclasses_of_local_scenes_are_scenes():
    code = """from manim import *

class BaseSlide(Scene):
    def setup(self):
        pass

class Intro(BaseSlide):
    def construct(self):
        self.play(FadeIn(Dot()), run_time=2)

class Outro(Intro):
    def construct(self):
        self.wait()

class Helper(dict):
    pass

def make():
    class Nested(Scene):
        pass
"""
    assert get_scenes_from_code(code) == ["BaseSlide", "Intro", "Outro"]
    anims = get_scene_animations(code)
    assert anims["Intro"] == [{"type": "play", "label": "FadeIn(Dot())", "line": 9, "duration": 2.0}]
    assert anims["Outro"][0]["label"] == "Wait 1s"


def test_default_script_matches_workspace_example():
    example = os.path.join(main.WORKSPACE_DIR, "example.py")
    with open(example, encoding="utf-8") as f:
        assert f.read() == main.DEFAULT_SCRIPT
    assert get_scenes_from_code(main.DEFAULT_SCRIPT) == ["SquareToCircle", "TitleCard", "SineWave"]


# --------------------------------------------------------------------------- #
# Listing and deleting files
# --------------------------------------------------------------------------- #


def _write(path, content="x", mtime=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if mtime is not None:
        os.utime(str(path), (mtime, mtime))
    return path


@pytest.fixture
def ws_dirs(tmp_path):
    media = tmp_path / "media"
    assets = tmp_path / "assets"
    media.mkdir()
    assets.mkdir()
    with patch.object(main, "WORKSPACE_DIR", str(tmp_path)), patch.object(
        main, "MEDIA_DIR", str(media)
    ), patch.object(main, "ASSETS_DIR", str(assets)):
        yield tmp_path, media, assets


def test_media_listing_metadata_and_order(client, ws_dirs):
    root, media, _ = ws_dirs
    _write(root / "demo.py")
    _write(media / "videos" / "demo" / "480p15" / "Old.mp4", mtime=100)
    _write(media / "videos" / "demo" / "1080p60" / "New Scene.mp4", mtime=300)
    _write(media / "images" / "demo" / "Still_ManimCE_v0.21.0.png", mtime=200)
    _write(media / "videos" / "demo" / "480p15" / "partial_movie_files" / "Old" / "chunk.mp4", mtime=400)
    _write(media / "videos" / "_temp_run_abcd1234" / "480p15" / "Tmp.mp4", mtime=500)

    items = client.get("/api/files").json()["media"]
    assert [item["name"] for item in items] == ["New Scene.mp4", "Still_ManimCE_v0.21.0.png", "Old.mp4"]

    newest, image, oldest = items
    assert newest["url"] == "/media/videos/demo/1080p60/New%20Scene.mp4"
    assert newest["path"] == "videos/demo/1080p60/New Scene.mp4"
    assert (newest["type"], newest["script"], newest["quality"], newest["scene"]) == ("video", "demo", "1080p60", "New Scene")
    assert (image["type"], image["scene"], image["quality"]) == ("image", "Still", None)
    assert oldest["modified"] == 100


def test_delete_script(client, ws_dirs):
    root, _, _ = ws_dirs
    _write(root / "gone.py")
    assert client.delete("/api/scripts", params={"filename": "gone.py"}).status_code == 200
    assert not (root / "gone.py").exists()
    assert client.delete("/api/scripts", params={"filename": "gone.py"}).status_code == 404
    assert client.delete("/api/scripts", params={"filename": "../main.py"}).status_code == 400
    assert client.delete("/api/scripts", params={"filename": "notes.txt"}).status_code == 400


def test_delete_asset(client, ws_dirs):
    _, _, assets = ws_dirs
    _write(assets / "logo.svg")
    assert client.delete("/api/assets", params={"filename": "logo.svg"}).status_code == 200
    assert not (assets / "logo.svg").exists()
    assert client.delete("/api/assets", params={"filename": "logo.svg"}).status_code == 404
    assert client.delete("/api/assets", params={"filename": "../x.svg"}).status_code == 400


def test_delete_media_removes_chunks_and_empty_folders(client, ws_dirs):
    _, media, _ = ws_dirs
    video = _write(media / "videos" / "demo" / "480p15" / "Intro.mp4")
    _write(media / "videos" / "demo" / "480p15" / "partial_movie_files" / "Intro" / "a.mp4")
    keep = _write(media / "videos" / "other" / "480p15" / "Keep.mp4")

    res = client.delete("/api/media", params={"path": "media/videos/demo/480p15/Intro.mp4"})
    assert res.status_code == 200
    assert not video.exists()
    assert not (media / "videos" / "demo").exists()
    assert (media / "videos").is_dir() and keep.exists()

    assert client.delete("/api/media", params={"path": "videos/demo/480p15/Intro.mp4"}).status_code == 404
    for bad in ("../example.py", "videos/../../example.py", "Tex/abc.svg", "videos/demo/notes.txt"):
        assert client.delete("/api/media", params={"path": bad}).status_code == 400, bad


def test_sweep_temp_renders(ws_dirs):
    root, media, _ = ws_dirs
    scratch = _write(root / "_temp_run_deadbeef.py")
    temp_video_dir = media / "videos" / "_temp_run_deadbeef"
    _write(temp_video_dir / "480p15" / "S.mp4")
    keep = _write(media / "videos" / "demo" / "480p15" / "S.mp4")
    main._sweep_temp_renders()
    assert not scratch.exists()
    assert not temp_video_dir.exists()
    assert keep.exists()


def test_diagnostics_reports_fresh_dependencies_and_platform(client):
    fresh = {**MOCK_BINARIES, "manim": "/fresh/manim"}
    with patch.object(main, "get_binary_paths", return_value=fresh):
        data = client.get("/api/diagnostics").json()
    assert data["dependencies"]["manim"] == "/fresh/manim"
    assert data["platform"]
    assert data["python_version"]


def test_manim_command_resolution():
    assert main._manim_command({"manim_command": ["py", "-m", "manim"], "manim": "x"}) == ["py", "-m", "manim"]
    assert main._manim_command({"manim": "/bin/manim"}) == ["/bin/manim"]
    assert main._manim_command({"manim": "Not Found"}) is None


# --------------------------------------------------------------------------- #
# Render socket extras
# --------------------------------------------------------------------------- #


def _drain_until_result(ws, limit=20):
    received = []
    for _ in range(limit):
        msg = ws.receive_json()
        received.append(msg)
        if msg.get("type") == "result":
            return received
    pytest.fail("no result message")


def test_unsaved_render_is_relocated_and_ids_echoed(client, ws_dirs):
    root, media, _ = ws_dirs

    async def mock_execute(manim_path, script_name, scene_name, quality, use_opengl, log_callback):
        stem = script_name[:-3]
        assert stem.startswith(main.TEMP_PREFIX)
        out = _write(media / "videos" / stem / "480p15" / f"{scene_name}.mp4", "frames")
        await log_callback({"type": "log", "stream": "stdout", "message": f"File ready at '{out}' from {stem}.py"})
        await log_callback({
            "type": "file_ready",
            "abs_path": str(out),
            "rel_path": f"media/videos/{stem}/480p15/{scene_name}.mp4",
            "filename": f"{scene_name}.mp4",
        })
        return {"success": True, "status": "success"}

    with patch.object(main, "get_binary_paths", return_value=MOCK_BINARIES):
        with _patch_conn_executor(mock_execute):
            with client.websocket_connect("/api/render") as ws:
                ws.send_json({"type": "start", "id": 7, "filename": "demo.py", "scene": "Intro", "quality": "l", "code": "x"})
                received = _drain_until_result(ws)

    assert all(m.get("render_id") == 7 for m in received)
    log = next(m for m in received if m["type"] == "log")
    assert main.TEMP_PREFIX not in log["message"] and "demo.py" in log["message"]
    ready = [m for m in received if m["type"] == "file_ready"]
    assert len(ready) == 1
    assert ready[0]["url"] == "/media/videos/demo/480p15/Intro.mp4"
    assert ready[0]["kind"] == "video"
    assert "abs_path" not in ready[0]
    assert (media / "videos" / "demo" / "480p15" / "Intro.mp4").read_text() == "frames"
    assert [p.name for p in root.iterdir() if p.name.startswith(main.TEMP_PREFIX)] == []
    assert not any(p.name.startswith(main.TEMP_PREFIX) for p in (media / "videos").iterdir())


def test_cancel_before_process_starts_still_reports_result(client, ws_dirs):
    root, _, _ = ws_dirs
    _write(root / "s.py")
    started = []

    async def never_finishes(manim_path, script_name, scene_name, quality, use_opengl, log_callback):
        started.append(True)
        import asyncio
        await asyncio.sleep(30)
        return {"success": True, "status": "success"}

    with patch.object(main, "get_binary_paths", return_value=MOCK_BINARIES):
        instance = MagicMock()
        instance.execute = AsyncMock(side_effect=never_finishes)
        instance.cancel = AsyncMock()
        instance.is_running = False
        with patch.object(main, "ManimExecutor", return_value=instance):
            with client.websocket_connect("/api/render") as ws:
                ws.send_json({"type": "start", "id": "a", "filename": "s.py", "scene": "S"})
                ws.send_json({"type": "cancel"})
                received = _drain_until_result(ws)

    result = received[-1]
    assert result["render_id"] == "a"
    assert result["status"] == "cancelled"


def test_validation_errors_echo_render_id(client):
    with client.websocket_connect("/api/render") as ws:
        ws.send_json({"type": "start", "id": "bad", "filename": "x.py", "scene": "1nope"})
        msg = ws.receive_json()
        result = ws.receive_json()
    assert msg == {"type": "error", "render_id": "bad", "message": "Scene name must be a valid Python identifier."}
    assert result == {"type": "result", "render_id": "bad", "success": False, "status": "rejected"}
