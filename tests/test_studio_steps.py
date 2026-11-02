"""Steps template: limits, presets, geometry in every aspect, timing and the poster moment."""

import pytest

pytest.importorskip("manim")

from manim import tempconfig  # noqa: E402
from manim.utils.exceptions import EndSceneEarlyException  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from studio import registry  # noqa: E402
from studio.kit import runtime  # noqa: E402
from studio.kit.layout import Layout  # noqa: E402
from studio.templates.steps.scene import Template  # noqa: E402
from studio.templates.steps.schema import META, PRESETS, Params, Step  # noqa: E402

DIMENSIONS = [(128 / 9, 8), (8, 128 / 9), (8, 8), (8, 10)]
STYLES = ["numbered", "checklist", "timeline"]

# Seven items, every typed field at its longest allowed content.
LONG_STEPS = [
    {"text": "Collect worksheets and pencils for class", "detail": "Bring your printed sheet",
     "time": "09:30a", "icon": "notebook"},
    {"text": "Read the question on the classroom board", "detail": "Work quietly on your own",
     "time": "09:45a", "icon": "book-open"},
    {"text": "Confirm the room and welcome the speaker", "detail": "Keep stirring until warm",
     "time": "10:00a", "icon": "users"},
    {"text": "Check the oven and prepare a baking tray", "detail": "Keep the opening concise",
     "time": "10:15a", "icon": "cooking-pot"},
    {"text": "Write down three key points to share now", "detail": "Hand in sheets by twelve",
     "time": "10:30a", "icon": "pencil"},
    {"text": "Share the meeting notes with every team.", "detail": "Leave notes by the door.",
     "time": "10:45a", "icon": "clipboard-check"},
    {"text": "Pack all the boxes and check the address", "detail": "Check every item on list",
     "time": "11:00a", "icon": "package"},
]
LONG_TITLE = {"kicker": "Monday morning team agenda", "title": "Everything we need to cover this morning"}


def _params(style="timeline", steps=None, highlight=3, **more):
    return {**LONG_TITLE, "style": style, "highlight": highlight, "steps": steps or LONG_STEPS, **more}


@pytest.fixture(scope="module")
def text_media(tmp_path_factory):
    return tmp_path_factory.mktemp("steps-text")


@pytest.fixture
def make_scene(text_media):
    def make(*, params=None, settings=None, mode="video"):
        runtime.set_job({"params": params or _params(), "settings": settings or {"theme": "clean"},
                         "mode": mode, "max_duration": 30})
        scene = Template()
        scene.setup()
        scene._prepare()
        return scene

    with tempconfig({"media_dir": str(text_media), "frame_width": 8, "frame_height": 8,
                     "dry_run": True, "skip_animations": True, "verbosity": "ERROR",
                     "progress_bar": "none"}):
        yield make
    runtime.set_job(None)


# -- schema ------------------------------------------------------------------
def test_the_stress_content_is_the_longest_allowed():
    assert all(len(step["text"]) == 40 and len(step["detail"]) == 24 and len(step["time"]) == 6 for step in LONG_STEPS)
    assert len(LONG_TITLE["title"]) == 40
    assert len(LONG_TITLE["kicker"]) == 26


def test_limits_are_enforced_and_cover_the_layout_tests():
    Step(text="x" * 40, detail="y" * 24, time="12:00")
    for field, limit in (("text", 40), ("detail", 24), ("time", 6)):
        with pytest.raises(ValidationError):
            Step(**{"text": "A step", field: "z" * (limit + 1)})
    for field, limit in (("title", 40), ("kicker", 26)):
        with pytest.raises(ValidationError):
            Params(**{field: "z" * (limit + 1)})
    with pytest.raises(ValidationError):
        Step(text="   ")


def test_two_to_seven_items_are_required():
    two = [{"text": f"Step {i}"} for i in range(2)]
    Params(steps=two)
    with pytest.raises(ValidationError):
        Params(steps=two[:1])
    with pytest.raises(ValidationError):
        Params(steps=[{"text": f"Step {i}"} for i in range(8)])


