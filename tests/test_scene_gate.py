"""The render pre-check only rejects what the AST can prove (no class, unknown name, syntax error)."""
import textwrap
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import main
from scene_parser import get_render_names, get_scenes_from_code

MOCK_BINARIES = {"manim": "/usr/bin/manim", "ffmpeg": "/usr/bin/ffmpeg", "latex": "/usr/bin/latex",
                 "dvisvgm": "/usr/bin/dvisvgm", "latex_available": True}


def code(src: str) -> str:
    return textwrap.dedent(src).lstrip()


ALIASED = code("""
    from manim import *
    from manim import Scene as S
    class Aliased(S):
        def construct(self):
            self.play(Create(Circle()))
""")
ALIASED_THREED = code("""
    from manim import ThreeDScene as TDS, MovingCameraScene as MCS
    class Spin(TDS):
        def construct(self): pass
    class Pan(MCS):
        def construct(self): pass
""")
FACTORY = code("""
    from manim import *
    def make_base():
        return Scene
    Base = make_base()
    class ViaFactory(Base):
        def construct(self): pass
""")
SLIDE = code("""
    from manim import *
    from manim_slides import Slide
    class Deck(Slide):
        def construct(self): pass
""")
IF_TRUE = code("""
    from manim import *
    if True:
        class Guarded(Scene):
            def construct(self): pass
""")
TRY_EXCEPT = code("""
    from manim import *
    try:
        import numpy
    except ImportError:
        numpy = None
    else:
        class InElse(Scene):
            def construct(self): pass
    finally:
        class InFinally(MovingCameraScene):
            def construct(self): pass
""")
CHAINS = code("""
    from manim import *
    class Base3D(ThreeDScene):
        pass
    class Orbit(Base3D):
        def construct(self): pass
    class Zoom(MovingCameraScene):
        def construct(self): pass
    class ZoomMore(Zoom):
        def construct(self): pass
""")
ASSIGNED = code("""
    from manim import *
    def build():
        class Inner(Scene):
            def construct(self): pass
        return Inner
    Intro = build()
""")
STAR_ONLY = code("""
    from manim import *
    from my_scenes import *
""")
NO_CLASS = code("""
    from manim import *
    x = 1
""")


@pytest.mark.parametrize(
    "src, expected",
    [
        (ALIASED, ["Aliased"]),
        (ALIASED_THREED, ["Spin", "Pan"]),
        (SLIDE, ["Deck"]),
        (IF_TRUE, ["Guarded"]),
        (TRY_EXCEPT, ["InElse", "InFinally"]),
        (CHAINS, ["Base3D", "Orbit", "Zoom", "ZoomMore"]),
    ],
)
def test_parser_finds_scenes_it_used_to_miss(src, expected):
    assert get_scenes_from_code(src) == expected


def test_nested_function_classes_are_not_module_scenes():
    assert get_scenes_from_code(ASSIGNED) == []
    info = get_render_names(ASSIGNED)
    assert info["has_class"] is True
    assert "Intro" in info["names"]


@pytest.mark.parametrize(
    "src, scene",
    [
        (ALIASED, "Aliased"),
        (ALIASED_THREED, "Spin"),
        (FACTORY, "ViaFactory"),
        (SLIDE, "Deck"),
        (IF_TRUE, "Guarded"),
        (TRY_EXCEPT, "InFinally"),
        (CHAINS, "Orbit"),
        (CHAINS, "ZoomMore"),
        (ASSIGNED, "Intro"),
        (STAR_ONLY, "Intro"),
    ],
)
def test_gate_lets_manim_decide(src, scene):
    assert main._render_block_reason(src, scene) is None


@pytest.mark.parametrize(
    "src, scene, warns",
    [
        (ALIASED, "Aliased", False),
        (SLIDE, "Deck", False),
        (FACTORY, "ViaFactory", True),
        (ASSIGNED, "Intro", True),
        (STAR_ONLY, "Intro", True),
    ],
)
def test_soft_warning_only_when_scene_is_unproven(src, scene, warns):
    assert (main._render_scene_warning(src, scene) is not None) is warns


def test_gate_still_rejects_file_without_any_class():
    assert main._render_block_reason(NO_CLASS, "Missing") == (
        "No Scene class found. Add one, for example: class Intro(Scene):"
    )


def test_gate_rejects_name_that_is_not_in_the_file():
    assert main._render_block_reason(CHAINS, "Nope") == (
        "Scene 'Nope' is not in this file. Found: Base3D, Orbit, Zoom, ZoomMore."
    )
    assert main._render_block_reason(FACTORY, "Nope") == (
        "Scene 'Nope' is not in this file. Found: no Scene classes."
    )


def test_gate_rejects_syntax_errors():
    assert main._render_block_reason("class A(Scene)\n    pass\n", "A").startswith("Syntax error on line 1:")


def _executor(seen):
    async def execute(manim_path, script_name, scene_name, quality, use_opengl, log_callback):
        seen.append(scene_name)
        await log_callback({"type": "status", "status": "failed", "message": "no output"})
        return {"success": False, "status": "failed"}

    instance = MagicMock()
    instance.execute = AsyncMock(side_effect=execute)
    instance.cancel = AsyncMock()
    return patch.object(main, "ManimExecutor", return_value=instance)


def _render(client, code_text, scene):
    seen = []
    with patch.object(main, "get_binary_paths", return_value=MOCK_BINARIES), _executor(seen):
        with client.websocket_connect("/api/render") as ws:
            ws.send_json({"type": "start", "id": "r1", "filename": "demo.py", "scene": scene,
                          "quality": "l", "code": code_text})
            events = []
            for _ in range(30):
                event = ws.receive_json()
                events.append(event)
                if event["type"] == "result":
                    break
    return seen, events


@pytest.fixture
def workspace_dirs(tmp_path):
    media = tmp_path / "media"
    media.mkdir()
    with patch.object(main, "WORKSPACE_DIR", str(tmp_path)), patch.object(main, "MEDIA_DIR", str(media)):
        yield tmp_path


def test_factory_scene_reaches_manim_with_info_note(client, workspace_dirs):
    seen, events = _render(client, FACTORY, "ViaFactory")
    assert seen == ["ViaFactory"]
    notes = [e["message"] for e in events if e["type"] == "info"]
    assert any("letting Manim decide" in note for note in notes)
    assert events[-1]["status"] == "failed"


def test_aliased_scene_reaches_manim_without_note(client, workspace_dirs):
    seen, events = _render(client, ALIASED, "Aliased")
    assert seen == ["Aliased"]
    assert not any("letting Manim decide" in e.get("message", "") for e in events)


def test_classless_file_is_rejected_before_manim(client, workspace_dirs):
    seen, events = _render(client, NO_CLASS, "Missing")
    assert seen == []
    assert events[-1]["status"] == "rejected"
    assert "No Scene class found" in events[-2]["message"]
