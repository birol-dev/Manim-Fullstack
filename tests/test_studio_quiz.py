"""A quiz with several questions in one video: schema, limits, fitting and a real export."""

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from studio import registry
from studio.templates.quiz import schema as quiz
from studio.templates.quiz.schema import MAX_QUESTIONS, Params, label_for

FIRST = {
    "label": "Question 3 of 10",
    "question": "Which planet is known as the Red Planet?",
    "options": [{"text": "Venus"}, {"text": "Mars"}, {"text": "Jupiter"}, {"text": "Mercury"}],
    "correct": 2,
    "think_seconds": 8,
    "explanation": "Iron oxide, or rust, on its surface gives Mars its red color.",
}

MORE = [
    {
        "question": "What is the largest ocean on Earth?",
        "options": [{"text": "Atlantic"}, {"text": "Indian"}, {"text": "Pacific"}, {"text": "Arctic"}],
        "correct": 3,
        "explanation": "The Pacific covers about a third of Earth, more than all the land together.",
    },
    {
        "question": "How many sides does a hexagon have?",
        "options": [{"text": "Five"}, {"text": "Six"}, {"text": "Seven"}, {"text": "Eight"}],
        "correct": 2,
        "explanation": "Hexa means six. A honeycomb cell is a hexagon.",
    },
    {
        "question": "What do plants take in from the air to make food?",
        "options": [{"text": "Oxygen"}, {"text": "Nitrogen"}, {"text": "Carbon dioxide"}, {"text": "Hydrogen"}],
        "correct": 3,
        "explanation": "Plants use sunlight, water and carbon dioxide, and give out oxygen.",
    },
]

SIXTEEN_NINE = 128 / 9


def test_a_single_question_keeps_every_field_and_its_effect():
    params = Params(**FIRST)
    values = params.model_dump()
    for key in ("label", "question", "options", "correct", "explanation", "think_seconds"):
        assert values[key] == FIRST[key]
    assert values["questions"] == []
    assert label_for(1, 1, FIRST["label"]) == FIRST["label"]
    # Every old gallery card still loads as one question.
    old_cards = [preset for preset in quiz.PRESETS if preset.id != "five-question-quiz"]
    assert old_cards
    for preset in old_cards:
        loaded = Params(**preset.params)
        assert loaded.questions == [] and loaded.label == preset.params["label"]


def test_the_counter_counts_by_itself_when_there_are_several_questions():
    assert label_for(1, 5, "") == "Question 1 of 5"
    assert label_for(2, 5, "Typed by mistake") == "Question 2 of 5"
    assert label_for(5, 5, "") == "Question 5 of 5"
    assert label_for(1, 1, "") == ""


def test_twelve_questions_are_allowed_and_a_thirteenth_is_refused_in_plain_words():
    twelve = {**FIRST, "questions": [dict(question) for question in MORE * 4][:MAX_QUESTIONS - 1]}
    _, model, _ = registry.validate_job("quiz", twelve, {"aspect": "16:9"})
    assert len(model.questions) == 11

    thirteen = {**FIRST, "questions": [dict(question) for question in MORE * 4]}
    with pytest.raises(registry.TemplateError) as info:
        registry.validate_job("quiz", thirteen, {"aspect": "16:9"})
    (error,) = info.value.errors
    assert error["field"] == "params.questions"
    assert "up to 12 questions" in error["message"] and "another video" in error["message"]


def test_a_further_question_must_point_at_one_of_its_own_answers():
    broken = {**FIRST, "questions": [{"question": "Is this right?", "options": ["Yes", "No"], "correct": 3}]}
    with pytest.raises(registry.TemplateError) as info:
        registry.validate_job("quiz", broken, {"aspect": "16:9"})
    (error,) = info.value.errors
    assert error["field"] == "params.questions.0.correct"
    assert "only 2 answers" in error["message"]