def test_every_preset_validates_and_the_four_show_the_three_styles():
    assert len(PRESETS) == 4
    assert len({p.id for p in PRESETS}) == len(PRESETS)
    assert {p.params["style"] for p in PRESETS} == set(STYLES)
    for preset in PRESETS:
        assert 2 <= len(preset.params["steps"]) <= 7
        registry.validate_job("steps", preset.params, {**preset.settings})
        assert registry.get_template("steps").meta.category == "teach"
    schedule = next(p for p in PRESETS if p.id == "event-schedule")
    assert schedule.settings["aspect"] == "9:16"


def test_highlight_must_point_at_a_real_step():
    steps = [{"text": "One"}, {"text": "Two"}]
    Params(steps=steps, highlight=2)
    with pytest.raises(ValidationError):
        Params(steps=steps, highlight=3)


# -- geometry ----------------------------------------------------------------
@pytest.mark.parametrize("style", STYLES)
@pytest.mark.parametrize("dimensions", DIMENSIONS)
def test_seven_long_steps_stay_inside_the_safe_area_without_overlapping(dimensions, style, make_scene):
    scene = make_scene(params=_params(style=style))
    scene.layout = Layout(*dimensions)
    header, rows = scene._compose()
    safe = scene.layout.safe
    eps = 0.02

    assert len(rows) == 7
    assert header.get_top()[1] <= safe.top + eps
    assert header.get_left()[0] >= safe.left - eps
    assert header.get_right()[0] <= safe.right + eps
    assert header.get_bottom()[1] > rows[0].get_top()[1]

    for index, row in enumerate(rows):
        assert not row.cut
        assert row.text.font_size >= 24 - 1e-6
        if row.detail is not None:
            assert row.detail.font_size >= 24 - 1e-6
        shown = " ".join(line.original_text for line in row.text.lines)
        step = scene.steps[index]
        assert shown == (f"{step.text} · {step.detail}" if row.compact_detail else step.text)
        for mob in (row.text, row.detail, row.marker, row.icon, row.time, row.card):
            if mob is None:
                continue
            assert mob.get_left()[0] >= safe.left - eps
            assert mob.get_right()[0] <= safe.right + eps
            assert mob.get_top()[1] <= safe.top + eps
            assert mob.get_bottom()[1] >= safe.bottom - eps
            # A VGroup's .font_size is just metadata: row.scale() used to leave
            # it unchanged while shrinking all of its real Text children.
            for line in getattr(mob, "lines", [mob]):
                if hasattr(line, "font_size"):
                    assert line.font_size >= 24 - 1e-6
        assert row.text.get_left()[0] > row.marker.get_right()[0]
        if row.detail is not None:
            assert row.detail.get_left()[0] == pytest.approx(row.text.get_left()[0])
            assert row.detail.get_top()[1] < row.text.get_bottom()[1]
        if row.card is not None:
            assert row.card.get_left()[0] > row.marker.get_right()[0]
            assert row.text.get_left()[0] > row.card.get_left()[0] + 0.05
            if style == "timeline" and row.time is not None and not row.compact_detail and dimensions[0] > dimensions[1] * 0.7:
                assert row.time.get_right()[0] < row.card.get_left()[0]
        if row.segment is not None:
            rail = row.segment.get_x()
            for mob in (row.text, row.detail):
                if mob is not None:
                    assert mob.get_left()[0] > rail + 0.1
        if row.time is not None:
            for mob in (row.text, row.detail):
                if mob is None:
                    continue
                for line in mob.lines:
                    stamp = row.time
                    assert (stamp.get_left()[0] >= line.get_right()[0] + 0.025
                            or stamp.get_right()[0] <= line.get_left()[0] - 0.025
                            or stamp.get_top()[1] <= line.get_bottom()[1] - 0.025
                            or stamp.get_bottom()[1] >= line.get_top()[1] + 0.025)

    for upper, lower in zip(rows, rows[1:]):
        assert upper.get_bottom()[1] >= lower.get_top()[1] - eps


