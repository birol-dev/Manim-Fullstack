"""Charts preserve labels, negative/zero data, locale numbers and every gallery card."""
import pytest
from pydantic import ValidationError

from studio import registry
from studio.numfmt import format_number
from studio.schema import ASPECTS
from studio.templates.chart.schema import META, PRESETS, Datum, Params
from studio.themes import THEMES


def test_chart_presets_and_plain_validation():
    assert len(PRESETS) == 3
    cards = next(s["cards"] for s in registry.catalog()["sections"] if s["id"] == "numbers")
    assert {c["id"] for c in cards if c["template"] == META.id} == {p.id for p in PRESETS}
    for preset in PRESETS:
        registry.validate_job(META.id, preset.params, preset.settings)
    Params(title="W" * 48, values=[{"label": "W" * 20, "value": 1_000_000}] * 12)
    for invalid in ({"title": "W" * 49}, {"values": [{"label": "W" * 21}] * 2},
                    {"decimals": -1}, {"decimals": 3}, {"chart_type": "area"}, {"accent": "red"}):
        with pytest.raises(ValidationError):
            Params(**invalid)
    for count in (0, 1, 13):
        with pytest.raises(ValidationError, match="Add between 2 and 12 labeled numbers"):
            Params(values=[{"label": "A"}] * count)
    with pytest.raises(ValidationError, match="Write a title"):
        Params(title=" ")
    with pytest.raises(ValidationError, match="Write a label"):
        Datum(label=" ")
    for value in (float("nan"), float("inf"), 1_000_001, -1_000_001):
        with pytest.raises(ValidationError, match="Use a number between"):
            Datum(label="A", value=value)
    with pytest.raises(ValidationError, match="Pie charts cannot show negative values"):
        Params(chart_type="pie", values=[{"label": "A", "value": -1}, {"label": "B", "value": 2}])
    with pytest.raises(ValidationError, match="above zero"):
        Params(chart_type="pie", values=[{"label": "A"}, {"label": "B"}])


@pytest.fixture
def make_scene(tmp_path):
    pytest.importorskip("manim")
    from manim import tempconfig
    from studio.compat import output_config
    from studio.formats import frame_size, pixel_size
    from studio.kit import runtime
    from studio.templates.chart.scene import Template

    def make(params, aspect="16:9", theme="clean", **settings):
        fw, fh = frame_size(*pixel_size(aspect, 480))
        runtime.set_job({"params": params, "settings": {"aspect": aspect, "theme": theme, **settings}, "mode": "video"})
        with tempconfig({**output_config(dry_run=True), "media_dir": str(tmp_path),
                         "frame_width": fw, "frame_height": fh, "verbosity": "ERROR"}):
            scene = Template()
            scene.setup()
        return scene
    yield make
    runtime.set_job(None)


def inside(mob, region):
    assert mob.get_left()[0] >= region.left - 1e-5
    assert mob.get_right()[0] <= region.right + 1e-5
    assert mob.get_top()[1] <= region.top + 1e-5
    assert mob.get_bottom()[1] >= region.bottom - 1e-5


def separated(a, b, gap=0):
    overlap_x = min(a.get_right()[0], b.get_right()[0]) - max(a.get_left()[0], b.get_left()[0])
    overlap_y = min(a.get_top()[1], b.get_top()[1]) - max(a.get_bottom()[1], b.get_bottom()[1])
    assert overlap_x <= -gap + 1e-5 or overlap_y <= -gap + 1e-5


@pytest.mark.parametrize("aspect", ASPECTS)
@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("kind", ["bars", "line", "pie"])
def test_chart_long_and_short_labels_have_real_room(make_scene, aspect, theme, kind):
    for count, word in ((12, "W" * 20), (2, "A")):
        data = [{"label": word, "value": (i - 6 if kind != "pie" else i) * 70000} for i in range(count)]
        scene = make_scene({"title": "W" * 48, "values": data, "chart_type": kind,
                            "accent": "#E11D48", "decimals": 2}, aspect, theme, safe_zone=True,
                           brand={"font": "JetBrains Mono", "accent": "#123456"})
        scene._compose()
        assert scene.accent == "#E11D48"
        inside(scene.heading, scene.layout.safe)
        assert "".join(line.original_text for line in scene.heading.lines) == "W" * 48
        assert scene.heading.font_size >= 24
        if count == 12:
            assert scene.uses_legend
        for index, (entry, row) in enumerate(zip(scene.entries, data)):
            inside(entry, scene.layout.safe)
            assert "".join(line.original_text for line in entry.words.lines) == word
            assert entry.words.font_size >= 24
            assert entry.number.size >= 24
            separated(entry.words, entry.number, .1)
            separated(entry.words, scene.heading, .1)
            separated(entry.number, scene.heading, .1)
            if scene.uses_legend:
                inside(entry, scene.legend_region)
                if scene.p.chart_type != "pie" or count > 6:
                    assert entry.words.get_bottom()[1] > entry.number.get_top()[1]
                assert entry.words.get_left()[0] - entry.marker.get_right()[0] >= .19
                separated(entry.marker, entry.words, .19)
                separated(entry.marker, entry.number)
                for mark in scene.marks:
                    if len(mark.get_all_points()):
                        separated(entry, mark, .1)
                separated(entry, scene.axes)
            assert entry.number.text_for(row["value"]) == format_number(row["value"], decimals=2)
            # Measure actual Pango glyphs and geometry, on every visible page.
            for other in next(page for page in scene.pages if entry in page):
                if other is entry:
                    continue
                separated(entry, other, .1)
        for mark in scene.marks:
            if len(mark.get_all_points()):
                inside(mark, scene.plot_region)
        for i, percent in enumerate(scene.percent_labels):
            inside(percent, scene.plot_region)
            for other in scene.percent_labels[i + 1:]:
                separated(percent, other, .1)


