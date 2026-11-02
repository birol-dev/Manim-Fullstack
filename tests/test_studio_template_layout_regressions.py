"""Content-fitting regressions for the five social templates (real Manim)."""

import pytest

pytest.importorskip("manim")

from studio.kit import fonts
from studio.kit.layout import Layout
from studio.kit.scene import Theme
from studio.templates.announcement.blocks import Palette, headline
from studio.templates.quiz.planner import plan_layout
from studio.themes import theme_tokens


def test_sale_headline_keeps_every_word_with_a_small_height_budget(tmp_path):
    from manim import tempconfig

    with tempconfig({"media_dir": str(tmp_path)}):
        fonts.register_bundled()
        text = headline("Summer *sale* on everything", Palette(Theme(theme_tokens("pop"))),
                        width=7.04, height=0.5, size=72, min_size=34, max_lines=3)
        shown = " ".join(line.original_text for line in text.lines)
        assert shown == "SUMMER SALE ON EVERYTHING"
        assert text.width <= 7.04 + 0.01


@pytest.mark.parametrize("dimensions", [(128 / 9, 8), (8, 128 / 9), (8, 8), (8, 10)])
def test_long_quiz_answers_leave_space_for_the_timer(dimensions, tmp_path):
    """The explanation may use the next screen; answers must fit the thinking screen."""
    from manim import tempconfig

    with tempconfig({"media_dir": str(tmp_path)}):
        fonts.register_bundled()
        layout = Layout(*dimensions)
        plan = plan_layout(
            layout, layout.safe, Theme(theme_tokens("midnight")),
            question=("Which of these activities would help our neighbourhood bring people together "
                      "and make the community a welcoming place? W"),
            options=["Organise a celebration for everyone Orga",
                     "Invite neighbours to share their stories",
                     "Start a community garden together Start!",
                     "Welcome new families to the neighbourhoo"],
            explanation="", has_label=True,
        )
        assert plan.overflow == 0
        cards_bottom = plan.opt_top - plan.rows * plan.card_h - (plan.rows - 1) * plan.gap
        assert cards_bottom >= plan.bottom_y + plan.bottom_h / 2 - 0.01
        assert min(plan.q_size, plan.opt_size) >= 24


def test_a_word_longer_than_the_line_shrinks_to_fit(tmp_path):
    from manim import tempconfig

    from studio.kit.text import fit_text

    with tempconfig({"media_dir": str(tmp_path)}):
        fonts.register_bundled()
        text = fit_text("Supercalifragilisticexpialidocious", width=4, size=48, min_size=24, max_lines=3)
        assert text.width <= 4 + 0.01


def test_emphasis_keeps_punctuation_and_part_words_attached(tmp_path):
    from manim import tempconfig

    from studio.kit.text import fit_text

    with tempconfig({"media_dir": str(tmp_path)}):
        fonts.register_bundled()
        text = fit_text("Save *today*! Kadı*köy* opens", width=50, emphasis_color="#FF0000", color="#FFFFFF")
        assert [line.original_text for line in text.lines] == ["Save today! Kadıköy opens"]
        red = "".join("R" if glyph.get_fill_color().to_hex() == "#FF0000" else "." for glyph in text.lines[0])
        assert red.replace(".", " ").split() == ["RRRRR", "RRR"]  # "today" and "köy", not "!" or "Kadı"


def test_svg_photos_render_as_vectors_inside_their_circle(tmp_path):
    from manim import tempconfig

    from studio.kit import media

    logo = tmp_path / "logo.svg"
    logo.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
                    '<rect width="10" height="10" fill="#2f6fed"/></svg>', encoding="utf-8")
    with tempconfig({"media_dir": str(tmp_path)}):
        mob = media.image(str(logo), height=2, shape="circle")
        assert mob.height == pytest.approx(1.4, abs=0.01)  # the square fits inside a circle of 2
