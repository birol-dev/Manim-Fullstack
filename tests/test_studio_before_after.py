"""Picture reveals: full labels, photo crops and every mask direction, including alpha."""

import pytest
import json
import shutil
import subprocess
from pydantic import ValidationError

from studio import registry
from studio.schema import ASPECTS
from studio.templates.before_after.schema import META, PRESETS, Params
from studio.themes import THEMES


def test_before_after_gallery_has_three_valid_cards_without_external_pictures():
    assert len(PRESETS) == 3
    cards = next(s["cards"] for s in registry.catalog()["sections"] if s["id"] == "creator")
    assert len([c for c in cards if c["template"] == META.id]) == 3
    for preset in PRESETS:
        _, params, _ = registry.validate_job(META.id, preset.params, preset.settings)
        assert params.before is None and params.after is None


@pytest.mark.parametrize("field,limit", [("before_label", 16), ("after_label", 16), ("headline", 60)])
def test_before_after_text_limits(field, limit):
    Params(**{field: "W" * limit})
    with pytest.raises(ValidationError):
        Params(**{field: "W" * (limit + 1)})


def test_before_after_plain_errors_and_optional_labels():
    with pytest.raises(ValidationError, match="Choose two different pictures"):
        Params(before="room.png", after="room.png")
    with pytest.raises(ValidationError, match="Add a headline or a label"):
        Params(before_label="", after_label="", headline="")
    Params(before_label="", after_label="", before="old.png")
    assert Params(headline="A\nnew look").headline == "A new look"
    for values in ({"direction": "diagonal"}, {"speed": "instant"}, {"accent": "blue"}, {"extra": 1}):
        with pytest.raises(ValidationError):
            Params(**values)


@pytest.fixture
def make_scene(tmp_path):
    pytest.importorskip("manim")
    from manim import tempconfig
    from studio.compat import output_config
    from studio.formats import frame_size, pixel_size
    from studio.kit import runtime
    from studio.templates.before_after.scene import Template
    from studio.templates.before_after.parts import Palette

    def make(params, aspect="16:9", theme="clean", **settings):
        width, height = pixel_size(aspect, 480)
        fw, fh = frame_size(width, height)
        runtime.set_job({"params": params, "settings": {"aspect": aspect, "theme": theme, **settings},
                         "mode": "video", "assets_dir": str(tmp_path)})
        with tempconfig({**output_config(dry_run=True), "media_dir": str(tmp_path),
                         "frame_width": fw, "frame_height": fh, "verbosity": "ERROR",
                         "progress_bar": "none"}):
            scene = Template()
            scene.setup()
        scene.pal = Palette(scene.theme, scene.p.accent)
        return scene

    yield make
    runtime.set_job(None)


def _inside(inner, outer):
    assert inner.get_left()[0] >= outer.left - 1e-5
    assert inner.get_right()[0] <= outer.right + 1e-5
    assert inner.get_bottom()[1] >= outer.bottom - 1e-5
    assert inner.get_top()[1] <= outer.top + 1e-5


@pytest.mark.parametrize("aspect", ASPECTS)
@pytest.mark.parametrize("direction", ["left", "right", "top", "bottom"])
@pytest.mark.parametrize("theme", THEMES)
def test_before_after_full_text_clear_in_every_shape_direction_and_theme(make_scene, aspect, direction, theme):
    from studio.templates.before_after.parts import reveal
    params = {"before_label": "An original look", "after_label": "The finished one",
              "headline": "A welcoming place to meet, read, work and relax with friends",
              "direction": direction}
    assert len(params["before_label"]) == 16
    assert len(params["headline"]) == 60
    scene = make_scene(params, aspect, theme, safe_zone=True,
                       brand={"accent": "#E11D48"})
    plan = scene._compose()
    reveal(plan, 0.5)
    _inside(plan.headline, scene.layout.safe)
    for word, source in ((plan.before_visual.word, params["before_label"]),
                         (plan.after_group.word, params["after_label"]),
                         (plan.headline[-1], params["headline"])):
        expected = source.strip().upper() if word is not plan.headline[-1] or scene.theme.case == "upper" else source.strip()
        assert "".join(line.original_text.replace(" ", "") for line in word.lines) == expected.replace(" ", "")
        _inside(word, scene.layout.safe)
    assert plan.headline.get_bottom()[1] > scene.picture_region.top
    if direction in ("left", "right"):
        a, b = plan.before_visual.word, plan.after_group.word
        assert a.get_right()[0] < b.get_left()[0]
    else:
        a, b = plan.before_visual.word, plan.after_group.word
        assert a.get_bottom()[1] > b.get_top()[1]