@pytest.mark.parametrize("style", STYLES)
def test_the_safe_zone_is_honoured_when_enabled(style, make_scene):
    scene = make_scene(params=_params(style=style, steps=LONG_STEPS[:4], highlight=2),
                       settings={"theme": "clean", "safe_zone": True})
    scene.layout = Layout(8, 128 / 9, safe_zone=True)
    _, rows = scene._compose()
    safe = scene.layout.safe
    episodes = [row.card for row in rows if row.card is not None]
    assert episodes, "the highlighted row needs its card"
    for row in rows:
        assert row.get_right()[0] <= safe.right + 0.02
        assert row.get_bottom()[1] >= safe.bottom - 0.02
        assert row.get_left()[0] >= safe.left - 0.02


def test_a_highlighted_row_has_a_card_and_other_rows_do_not(make_scene):
    scene = make_scene(params=_params(style="numbered", steps=LONG_STEPS[:4], highlight=2))
    scene.layout = Layout(8, 8)
    _, rows = scene._compose()
    assert [row.card is not None for row in rows] == [False, True, False, False]


@pytest.mark.parametrize("dimensions", DIMENSIONS)
@pytest.mark.parametrize("count", [2, 4, 5])
def test_short_lists_balance_the_header_and_body(dimensions, count, make_scene):
    scene = make_scene(params={"title": "Our next steps", "kicker": "Team workshop",
                               "steps": [{"text": "Discuss our next steps", "detail": "Share one idea"}] * count})
    scene.layout = Layout(*dimensions)
    header, rows = scene._compose()
    safe = scene.layout.safe
    top_space = safe.top - header.get_top()[1]
    bottom_space = rows[-1].get_bottom()[1] - safe.bottom
    assert top_space >= 0.12 - 1e-6
    assert top_space == pytest.approx(bottom_space, abs=0.02)
    assert min(line.font_size for row in rows for line in row.text.lines) >= 32


@pytest.mark.parametrize("theme", ["clean", "midnight"])
def test_highlight_separates_the_rail_time_and_content(theme, make_scene):
    from studio.templates.steps.parts import contrast

    preset = next(p for p in PRESETS if p.id == "meeting-agenda")
    scene = make_scene(params=preset.params, settings={"theme": theme})
    scene.layout = Layout(128 / 9, 8)
    _, rows = scene._compose()
    row = rows[1]
    assert row.time.get_right()[0] < row.marker.get_left()[0]
    assert row.marker.get_right()[0] < row.card.get_left()[0] < row.text.get_left()[0]
    assert row.card.get_fill_opacity() >= 0.1
    assert row.card.get_stroke_opacity() >= 0.4
    assert contrast(scene.pal.text, scene.pal.bg) >= 7


def test_unbroken_text_wraps_without_shrinking_the_type(make_scene):
    from studio.templates.steps.parts import full_text

    scene = make_scene()
    mob = full_text("W" * 40, width=5.5, size=24, min_size=24, font=scene.pal.font)
    assert mob.width <= 5.5
    assert "".join(line.original_text for line in mob.lines) == "W" * 40
    assert min(line.font_size for line in mob.lines) >= 24 - 1e-6


@pytest.mark.parametrize("style", STYLES)
def test_empty_optional_text_and_header_keep_the_list_centred(style, make_scene):
    scene = make_scene(params={"title": "", "kicker": "", "style": style,
                               "steps": [{"text": "Welcome", "time": "09:30", "icon": "users"},
                                         {"text": "Make a plan"}]})
    scene.layout = Layout(128 / 9, 8)
    header, rows = scene._compose()
    assert not len(header)
    assert (rows[0].get_top()[1] + rows[-1].get_bottom()[1]) / 2 == pytest.approx(0)
    if style != "timeline":
        assert rows[0].time.get_right()[0] < rows[0].icon.get_left()[0]
    assert scene._plan()["intro"] == 0


# -- timing and motion -------------------------------------------------------
def test_the_content_sets_a_longer_length_for_more_steps(make_scene):
    three = make_scene(params=_params(steps=LONG_STEPS[:3], highlight=0))
    seven = make_scene(params=_params(steps=LONG_STEPS, highlight=0))
    three._plan()
    seven._plan()
    assert META.min_length <= three.target_length <= META.max_length
    assert three.target_length < seven.target_length
    assert seven.target_length <= META.max_length


