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
"""
        anims = get_scene_animations(code)
        self.assertIn("DemoScene", anims)
        self.assertEqual(len(anims["DemoScene"]), 2)
        self.assertEqual(anims["DemoScene"][0]["type"], "play")
        self.assertEqual(anims["DemoScene"][1]["type"], "wait")
        self.assertEqual(anims["DemoScene"][1]["duration"], 2.5)
        self.assertEqual(anims["DemoScene"][1]["label"], "Wait 2.5s")


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


if __name__ == "__main__":
    unittest.main()
