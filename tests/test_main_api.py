import os
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from main import get_scenes_from_code, get_scene_animations  # noqa: E402
from workspace_paths import safe_join, safe_basename, UnsafePathError  # noqa: E402


class MainApiASTTests(unittest.TestCase):
    def test_get_scenes_preserves_source_line_order(self):
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
"""
        scenes = get_scenes_from_code(code)
        self.assertEqual(scenes, ["AlphaScene", "BetaScene", "GammaScene"])

    def test_get_scene_animations_handles_async_and_wait(self):
        code = """from manim import *

class DemoScene(Scene):
    async def construct(self):
        self.play(Create(Square()))
        self.wait(2.5)
        self.wait(duration=3.0)
"""
        anims = get_scene_animations(code)
        self.assertIn("DemoScene", anims)
        self.assertEqual(len(anims["DemoScene"]), 3)
        self.assertEqual(anims["DemoScene"][0]["type"], "play")
        self.assertEqual(anims["DemoScene"][1]["type"], "wait")
        self.assertEqual(anims["DemoScene"][1]["duration"], 2.5)
        self.assertEqual(anims["DemoScene"][1]["label"], "Wait 2.5s")
        self.assertEqual(anims["DemoScene"][2]["duration"], 3.0)

    def test_get_scenes_handles_syntax_errors_gracefully(self):
        malformed_code = "class IncompleteScene(Scene:\n    def construct(self):"
        scenes = get_scenes_from_code(malformed_code)
        self.assertEqual(scenes, [])
        anims = get_scene_animations(malformed_code)
        self.assertEqual(anims, {})


class AssetValidationTests(unittest.TestCase):
    def test_allowed_extensions_set(self):
        from main import ALLOWED_ASSET_EXTENSIONS
        self.assertIn(".svg", ALLOWED_ASSET_EXTENSIONS)
        self.assertIn(".png", ALLOWED_ASSET_EXTENSIONS)
        self.assertIn(".mp3", ALLOWED_ASSET_EXTENSIONS)
        self.assertNotIn(".exe", ALLOWED_ASSET_EXTENSIONS)
        self.assertNotIn(".bat", ALLOWED_ASSET_EXTENSIONS)
        self.assertNotIn(".py", ALLOWED_ASSET_EXTENSIONS)


class PathSanitizationTests(unittest.TestCase):
    def test_download_temp_clean_path_handling(self):
        with tempfile.TemporaryDirectory() as tmp:
            media_dir = os.path.join(tmp, "media")
            videos_dir = os.path.join(media_dir, "videos")
            os.makedirs(videos_dir)
            sample_file = os.path.join(videos_dir, "sample.mp4")
            with open(sample_file, "w") as f:
                f.write("content")

            # Verify that stripped relative path can be safely joined
            clean_path = "/media/videos/sample.mp4".strip().replace("\\", "/").lstrip("/")
            if clean_path.startswith("media/"):
                clean_path = clean_path[len("media/"):]

            resolved = safe_join(media_dir, clean_path)
            self.assertEqual(resolved, sample_file)


class CaseOnlyRenameLogicTests(unittest.TestCase):
    def test_case_only_rename_detection(self):
        old_name = "test.py"
        new_name = "Test.py"
        old_path = os.path.normcase(os.path.abspath("workspace/test.py"))
        new_path = os.path.normcase(os.path.abspath("workspace/Test.py"))
        self.assertEqual(old_path, new_path)
        self.assertNotEqual(old_name, new_name)


class EndpointsIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from main import app
        cls.client = TestClient(app)

    def test_status_endpoint(self):
        res = self.client.get("/api/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "online")

    def test_diagnostics_endpoint(self):
        res = self.client.get("/api/diagnostics")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("profile", data)
        self.assertIn("hardware", data)

    def test_files_endpoint(self):
        res = self.client.get("/api/files")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("scripts", data)
        self.assertIn("assets", data)
        self.assertIn("media", data)

    def test_parse_code_endpoint(self):
        res = self.client.post("/api/parse-code", json={"code": "class MyScene(Scene):\n    def construct(self):\n        self.play(Create(Circle()))\n"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["scenes"], ["MyScene"])
        self.assertIn("MyScene", data["animations"])

    def test_save_and_get_file_content(self):
        # Save valid file
        save_res = self.client.post("/api/save", json={"filename": "test_script.py", "code": "class Hello(Scene):\n    pass\n"})
        self.assertEqual(save_res.status_code, 200)
        save_data = save_res.json()
        self.assertTrue(save_data["success"])

        # Fetch file content
        get_res = self.client.get("/api/file-content?filename=test_script.py")
        self.assertEqual(get_res.status_code, 200)
        get_data = get_res.json()
        self.assertEqual(get_data["filename"], "test_script.py")
        self.assertEqual(get_data["scenes"], ["Hello"])

        # Traversal attempt should return 400
        bad_res = self.client.get("/api/file-content?filename=../secret.py")
        self.assertEqual(bad_res.status_code, 400)

        # Missing file should return 404
        missing_res = self.client.get("/api/file-content?filename=non_existent_12345.py")
        self.assertEqual(missing_res.status_code, 404)

    def test_upload_asset_validation(self):
        # Disallowed extension (.exe) -> 400
        res = self.client.post(
            "/api/upload-asset",
            files={"file": ("malicious.exe", b"MZ\x90\x00", "application/octet-stream")},
        )
        self.assertEqual(res.status_code, 400)

        # Allowed extension (.svg) -> 200
        res_ok = self.client.post(
            "/api/upload-asset",
            files={"file": ("valid_icon.svg", b"<svg></svg>", "image/svg+xml")},
        )
        self.assertEqual(res_ok.status_code, 200)
        data = res_ok.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["filename"], "valid_icon.svg")

    def test_download_temp_traversal_rejection(self):
        res = self.client.get("/api/download-temp?path=../../etc/passwd")
        self.assertEqual(res.status_code, 400)

    def test_websocket_render_error_handling(self):
        with self.client.websocket_connect("/api/render") as ws:
            # Invalid JSON
            ws.send_text("not-json")
            msg = ws.receive_json()
            self.assertEqual(msg["type"], "error")

            # Non-dict payload
            ws.send_text("[1, 2, 3]")
            msg2 = ws.receive_json()
            self.assertEqual(msg2["type"], "error")

            # Missing fields
            ws.send_json({"type": "start"})
            msg3 = ws.receive_json()
            self.assertEqual(msg3["type"], "error")

            # Invalid identifier scene name
            ws.send_json({"type": "start", "filename": "example.py", "scene": "123BadName!"})
            msg4 = ws.receive_json()
            self.assertEqual(msg4["type"], "error")

            # Cancel when idle
            ws.send_json({"type": "cancel"})
            msg5 = ws.receive_json()
            self.assertEqual(msg5["type"], "info")


if __name__ == "__main__":
    unittest.main()
