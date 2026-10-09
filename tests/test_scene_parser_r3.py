"""Round 3 scene parser: match/case blocks, range(0) and nested loop counts,
comprehensions, and the loop chain the timeline uses to interleave loop bodies."""
import main
from scene_parser import get_render_names, get_scene_animations, get_scenes_from_code

HEAD = "from manim import *\n"


def _steps(body, scene="S"):
    code = HEAD + f"class {scene}(Scene):\n    def construct(self):\n" + body
    return get_scene_animations(code)[scene]


def test_scene_inside_match_case_is_found_and_renderable():
    code = HEAD + (
        "match 1:\n"
        "    case 1:\n"
        "        class InMatch(Scene):\n"
        "            def construct(self):\n"
        "                self.wait()\n"
        "    case _:\n"
        "        class Fallback(Scene):\n"
        "            pass\n"
    )
    assert get_scenes_from_code(code) == ["InMatch", "Fallback"]
    assert {"InMatch", "Fallback"} <= get_render_names(code)["names"]
    # The render gate neither refuses nor warns about it any more.
    assert main._render_block_reason(code, "InMatch") is None
    assert main._render_scene_warning(code, "InMatch") is None


def test_inner_range_zero_gives_zero_runs():
    steps = _steps(
        "        for i in range(3):\n"
        "            for j in range(0):\n"
        "                self.play(Create(Circle()))\n"
        "            self.play(FadeIn(Square()))\n"
    )
    assert [(s["label"], s["repeat"]) for s in steps] == [("Create(Circle())", 0), ("FadeIn(Square())", 3)]


def test_outer_range_zero_gives_zero_runs_for_everything_inside():
    steps = _steps(
        "        for i in range(0):\n"
        "            for j in range(3):\n"
        "                self.play(Create(Circle()))\n"
        "            self.wait()\n"
    )
    assert [s["repeat"] for s in steps] == [0, 0]


def test_nested_loops_multiply_and_report_the_chain():
    steps = _steps(
        "        for i in range(2):\n"
        "            for j in [a, b, c]:\n"
        "                self.play(Create(Circle()))\n"
        "            self.play(FadeIn(Square()))\n"
    )
    create, fade = steps
    assert create["repeat"] == 6 and create["loop_line"] == 4
    assert create["loops"] == [[4, 8, 2], [5, 12, 3]]
    assert fade["repeat"] == 2 and fade["loops"] == [[4, 8, 2]]


def test_unknown_outer_loop_makes_inner_unknown():
    steps = _steps(
        "        for i in items:\n"
        "            for j in range(3):\n"
        "                self.play(Create(Circle()))\n"
    )
    assert steps[0]["repeat"] is None
    assert steps[0]["loops"] == [[4, 8, None], [5, 12, 3]]


def test_play_in_comprehensions_is_counted():
    steps = _steps(
        "        [self.play(Create(c)) for c in (a, b, c)]\n"
        "        list(self.play(FadeIn(d)) for d in range(2))\n"
        "        {self.play(Write(t)) for t in texts}\n"
        "        [self.play(Write(t)) for t in range(4) if t]\n"
        "        {k: self.play(Write(k)) for k in 'ab' for _ in range(2)}\n"
        "        self.wait()\n"
    )
    by_line = {s["line"]: s for s in steps}
    assert by_line[4]["repeat"] == 3 and by_line[4]["loop_line"] == 4
    assert by_line[5]["repeat"] == 2
    assert by_line[6]["repeat"] is None
    assert by_line[7]["repeat"] is None  # an `if` clause filters an unknown number
    assert by_line[8]["repeat"] == 4 and len(by_line[8]["loops"]) == 2
    assert "repeat" not in by_line[9] and by_line[9]["type"] == "wait"


def test_comprehension_inside_a_loop_multiplies():
    steps = _steps(
        "        for i in range(2):\n"
        "            [self.play(Create(c)) for c in (a, b, c)]\n"
    )
    assert steps[0]["repeat"] == 6
    assert steps[0]["loop_line"] == 4


def test_parse_code_endpoint_returns_json_loops(client):
    code = HEAD + "class S(Scene):\n    def construct(self):\n        for i in range(2):\n            self.wait()\n"
    res = client.post("/api/parse-code", json={"code": code})
    assert res.status_code == 200
    step = res.json()["animations"]["S"][0]
    assert step["loops"] == [[4, 8, 2]] and step["repeat"] == 2