@pytest.mark.parametrize("direction", ["left", "right", "top", "bottom"])
def test_before_after_photo_mask_reveals_progressively_and_preserves_alpha(make_scene, tmp_path, direction):
    import numpy as np
    from PIL import Image
    from studio.templates.before_after.parts import reveal
    Image.new("RGBA", (120, 80), (25, 160, 90, 128)).save(tmp_path / "after.png")
    Image.new("RGB", (80, 120), (200, 100, 40)).save(tmp_path / "before.png")
    scene = make_scene({"before": "before.png", "after": "after.png", "direction": direction})
    plan = scene._compose()
    assert plan.pictures == 2
    counts = []
    for value in (0, 0.25, 0.5, 0.75, 1):
        reveal(plan, value)
        alpha = plan.after_image.pixel_array[:, :, 3]
        counts.append(np.count_nonzero(alpha))
        assert set(np.unique(alpha)) <= {0, 128}
        if value == 0.25:
            if direction in ("left", "right"):
                assert alpha[alpha.shape[0] // 2, -1] == 128 and alpha[alpha.shape[0] // 2, 0] == 0
            else:
                assert alpha[-1, alpha.shape[1] // 2] == 128 and alpha[0, alpha.shape[1] // 2] == 0
    assert counts[0] == 0 and counts[-1] == alpha.size
    assert all(a < b for a, b in zip(counts, counts[1:]))
    assert plan.before_label[0].get_fill_opacity() == 0
    assert plan.after_label[0].get_fill_opacity() == 1
    assert plan.before_visual.width == pytest.approx(scene.picture_region.width)
    assert plan.before_visual.height == pytest.approx(scene.picture_region.height)


def test_before_after_missing_pictures_are_deliberate_panels(make_scene):
    scene = make_scene({"before": "missing.png", "after": "also-missing.png"})
    plan = scene._compose()
    assert plan.pictures == 0
    assert plan.before_visual.word is not None and plan.after_group.word is not None
    assert plan.after_panel is not None


@pytest.mark.parametrize("aspect", ASPECTS)
@pytest.mark.parametrize("direction", ["left", "right", "top", "bottom"])
def test_before_after_short_and_unbroken_text_also_fit(make_scene, aspect, direction):
    for label, headline in (("A", ""), ("W" * 16, "W" * 60)):
        scene = make_scene({"before_label": label, "after_label": label, "headline": headline,
                            "direction": direction}, aspect,
                           brand={"font": "JetBrains Mono"}, safe_zone=True)
        plan = scene._compose()
        _inside(plan.before_visual.word, scene.picture_region)
        _inside(plan.after_group.word, scene.picture_region)
        for word in (plan.before_visual.word, plan.after_group.word):
            assert "".join(line.original_text for line in word.lines) == label
        if plan.headline is not None:
            assert "".join(line.original_text for line in plan.headline[-1].lines) == headline
            assert plan.headline.get_bottom()[1] > scene.picture_region.top


def test_before_after_more_pictures_and_slower_reveal_get_more_time(make_scene, tmp_path):
    from PIL import Image
    Image.new("RGB", (80, 80), "red").save(tmp_path / "before.png")
    Image.new("RGB", (80, 80), "blue").save(tmp_path / "after.png")
    lengths = []
    for params in ({"speed": "fast"}, {"speed": "slow"},
                   {"speed": "slow", "before": "before.png", "after": "after.png"}):
        scene = make_scene(params)
        plan = scene._compose()
        scene.play = lambda *animations, **kwargs: None
        scene.wait = lambda *args: None
        scene._play(plan)
        lengths.append(scene.target_length)
    assert lengths[0] < lengths[1] < lengths[2]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg decodes the real movie frames")
@pytest.mark.parametrize("direction", ["left", "right", "top", "bottom"])
def test_before_after_real_movie_has_intermediate_reveal_frames(tmp_path, direction):
    pytest.importorskip("manim")
    import numpy as np
    from PIL import Image
    from studio.worker import _Child

    Image.new("RGB", (120, 80), "#E02020").save(tmp_path / "before.png")
    Image.new("RGB", (80, 120), "#2040E0").save(tmp_path / "after.png")
    movie = tmp_path / "reveal.mp4"
    result = _Child(None).render({"id": 1, "width": 128, "height": 72,
        "media_dir": str(tmp_path / "media"), "job": {"template": META.id, "mode": "motion",
        "max_duration": 20, "output": str(movie), "assets_dir": str(tmp_path),
        "params": {"before": "before.png", "after": "after.png", "before_label": "",
                   "after_label": "", "direction": direction, "speed": "slow"},
        "settings": {"aspect": "16:9", "sound": {"effects": False}}}})
    assert result["ok"], json.dumps(result)
    decoded = subprocess.run(["ffmpeg", "-v", "error", "-i", str(movie),
                              "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                             capture_output=True, check=True, timeout=30)
    frames = np.frombuffer(decoded.stdout, dtype=np.uint8).reshape(-1, 72, 128, 3)
    coverage = []
    for seconds in (0.8, 1.55, 2.3, 3.05, 4.0):
        frame = frames[round(seconds * 15)]
        blue = (frame[..., 2] > 140) & (frame[..., 0] < 100)
        coverage.append(int(blue.sum()))
    # The handle is accent-colored; exclude it from the first-frame photo count.
    assert coverage[0] < coverage[-1] * .01
    assert all(a < b for a, b in zip(coverage, coverage[1:])), coverage
    assert coverage[1] / coverage[-1] == pytest.approx(0.25, abs=0.06)
    assert coverage[2] / coverage[-1] == pytest.approx(0.5, abs=0.06)
    assert coverage[3] / coverage[-1] == pytest.approx(0.75, abs=0.06)


@pytest.mark.parametrize("direction", ["left", "right", "top", "bottom", "horizontal", "vertical"])
def test_before_after_labels_are_steady_on_photos_and_centered_on_full_empty_panels(make_scene, tmp_path, direction):
    import numpy as np
    from PIL import Image
    from studio.templates.before_after.parts import reveal
    for pictures in (False, True):
        params = {"direction": direction}
        if pictures:
            Image.new("RGB", (200, 120), "red").save(tmp_path / "before.png")
            Image.new("RGB", (120, 200), "blue").save(tmp_path / "after.png")
            params.update(before="before.png", after="after.png")
        scene = make_scene(params)
        plan = scene._compose()
        if pictures:
            positions = [label.get_center().copy() for label in (plan.before_label, plan.after_label)]
            for progress in (0, .25, .5, .75, 1):
                reveal(plan, progress)
                for label, position in zip((plan.before_label, plan.after_label), positions):
                    assert np.allclose(label.get_center(), position)
                    _inside(label, scene.picture_region)
                    assert label.height < scene.picture_region.height * .18
        else:
            reveal(plan, 0)
            assert np.allclose(plan.before_word.get_center(), plan.center)
            reveal(plan, 1)
            assert np.allclose(plan.after_group.word.get_center(), plan.center)
        assert plan.handle.width >= scene.layout.unit * 5


def test_before_after_old_direction_values_still_work():
    for old, new in (("left", "horizontal"), ("right", "horizontal"),
                     ("top", "vertical"), ("bottom", "vertical")):
        assert Params(direction=old).direction == new
