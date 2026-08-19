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

    def test_extracts_media_suffix_when_parent_has_media(self):
        rel = ManimExecutor._to_media_rel_path(
            "/home/media/workspace/media/videos/demo/clip.mp4"
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

    def test_ignores_partial_movie_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            videos = os.path.join(tmp, "media", "videos", "script", "1080p60")
            partial = os.path.join(videos, "partial_movie_files", "Scene")
            os.makedirs(partial)
            chunk = os.path.join(partial, "Scene.mp4")
            final = os.path.join(videos, "Scene.mp4")
            with open(final, "w", encoding="utf-8") as handle:
                handle.write("final")
            with open(chunk, "w", encoding="utf-8") as handle:
                handle.write("chunk")
            os.utime(final, (2, 2))
            os.utime(chunk, (5, 5))

    def test_finds_latest_mov_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            videos = os.path.join(tmp, "media", "videos", "script", "1080p60")
            os.makedirs(videos)
            final = os.path.join(videos, "Scene.mov")
            with open(final, "w", encoding="utf-8") as handle:
                handle.write("mov content")
            os.utime(final, (10, 10))

            executor = ManimExecutor(tmp)
            latest = executor._find_latest_render("script.py", "Scene")
            self.assertEqual(latest, final)


class ProgressParsingTests(unittest.TestCase):
    def test_extracts_rich_bracketed_progress(self):
        import asyncio
        executor = ManimExecutor("/tmp")
        events = []

        async def callback(evt):
            events.append(evt)

        async def run():
            stream = asyncio.StreamReader()
            stream.feed_data(b"Rendering Scene\n[ 42%] 25/60\n[100%] 60/60\n")
            stream.feed_eof()
            await executor._read_stream(stream, "stdout", callback)

        asyncio.run(run())
        progresses = [e["percent"] for e in events if e.get("type") == "progress"]
        self.assertEqual(progresses, [42, 100])


if __name__ == "__main__":
    unittest.main()


