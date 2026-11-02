"""Name strips: useful gallery defaults, full text, placement and a clean exit."""

import pytest
from pydantic import ValidationError

from studio import registry
from studio.schema import ASPECTS
from studio.templates.lower_third.schema import META, PRESETS, Params
from studio.themes import THEMES


def test_lower_third_presets_are_transparent_and_in_the_creator_gallery():
    assert len(PRESETS) == 3
    assert META.default_aspect == "16:9"
    assert {p.params["style"] for p in PRESETS} == {"panel", "block", "underline"}
    cards = next(s["cards"] for s in registry.catalog()["sections"] if s["id"] == "creator")
    assert {c["id"] for c in cards if c["template"] == META.id} == {p.id for p in PRESETS}
    for preset in PRESETS:
        _, _, settings = registry.validate_job(META.id, preset.params, preset.settings)
        assert settings.background.kind == "transparent"


@pytest.mark.parametrize("field,limit", [("name", 36), ("role", 48)])
def test_lower_third_text_limits(field, limit):
    Params(**{field: "W" * limit})
    with pytest.raises(ValidationError):
        Params(**{field: "W" * (limit + 1)})


@pytest.mark.parametrize("hold", [0, 26])
def test_lower_third_hold_limits(hold):
    with pytest.raises(ValidationError):
        Params(hold=hold)


def test_lower_third_plain_errors_and_whitespace():
    with pytest.raises(ValidationError, match="Write the name to show"):
        Params(name=" \n ")
    assert Params(name="Maya\nTorres", role="Product\ndesigner").name == "Maya Torres"
    for values in ({"side": "up"}, {"style": "unknown"}, {"accent": "blue"}, {"extra": 1}):
        with pytest.raises(ValidationError):
            Params(**values)


@pytest.fixture
def make_scene(tmp_path):
    pytest.importorskip("manim")
    from manim import tempconfig
    from studio.compat import output_config
    from studio.formats import frame_size, pixel_size
    from studio.kit import runtime
    from studio.templates.lower_third.scene import Template

    def make(params, aspect="16:9", theme="clean", **settings):
        width, height = pixel_size(aspect, 480)
        fw, fh = frame_size(width, height)
        runtime.set_job({"params": params, "settings": {"aspect": aspect, "theme": theme, **settings},
                         "mode": "video"})
        with tempconfig({**output_config(dry_run=True), "media_dir": str(tmp_path),
                         "frame_width": fw, "frame_height": fh, "verbosity": "ERROR",
                         "progress_bar": "none"}):
            scene = Template()
            scene.setup()
        return scene

    yield make
    runtime.set_job(None)


def _inside(inner, outer):
    assert inner.get_left()[0] >= outer.left - 1e-5
    assert inner.get_right()[0] <= outer.right + 1e-5
    assert inner.get_bottom()[1] >= outer.bottom - 1e-5
    assert inner.get_top()[1] <= outer.top + 1e-5


@pytest.mark.parametrize("aspect", ASPECTS)
@pytest.mark.parametrize("style", ["panel", "block", "underline"])
@pytest.mark.parametrize("theme", THEMES)
def test_lower_third_maximum_text_fits_every_shape_style_and_theme(make_scene, aspect, style, theme):
    for side, short in (("left", False), ("center", True), ("right", False)):
        name = "W" * 36 if not short else "M"
        role = "Senior workshop leader and community coordinator" if not short else ""
        assert len(role) <= 48
        scene = make_scene({"name": name, "role": role, "style": style, "side": side}, aspect, theme,
                           safe_zone=True, brand={"accent": "#FDE047"})
        strip = scene._compose()
        _inside(strip, scene.layout.safe)
        for text, source in ((strip.name, name), (strip.role, role)):
            if text is not None:
                shown = " ".join(line.original_text for line in text.lines)
                assert shown.replace(" ", "") == source.replace(" ", "")
                assert text.get_left()[0] >= strip.card.get_left()[0]
                assert text.get_right()[0] <= strip.card.get_right()[0]
        if strip.role is not None:
            assert strip.name.get_bottom()[1] - strip.role.get_top()[1] >= 0.15 * strip.name.height
        if strip.marker is not None:
            assert strip.marker.get_right()[0] < strip.name.get_left()[0]
        if strip.bar is not None:
            assert strip.bar.get_top()[1] < strip.text.get_bottom()[1]
        assert strip.card.get_top()[1] < scene.layout.safe.center[1]


def test_lower_third_timing_follows_hold_and_removes_every_piece(make_scene):
    lengths = []
    for hold in (1, 25):
        scene = make_scene({"name": "Maya", "hold": hold}, ending="cut")
        strip = scene._compose()
        elapsed = []
        scene.play = lambda *animations, **kwargs: elapsed.append(kwargs["run_time"])
        scene.wait = lambda seconds: elapsed.append(seconds)
        # Reproduce the intro's separate roots; the exit must remove all of them.
        scene.add(strip.card_group, strip.name, strip.marker)
        scene._play(strip)
        assert sum(elapsed) == pytest.approx(scene.target_length)
        assert elapsed[1] == pytest.approx(hold)
        assert not {id(m) for root in scene.mobjects for m in root.get_family()} & {
            id(m) for m in strip.get_family()}
        lengths.append(scene.target_length)
    assert lengths[1] - lengths[0] == pytest.approx(24)


def test_lower_third_own_accent_wins_over_brand(make_scene):
    from studio.templates.lower_third.parts import Palette, contrast
    scene = make_scene({"name": "Maya", "accent": "#FFFFFF"},
                       brand={"accent": "#123456", "font": "JetBrains Mono"})
    palette = Palette(scene.theme, scene.p.accent)
    assert palette.accent == "#FFFFFF"
    assert palette.font == "JetBrains Mono"
    assert contrast(palette.on_accent, palette.accent) >= 4.5


@pytest.mark.parametrize("aspect", ASPECTS)
@pytest.mark.parametrize("style", ["panel", "block", "underline"])
@pytest.mark.parametrize("preset", [p for p in PRESETS if p.params.get("role")])
def test_lower_third_gallery_lines_have_measured_breathing_room(make_scene, aspect, style, preset):
    scene = make_scene({**preset.params, "style": style}, aspect)
    strip = scene._compose()
    gap = strip.name.get_bottom()[1] - strip.role.get_top()[1]
    assert gap >= .15 * strip.name.height