@pytest.mark.parametrize("aspect", ASPECTS)
@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.id)
def test_chart_cards_use_direct_labels_or_pie_swatches(make_scene, aspect, preset):
    from studio.templates.chart.parts import contrast
    scene = make_scene(preset.params, aspect, preset.settings["theme"])
    scene._compose()
    assert "Example" not in scene.p.title
    if scene.p.chart_type == "pie":
        assert scene.legend_side == (aspect == "16:9")
        assert len(scene.percent_labels) == len(scene.p.values)
        for entry in scene.entries:
            assert not entry.marker.submobjects  # Solid color swatch, no index glyphs.
            inside(entry, scene.legend_region)
        if scene.legend_side:
            assert scene.pie_center[1] == pytest.approx(scene.legend_region.center[1])
            assert scene.pie_radius > 2
        for percent in scene.percent_labels:
            color = scene.colors[percent.slice_index]
            for glyph in percent.family_members_with_points():
                assert contrast(str(glyph.get_fill_color()), color) >= 4.5
    else:
        assert not scene.uses_legend
        assert len(scene.pages) == 1
        assert scene.plot_region.height > scene.layout.safe.height * .50
        for words, number, mark, point in zip(scene.axis_labels, scene.counters, scene.marks, scene.points):
            assert words.get_center()[0] == pytest.approx(point[0], abs=.2)
            assert number.get_center()[0] == pytest.approx(point[0])
            assert words.get_top()[1] < scene.plot_region.bottom
            assert number.get_bottom()[1] > point[1]
            inside(number, scene.plot_region)
        if scene.p.chart_type == "line":
            assert scene.y_range[0] > 0
            assert all(segment.get_stroke_width() >= 4 for segment in scene.line_segments)
            assert scene.marks[0][-1].width >= .14
            # Months fit intact at the kit's minimum; no "Janu / ary" split.
            assert all(len(words.lines) == 1 for words in scene.axis_labels)
            import numpy as np
            for segment in scene.line_segments:
                for number in scene.counters:
                    samples = np.linspace(segment.get_start(), segment.get_end(), 200)
                    assert not any(number.get_left()[0] < x < number.get_right()[0]
                                   and number.get_bottom()[1] < y < number.get_top()[1]
                                   for x, y, _ in samples)
        else:
            assert scene.y_range[0] == 0
            assert len(set(scene.colors)) <= 2
            assert scene.colors[-1] == scene.accent


@pytest.mark.parametrize("aspect", ASPECTS)
@pytest.mark.parametrize("values", [[-100, -1, 0, 2], [-.001, 0, .001, 100], [-1_000_000, 0, 1_000_000]])
def test_negative_and_zero_bar_labels_stay_outside_bars_and_clear_of_axis(make_scene, aspect, values):
    scene = make_scene({"values": [{"label": f"Q{i + 1}", "value": v} for i, v in enumerate(values)]}, aspect)
    scene._compose()
    assert not scene.uses_legend
    for row, mark, number, words in zip(scene.p.values, scene.marks, scene.counters, scene.axis_labels):
        separated(number, mark, .14)
        separated(number, scene.baseline, .14)
        separated(number, words, .14)
        inside(number, scene.plot_region)
        if row.value < 0:
            assert number.get_top()[1] < mark.get_bottom()[1]
        else:
            assert number.get_bottom()[1] > mark.get_top()[1]
        # The actual counter updater keeps this gap during growth as well.
        for fraction in (0, .25, .5, 1):
            growing = mark.copy().stretch(max(.001, fraction), 1, about_point=mark.grow_from)
            number.set_value(row.value * fraction)
            scene._place_value(number, growing, -1 if row.value < 0 else 1)
            separated(number, growing, .14)
            separated(number, scene.baseline, .14)
            separated(number, words, .14)