def test_the_new_card_is_a_real_five_question_quiz():
    card = next(preset for preset in quiz.PRESETS if preset.id == "five-question-quiz")
    params = Params(**card.params)
    questions = [params, *params.questions]
    assert len(questions) == 5 and card.params["label"] == ""
    answers = ["Mars", "Pacific", "Six", "Carbon dioxide", "Leonardo da Vinci"]
    for item, answer in zip(questions, answers):
        assert len(item.options) == 4
        assert item.options[item.correct - 1].text == answer
        assert item.explanation and len(item.explanation) <= 120
        assert len(item.question) <= 120
        assert all(len(option.text) <= 40 for option in item.options)


LONG_QUESTION = ("Which of these activities would help our neighbourhood bring people together and make our "
                 "community feel more welcoming?")
LONG_OPTIONS = [
    "A neighbourhood clean-up and picnic day.",
    "Organise a celebration for neighbours",
    "Invite all neighbours to share a meal",
    "Welcome every new family to our street",
]
LONG_EXPLANATION = ("A community event lets people meet, talk and help each other, so neighbours become friends "
                    "and everyone feels at home.")


def test_the_layout_test_strings_use_the_schema_limits():
    assert len(LONG_QUESTION) == 120
    assert max(len(option) for option in LONG_OPTIONS) == 40
    assert len(LONG_OPTIONS[0]) == 40
    assert len(LONG_EXPLANATION) <= 120


@pytest.mark.parametrize("dimensions", [(SIXTEEN_NINE, 8), (8, SIXTEEN_NINE), (8, 8), (8, 10)],
                         ids=["16:9", "9:16", "1:1", "4:5"])
@pytest.mark.parametrize("answer_count", [4, 2])
def test_maximum_length_questions_and_answers_fit_around_the_logo(dimensions, answer_count):
    pytest.importorskip("manim")
    from manim import tempconfig

    from studio.kit import fonts
    from studio.kit.layout import Layout
    from studio.kit.scene import Theme
    from studio.kit.text import fit_text
    from studio.templates.quiz.helpers import lines_at
    from studio.templates.quiz.planner import plan_layout
    from studio.themes import theme_tokens

    with tempconfig({"media_dir": str(Path(tempfile.gettempdir()) / "quiz-layout-media")}):
        fonts.register_bundled()
        layout = Layout(*dimensions)
        layout.bottom += 13 * layout.unit  # reserve_logo_band for the bottom-left logo
        theme = Theme(theme_tokens("midnight"))
        options = LONG_OPTIONS[:answer_count]
        plan = plan_layout(layout, layout.safe, theme, question=LONG_QUESTION, options=options,
                           explanation=LONG_EXPLANATION, has_label=True)
        assert plan.overflow == 0
        cards_bottom = plan.opt_top - plan.rows * plan.card_h - (plan.rows - 1) * plan.gap
        assert cards_bottom >= plan.bottom_y + plan.bottom_h / 2 - 0.01

        question = fit_text(LONG_QUESTION, width=plan.q_width, size=plan.q_size, min_size=plan.q_size,
                            max_lines=max(8, plan.q_lines), font=theme.font, weight=theme.display_weight)
        assert len(question.lines) == lines_at(LONG_QUESTION, plan.q_width, plan.q_size, theme.font,
                                               theme.display_weight)
        assert all(not line.original_text.endswith("…") for line in question.lines)
        for option in options:
            body = fit_text(option, width=plan.text_w, size=plan.opt_size, min_size=plan.opt_size,
                            max_lines=plan.opt_lines, font=theme.font, weight="SEMIBOLD")
            assert all(not line.original_text.endswith("…") for line in body.lines)
        explanation = fit_text(LONG_EXPLANATION, width=plan.e_text_w, size=plan.e_size, min_size=plan.e_size,
                               max_lines=plan.e_lines, font=theme.font)
        assert all(not line.original_text.endswith("…") for line in explanation.lines)


def _short_question(answer: str, index: int) -> dict:
    return {
        "question": f"Sample question number {index}?",
        "options": [{"text": "First answer"}, {"text": "Second answer"},
                    {"text": "Third answer"}, {"text": answer}],
        "correct": 4,
        "explanation": "A short explanation for the answer.",
    }


