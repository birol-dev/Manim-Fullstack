import os
import sys
import tempfile
import unittest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from executor import ManimExecutor  # noqa: E402


class MediaRelPathTests(unittest.TestCase):
    def test_extracts_media_suffix_from_absolute_path(self):
        rel = ManimExecutor._to_media_rel_path(
            "/tmp/workspace/media/videos/demo/clip.mp4"
        )
        self.assertEqual(rel, "media/videos/demo/clip.mp4")


class FindLatestRenderTests(unittest.TestCase):
    def test_does_not_match_scene_name_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            videos = os.path.join(tmp, "media", "videos", "script")
            os.makedirs(videos)
            decoy = os.path.join(videos, "SceneExtra.mp4")
            target = os.path.join(videos, "Scene.mp4")
            with open(decoy, "w", encoding="utf-8") as handle:
                handle.write("decoy")
            with open(target, "w", encoding="utf-8") as handle:
                handle.write("target")
            os.utime(decoy, (3, 3))
            os.utime(target, (2, 2))

            executor = ManimExecutor(tmp)
            latest = executor._find_latest_render("script.py", "Scene")
            self.assertEqual(os.path.basename(latest), "Scene.mp4")


if __name__ == "__main__":
    unittest.main()
