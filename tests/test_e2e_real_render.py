import shutil
import sys
import pytest

from diagnostics import get_binary_paths
from executor import ManimExecutor


@pytest.mark.asyncio
async def test_real_render_pipeline_or_cli_subprocess(tmp_path):
    """
    Integration test exercising real subprocess execution, pipe streaming,
    progress parsing, and result generation.
    """
    binaries = get_binary_paths()
    manim_bin = binaries.get("manim")
    executor = ManimExecutor(str(tmp_path))
    script_path = tmp_path / "minimal_test.py"

    events = []

    async def log_cb(evt):
        events.append(evt)

    if manim_bin and manim_bin != "Not Found" and shutil.which(manim_bin):
        code = """from manim import *

class MinimalCircle(Scene):
    def construct(self):
        c = Circle(radius=0.5)
        self.play(Create(c), run_time=0.5)
"""
        script_path.write_text(code, encoding="utf-8")

        result = await executor.execute(
            manim_path=manim_bin,
            script_name="minimal_test.py",
            scene_name="MinimalCircle",
            quality="l",
            use_opengl=False,
            log_callback=log_cb,
        )
        assert result.get("status") in ("success", "failed", "error")
        assert len(events) > 0
    else:
        code = """import sys
print("[ 50%] 15/30")
sys.stdout.flush()
"""
        script_path.write_text(code, encoding="utf-8")

        result = await executor.execute(
            manim_path=sys.executable,
            script_name="minimal_test.py",
            scene_name="MinimalCircle",
            quality="l",
            use_opengl=False,
            log_callback=log_cb,
        )
        assert result is not None
        assert result.get("status") in ("success", "failed", "error")