def test_a_long_quiz_has_a_scaling_estimate_and_enough_render_time(tmp_path):
    pytest.importorskip("manim")
    from studio.exports import ExportManager
    from studio.service import StudioService

    first = {"label": "", "question": "Sample question number 1?",
             "options": [{"text": "First answer"}, {"text": "Second answer"},
                         {"text": "Third answer"}, {"text": "Fourth answer"}],
             "correct": 4, "explanation": "A short explanation for the answer.", "think_seconds": 3}
    twelve = {**first, "questions": [_short_question(f"Answer {index}", index) for index in range(2, 13)]}
    service = StudioService(str(tmp_path / "ws"))
    # Other work may be adding bundled fonts or icons meanwhile; keep cache keys still.
    service._kit_fingerprint = service._icons_fingerprint = lambda: "frozen"
    try:
        one = service.preview_sync("quiz", first, {"aspect": "9:16"}, mode="storyboard")
        long = service.preview_sync("quiz", twelve, {"aspect": "9:16"}, mode="storyboard")
    finally:
        service.shutdown_sync()

    one_length = one["storyboard"]["length"]
    long_length = long["storyboard"]["length"]
    assert long_length == pytest.approx(12.5 * one_length, rel=0.08)
    # The editor shows this storyboard length, and the export plans with it.
    assert long["ms"] < service.preview_timeout * 1000
    record = {"_job": {"settings": {"aspect": "9:16"}}, "width": 480, "height": 854, "fps": 15}
    timeout = ExportManager._timeout_for(SimpleNamespace(base_timeout=None), record, long_length)
    assert timeout >= 120 + 4 * long_length - 0.01


def test_three_questions_export_one_real_video_with_a_nine_by_sixteen_storyboard(tmp_path):
    pytest.importorskip("manim")
    from executor import media_file_is_complete
    from studio.service import StudioService

    explanation = "A short explanation for the answer."
    first = {**FIRST, "label": "", "think_seconds": 3, "explanation": explanation}
    three = {**first, "questions": [dict(question, explanation=explanation) for question in MORE[:2]]}
    proof = Path(tempfile.gettempdir()) / "manim-studio-quiz-proof"
    proof.mkdir(parents=True, exist_ok=True)
    service = StudioService(str(tmp_path / "ws"))
    service._kit_fingerprint = service._icons_fingerprint = lambda: "frozen"
    try:
        one = service.preview_sync("quiz", first, {"aspect": "9:16"}, mode="storyboard")
        board = service.preview_sync("quiz", three, {"aspect": "9:16"}, mode="storyboard")
        storyboard = proof / "quiz-3-questions-9x16-storyboard.png"
        shutil.copyfile(board["path"], storyboard)
        assert storyboard.stat().st_size > 1000

        started = time.perf_counter()
        export = asyncio.run(service.start_export("quiz", three, {"aspect": "9:16"}, format="mp4",
                                                  quality="draft", title="Three question quiz"))
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            export = asyncio.run(service.get_export(export["id"]))
            if export["status"] in ("done", "failed", "cancelled"):
                break
            time.sleep(0.25)
        assert export["status"] == "done", export
        print(f"draft quiz export took {time.perf_counter() - started:.1f} s")
        path = Path(service.exports_dir) / export["filename"]
        assert media_file_is_complete(str(path))
        assert export["duration"] == pytest.approx(board["storyboard"]["length"], abs=0.5)
        assert board["storyboard"]["length"] == pytest.approx(3 * one["storyboard"]["length"], rel=0.15)
        if shutil.which("ffprobe"):
            probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                    "stream=width,height:format=duration", "-of", "json", str(path)],
                                   capture_output=True, text=True, timeout=30, check=True)
            probed = json.loads(probe.stdout)
            stream = probed["streams"][0]
            assert min(stream["width"], stream["height"]) == 480  # the lowest quality
            assert float(probed["format"]["duration"]) == pytest.approx(export["duration"], abs=0.2)
    finally:
        service.shutdown_sync()
