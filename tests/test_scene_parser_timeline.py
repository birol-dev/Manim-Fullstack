"""Timeline run-time estimates and loop tagging in scene_parser."""

from scene_parser import get_scene_animations

CODE = '''from manim import *

class TextScene(Scene):
    def construct(self):
        t = Text("I make ideas move.", font_size=56)
        short = Text("Hello Manim").to_edge(UP)
        eq = MathTex(r"\\frac{a}{b} = c")
        self.play(Write(t))
        self.play(Write(short), FadeIn(eq))
        self.play(Write(Text("A rather long inline title")))
        self.play(AddTextLetterByLetter(short))
        self.play(Write(eq), run_time=3)
        self.play(Write(t, run_time=0.5))
        self.play(DrawBorderThenFill(Square()))
        self.play(Succession(FadeIn(short), FadeOut(short)))
        self.play(LaggedStart(FadeIn(short), FadeIn(t), lag_ratio=0.5))
        self.play(short.animate.shift(UP))
        for _ in range(3):
            self.play(Indicate(short))
            for item in [1, 2]:
                self.wait(0.5)
        while True:
            self.play(FadeOut(short))
            break
        for mob in things:
            self.play(FadeIn(mob))
        self.wait()
'''


def steps():
    return get_scene_animations(CODE)["TextScene"]


def by_line(line):
    return next(step for step in steps() if step["line"] == line)


def test_write_run_time_follows_glyph_count():
    # "I make ideas move." has 15 glyphs -> Manim's Write runs 2s.
    assert by_line(8)["duration"] == 2.0
    assert by_line(8)["estimated"] is True
    # 10 glyphs -> 1s; the play lasts as long as its longest animation.
    assert by_line(9)["duration"] == 1.0
    assert by_line(10)["duration"] == 2.0


def test_letter_by_letter_and_fixed_defaults():
    assert by_line(11)["duration"] == 1.0  # 10 chars * 0.1s
    assert by_line(14)["duration"] == 2.0  # DrawBorderThenFill
    assert by_line(15)["duration"] == 2.0  # Succession sums
    assert by_line(16)["duration"] == 1.5  # LaggedStart, 2 anims, lag 0.5
    assert by_line(17)["duration"] == 1.0  # .animate


def test_explicit_run_time_wins_and_is_not_estimated():
    assert by_line(12) == {"type": "play", "label": "Write(eq)", "line": 12, "duration": 3.0}
    assert by_line(13)["duration"] == 0.5


def test_loops_are_tagged_with_repeat_counts():
    assert by_line(19)["repeat"] == 3 and by_line(19)["loop_line"] == 18
    assert by_line(21)["repeat"] == 6 and by_line(21)["loop_line"] == 18
    assert by_line(23)["repeat"] is None and by_line(23)["loop_line"] == 22
    assert by_line(26)["repeat"] is None
    assert "repeat" not in by_line(27)
    assert "repeat" not in by_line(8)


def test_loops_and_estimates_work_with_aliased_nested_and_slide_scenes():
    code = '''from manim import Scene as S, Text, Write, FadeIn
from manim_slides import Slide

class Aliased(S):
    def construct(self):
        t = Text("I make ideas move.")
        for _ in range(2):
            self.play(Write(t))

if True:
    class Nested(S):
        def construct(self):
            self.play(FadeIn(Text("x")), run_time=3)

class Deck(Slide):
    def construct(self):
        while True:
            self.wait(0.5)
'''
    anims = get_scene_animations(code)
    assert anims["Aliased"] == [
        {"type": "play", "label": "Write(t)", "line": 8, "duration": 2.0, "estimated": True, "repeat": 2, "loop_line": 7}
    ]
    assert anims["Nested"] == [{"type": "play", "label": "FadeIn(Text('x'))", "line": 13, "duration": 3.0}]
    assert anims["Deck"][0]["repeat"] is None and anims["Deck"][0]["loop_line"] == 17