@pytest.mark.parametrize("accent", ["#E11D48", "#123456", "#FFFF00", "#FFFFFF", "#000000", "#808080"])
@pytest.mark.parametrize("dark", [False, True])
def test_pie_palette_has_distinct_neighbors_and_readable_ink(accent, dark):
    from studio.templates.chart.parts import contrast, ink_on, slice_colors
    for count in range(2, 13):
        colors = slice_colors(accent, count, dark)
        assert len(set(colors)) == count
        for a, b in zip(colors, colors[1:] + colors[:1]):
            assert contrast(a, b) >= 1.5
            assert contrast(ink_on(a), a) >= 4.5


@pytest.mark.parametrize("aspect", ASPECTS)
def test_pie_zero_rows_do_not_break_visible_neighbors_or_whole_share(make_scene, aspect):
    from studio.templates.chart.parts import contrast
    data = [{"label": f"Choice {i}", "value": 1 if i % 3 == 0 else 0} for i in range(12)]
    scene = make_scene({"chart_type": "pie", "values": data}, aspect, "midnight", brand={"accent": "#FFFF00"})
    scene._compose()
    visible = [color for color, row in zip(scene.colors, data) if row["value"]]
    for a, b in zip(visible, visible[1:] + visible[:1]):
        assert contrast(a, b) >= 1.5
    scene = make_scene({"chart_type": "pie", "values": [
        {"label": "All", "value": 1}, {"label": "None", "value": 0}]}, aspect)
    scene._compose()
    assert [percent.original_text for percent in scene.percent_labels] == ["100%"]
    assert not scene.marks[1].submobjects


@pytest.mark.parametrize("values", [[.01, 10], [0, 10], [-4, -1], [-2, 3], [2, 2], [950, 1000]])
def test_line_range_fits_data_and_keeps_zero_when_nearby(make_scene, values):
    scene = make_scene({"chart_type": "line", "values": [{"label": str(i), "value": v} for i, v in enumerate(values)]})
    scene._compose()
    low, high = scene.y_range
    assert low <= min(values) <= max(values) <= high
    if min(values) >= 0 and min(values) <= (max(values) - min(values)) * .2:
        assert low == 0
    if min(values) > 0 and min(values) > (max(values) - min(values)) * .2:
        assert low > 0


@pytest.mark.parametrize("kind", ["bars", "line"])
@pytest.mark.parametrize("values", [[0, 0], [-4, -1], [-2, 0, 3], [2, 2]])
def test_chart_zero_and_negative_ranges_are_finite(make_scene, kind, values):
    import numpy as np
    scene = make_scene({"chart_type": kind, "values": [{"label": str(i), "value": v} for i, v in enumerate(values)]})
    scene._compose()
    assert all(np.isfinite(mark.get_all_points()).all() for mark in scene.marks)


@pytest.mark.parametrize("locale", ["en", "de", "tr", "pl"])
def test_chart_counter_uses_locale_and_reaches_its_value(make_scene, locale):
    scene = make_scene({"values": [{"label": "A", "value": -1234.5}, {"label": "B", "value": 0}],
                        "decimals": 1}, locale=locale)
    scene._compose()
    counter = scene.counters[0]
    tracker, _ = counter.counting(0, -1234.5)
    tracker.set_value(-617.25)
    counter.update(0)
    assert counter.value == pytest.approx(-617.25)
    assert counter._text == format_number(-617.25, decimals=1, locale=locale)
    counter.clear_updaters()
    counter.set_value(-1234.5)
    assert counter._text == format_number(-1234.5, decimals=1, locale=locale)


def test_chart_more_numbers_get_more_time(make_scene):
    lengths = []
    for count in (2, 12):
        scene = make_scene({"values": [{"label": f"Item {i}", "value": i} for i in range(count)]})
        scene.play = lambda *args, **kwargs: None
        scene.build()
        lengths.append(scene.target_length)
    assert lengths[0] < lengths[1]


def test_chart_real_poster_and_lowest_quality_movie(tmp_path):
    pytest.importorskip("manim")
    import json
    import shutil
    import subprocess
    from studio.dev import render_preview
    from studio.worker import _Child
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg checks the real draft movie")
    params = {"title": "Example *changes*", "values": [
        {"label": "Last month", "value": -2}, {"label": "This month", "value": 3}]}
    settings = {"aspect": "16:9", "sound": {"effects": False}}
    poster = tmp_path / "poster.png"
    render_preview(META.id, params, settings, "poster", str(poster), short=180,
                   media_dir=str(tmp_path / "preview-media"))
    assert poster.stat().st_size > 500
    movie = tmp_path / "draft.mp4"
    result = _Child(None).render({"id": 1, "width": 854, "height": 480,
        "media_dir": str(tmp_path / "movie-media"), "job": {"template": META.id,
        "mode": "motion", "max_duration": 20, "output": str(movie), "params": params,
        "settings": settings}})
    assert result["ok"], result
    streams = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_streams",
                                                  "-of", "json", str(movie)]))["streams"]
    video = next(stream for stream in streams if stream["codec_type"] == "video")
    assert (video["width"], video["height"], video["avg_frame_rate"]) == (854, 480, "15/1")
    assert float(video["duration"]) >= META.min_length