def test_a_requested_length_wins_and_the_pauses_are_scaled(make_scene):
    scene = make_scene(params=_params(), settings={"theme": "clean", "length": 12})
    plan = scene._plan()
    assert scene.target_length == 12
    assert sum(plan["reads"]) < sum(scene.motion.reading_time(f"{s.text} {s.detail}".strip(), minimum=0.8)
                                    for s in scene.steps)


def test_the_poster_moment_shows_the_full_list_and_every_tick(make_scene):
    scene = make_scene(params=_params(style="checklist", steps=LONG_STEPS[:5], highlight=0))
    seen = {}

    def probe():
        seen["rows"] = scene.visible_rows
        seen["ticked"] = scene.ticked
        raise EndSceneEarlyException()

    scene.poster = probe
    with pytest.raises(EndSceneEarlyException):
        scene.build()
    assert seen == {"rows": 5, "ticked": 5}


def test_numbered_rows_do_not_tick(make_scene):
    scene = make_scene(params=_params(style="numbered", steps=LONG_STEPS[:4], highlight=0))
    seen = {}

    def probe():
        seen["rows"] = scene.visible_rows
        seen["ticked"] = scene.ticked
        raise EndSceneEarlyException()

    scene.poster = probe
    with pytest.raises(EndSceneEarlyException):
        scene.build()
    assert seen == {"rows": 4, "ticked": 0}


@pytest.mark.parametrize("style", STYLES)
@pytest.mark.parametrize("length", [6, 12])
def test_short_requested_lengths_budget_every_beat(style, length, make_scene):
    scene = make_scene(params=_params(style=style), settings={"length": length, "ending": "fade"})
    plan = scene._plan()
    total = (plan["intro"] + 7 * (plan["enter"] + plan["tick"]) + sum(plan["reads"])
             + plan["hold"] + scene.motion.exit + 0.15)
    assert total <= length + 1e-6
    assert min(plan["reads"]) > 0


@pytest.mark.parametrize("style,energy", [("numbered", "normal"), ("timeline", "calm"),
                                          ("checklist", "punchy")])
def test_cues_follow_the_real_step_landings(style, energy, tmp_path):
    from math import ceil

    runtime.set_job({"mode": "video", "params": _params(style=style), "settings": {"energy": energy}})
    try:
        with tempconfig({"dry_run": True, "media_dir": str(tmp_path), "verbosity": "ERROR",
                         "progress_bar": "none", "pixel_width": 192, "pixel_height": 108,
                         "frame_width": 128 / 9, "frame_height": 8, "frame_rate": 30}):
            scene = Template()
            scene.render()
            plan = scene.plan
            frame = lambda t: ceil(t * 30 - 1e-7) / 30
            at = frame(plan["intro"])
            expected = []
            for read in plan["reads"]:
                at += frame(plan["enter"])
                expected.append(at + (plan["tick"] * 0.7 if style == "checklist" else 0))
                if style == "checklist":
                    at += frame(plan["tick"])
                # Cairo's frozen-frame waits use int(duration * fps), whereas
                # animated entrances sample np.arange and round up a frame.
                at += int(read * 30 + 1e-7) / 30
            cues = scene._sound_cues
            assert [name for name, _ in cues] == ["tick" if style == "checklist" else "pop"] * 7
            assert [at for _, at in cues] == pytest.approx(expected, abs=0.04)
            assert all(b - a > 1 for a, b in zip(expected, expected[1:]))
            assert cues[-1][1] < scene.elapsed
    finally:
        runtime.set_job(None)


@pytest.mark.parametrize("mode,disabled", [("poster", False), ("storyboard", False), ("video", True)])
def test_step_cues_are_silent_for_stills_and_disabled_effects(mode, disabled, tmp_path):
    runtime.set_job({"mode": mode, "params": _params(style="checklist", steps=LONG_STEPS[:2], highlight=0),
                     "settings": {"sound": {"effects": not disabled}}})
    try:
        with tempconfig({"dry_run": True, "media_dir": str(tmp_path), "verbosity": "ERROR",
                         "progress_bar": "none", "frame_width": 128 / 9, "frame_height": 8,
                         "pixel_width": 192, "pixel_height": 108}):
            scene = Template()
            scene.render()
            assert scene._sound_cues == []
    finally:
        runtime.set_job(None)
