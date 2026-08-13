import os
import sys
import tempfile
import unittest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from workspace_paths import (  # noqa: E402
    UnsafePathError,
    is_within_directory,
    safe_basename,
    safe_join,
)


class SafeBasenameTests(unittest.TestCase):
    def test_accepts_plain_python_filename(self):
        self.assertEqual(safe_basename("example.py", required_suffix=".py"), "example.py")

    def test_rejects_parent_directory_traversal(self):
        with self.assertRaises(UnsafePathError):
            safe_basename("../secret.py", required_suffix=".py")

    def test_rejects_nested_relative_path(self):
        with self.assertRaises(UnsafePathError):
            safe_basename("subdir/scene.py", required_suffix=".py")

    def test_rejects_empty_and_dot_names(self):
        for name in ("", "   ", ".", "..", None):
            with self.subTest(name=name):
                with self.assertRaises(UnsafePathError):
                    safe_basename(name)

    def test_rejects_backslash_traversal(self):
        with self.assertRaises(UnsafePathError):
            safe_basename("..\\secret.py", required_suffix=".py")

    def test_rejects_wrong_suffix(self):
        with self.assertRaises(UnsafePathError):
            safe_basename("notes.txt", required_suffix=".py")


class DirectoryBoundaryTests(unittest.TestCase):
    def test_rejects_sibling_prefix_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            media_dir = os.path.join(tmp, "media")
            sibling = os.path.join(tmp, "media_backup")
            os.makedirs(media_dir)
            os.makedirs(sibling)
            secret = os.path.join(sibling, "secret.mp4")
            with open(secret, "w", encoding="utf-8") as handle:
                handle.write("x")

            self.assertTrue(is_within_directory(os.path.join(media_dir, "clip.mp4"), media_dir))
            self.assertFalse(is_within_directory(secret, media_dir))
            with self.assertRaises(UnsafePathError):
                safe_join(media_dir, os.path.join("..", "media_backup", "secret.mp4"))

    def test_rejects_absolute_path_join(self):
        with tempfile.TemporaryDirectory() as tmp:
            media_dir = os.path.join(tmp, "media")
            os.makedirs(media_dir)
            outside = os.path.join(tmp, "outside.mp4")
            with open(outside, "w", encoding="utf-8") as handle:
                handle.write("x")
            with self.assertRaises(UnsafePathError):
                safe_join(media_dir, outside)

    def test_safe_join_keeps_relative_media_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            media_dir = os.path.join(tmp, "media")
            os.makedirs(os.path.join(media_dir, "videos"))
            joined = safe_join(media_dir, "videos", "scene.mp4")
            self.assertTrue(is_within_directory(joined, media_dir))
            self.assertTrue(joined.endswith(os.path.join("videos", "scene.mp4")))


if __name__ == "__main__":
    unittest.main()
