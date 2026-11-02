"""Photo stories keep captions, crops and timing useful in every shape."""
import pytest
from pydantic import ValidationError

from studio import registry
from studio.schema import ASPECTS
from studio.templates.slideshow.schema import META, PRESETS, Params, Slide
from studio.themes import THEMES


def test_slideshow_gallery_and_limits():
    assert len(PRESETS) == 3
    cards = next(s["cards"] for s in registry.catalog()["sections"] if s["id"] == "creator")
    assert {c["id"] for c in cards if c["template"] == META.id} == {p.id for p in PRESETS}
    for preset in PRESETS:
        registry.validate_job(META.id, preset.params, preset.settings)
    Params(title="W" * 60, slides=[{"caption": "W" * 80}] * 12, seconds_per_slide=10)
    for invalid in ({"title": "W" * 61}, {"slides": [{"caption": "W" * 81}] * 2},
                    {"caption_position": "middle"}, {"accent": "red"}, {"unknown": True}):
        with pytest.raises(ValidationError):
            Params(**invalid)
    for count in (0, 1, 13):
        with pytest.raises(ValidationError, match="Choose between 2 and 12 pictures"):
            Params(slides=[{}] * count)
    for seconds in (0, 1.9, 10.1, float("nan")):
        with pytest.raises(ValidationError, match="Choose between 2 and 10 seconds"):
            Params(seconds_per_slide=seconds)
    assert Slide(caption="A\nnew day").caption == "A new day"


@pytest.fixture
def make_scene(tmp_path):
    pytest.importorskip("manim")
    from manim import tempconfig
    from studio.compat import output_config
    from studio.formats import frame_size, pixel_size
    from studio.kit import runtime
    from studio.templates.slideshow.scene import Template

    def make(params, aspect="16:9", theme="clean", **settings):
        fw, fh = frame_size(*pixel_size(aspect, 480))
        runtime.set_job({"params": params, "settings": {"aspect": aspect, "theme": theme, **settings},
                         "mode": "video", "assets_dir": str(tmp_path)})
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


@pytest.mark.parametrize("aspect", ASPECTS)
@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("position", ["top", "bottom"])
def test_slideshow_maximum_and_minimum_text_have_real_room(make_scene, aspect, theme, position):
    for title, caption in (("W" * 60, "W" * 80), ("", "")):
        scene = make_scene({"title": title, "slides": [{"caption": caption}] * 2,
                            "caption_position": position, "accent": "#E11D48"}, aspect, theme,
                           safe_zone=True, brand={"font": "JetBrains Mono", "accent": "#123456"})
        slides = scene._compose()
        assert scene.accent == "#E11D48"
        if scene.heading is not None:
            inside(scene.heading, scene.layout.safe)
            assert "".join(line.original_text for line in scene.heading.lines) == title
            assert scene.heading.get_bottom()[1] > scene.picture_region.top
        for slide in slides:
            inside(slide, scene.layout.safe)
            if slide.caption is not None:
                inside(slide.caption, scene.picture_region)
                shown = "".join(line.original_text for line in slide.caption[1].lines)
                assert shown == caption


def test_slideshow_photo_uses_kit_preparation_and_zoom_stays_in_frame(make_scene, tmp_path, monkeypatch):
    import numpy as np
    from PIL import Image
    from studio.templates.slideshow import parts
    pixels = np.zeros((100, 160, 4), dtype=np.uint8)
    pixels[..., 0] = np.arange(160)
    pixels[..., 1] = np.arange(100)[:, None]
    pixels[..., 3] = 128
    Image.fromarray(pixels).save(tmp_path / "photo.png")
    calls, original = [], parts.media.image
    def prepared(*args, **kwargs):
        calls.append(args[0])
        return original(*args, **kwargs)
    monkeypatch.setattr(parts.media, "image", prepared)
    scene = make_scene({"slides": [{"picture": "photo.png"}, {"picture": "missing.png"}]})
    slides = scene._compose()
    assert len(calls) == 1 and slides[0].photo is not None and slides[1].photo is None
    photo = slides[0].photo
    bounds = photo.get_all_points().copy()
    before = photo.pixel_array.copy()
    animation = parts.GentleZoom(photo)
    animation.interpolate_mobject(1)
    assert np.array_equal(bounds, photo.get_all_points())
    assert not np.array_equal(before, photo.pixel_array)
    assert set(np.unique(photo.pixel_array[..., 3])) == {128}


def test_slideshow_length_is_number_of_pictures_times_seconds(make_scene):
    for count, seconds in ((2, 2), (12, 10)):
        scene = make_scene({"slides": [{}] * count, "seconds_per_slide": seconds}, ending="cut")
        times = []
        scene.play = lambda *args, **kwargs: times.append(kwargs["run_time"])
        scene.build()
        assert scene.target_length == count * seconds
        assert sum(times) == pytest.approx(count * seconds)


def test_slideshow_real_poster_and_lowest_quality_movie(tmp_path):
    pytest.importorskip("manim")
    import json
    import shutil
    import subprocess
    from studio.dev import render_preview
    from studio.worker import _Child
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg checks the real draft movie")
    params = {"slides": [{"caption": "First day"}, {"caption": "A day to remember"}],
              "seconds_per_slide": 2}
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
    assert float(video["duration"]) >= 4
