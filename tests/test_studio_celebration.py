"""Celebration geometry and draw order, without rendering pixels."""

import pytest

pytest.importorskip("manim")

from manim import tempconfig  # noqa: E402

from studio.kit import runtime  # noqa: E402
from studio.kit.layout import Layout  # noqa: E402
from studio.templates.celebration import fx  # noqa: E402
from studio.templates.celebration.scene import FLAVORS, TEXT_Z, Template  # noqa: E402
from studio.templates.celebration.schema import PRESETS  # noqa: E402
from studio.themes import THEMES  # noqa: E402

DIMENSIONS = [(128 / 9, 8), (8, 128 / 9), (8, 8), (8, 10)]


@pytest.fixture(scope="module")
def text_media(tmp_path_factory):
    # Reuse Manim's text SVG cache across cases; no frame images are written.
    return tmp_path_factory.mktemp("celebration-text")


@pytest.fixture
def make_scene(text_media):
    def make(*, params=None, theme="pastel", mode="poster"):
        runtime.set_job({"params": params or {}, "settings": {"theme": theme, "length": 30},
                         "mode": mode, "max_duration": 30})
        scene = Template()
        scene.setup()
        scene.flavor = FLAVORS[scene.p.occasion]
        scene._palette()
        scene.clock = fx.Clock()
        return scene

    with tempconfig({"media_dir": str(text_media), "frame_width": 8, "frame_height": 128 / 9,
                     "dry_run": True, "skip_animations": True, "verbosity": "ERROR", "progress_bar": "none"}):
        yield make
    runtime.set_job(None)


@pytest.mark.parametrize("theme", THEMES)
def test_body_text_has_phone_readable_contrast_in_every_theme(theme, make_scene):
    scene = make_scene(theme=theme, params={"message": "A note with *emphasis*.", "from_line": "With love",
                                          "number": 30, "number_label": "years"})
    texts = scene._texts(1, scene.layout.safe.width, "center")
    for body in (texts.message, texts.signoff, texts.label):
        colors = {mob.get_fill_color().to_hex() for mob in body.family_members_with_points()
                  if mob.get_fill_opacity() > 0}
        assert colors == {THEMES[theme]["text"]}
        for color in colors:
            for background in (THEMES[theme]["bg"], THEMES[theme]["bg2"]):
                assert fx.contrast(color, background) >= 4.5


@pytest.mark.parametrize("dimensions", DIMENSIONS)
@pytest.mark.parametrize("preset", PRESETS, ids=lambda preset: preset.id)
def test_headline_name_gap_and_content_stay_inside_the_safe_frame(dimensions, preset, make_scene):
    scene = make_scene(params=preset.params, theme=preset.settings["theme"])
    scene.layout = Layout(*dimensions)
    parts = scene._compose()
    texts = parts.texts
    gap = texts.headline.get_bottom()[1] - texts.name.get_top()[1]
    assert gap == pytest.approx(0.18 * texts.name.height, abs=0.01)
    safe = scene.layout.safe
    for row in parts.rows:
        assert row.mob.get_top()[1] <= safe.top + 0.01
        assert row.mob.get_bottom()[1] >= safe.bottom - 0.01
        assert row.mob.get_left()[0] >= safe.left - 0.01
        assert row.mob.get_right()[0] <= safe.right + 0.01


@pytest.mark.parametrize("mode", ["poster", "storyboard", "video", "motion"])
@pytest.mark.parametrize("occasion", ["birthday", "anniversary", "thanks"])
@pytest.mark.parametrize("photo", [False, True], ids=["icon", "photo-badge"])
def test_every_foreground_family_draws_above_every_burst(mode, occasion, photo, make_scene, monkeypatch, tmp_path):
    params = {"occasion": occasion, "message": "Cake, laughter and everyone you love.",
              "from_line": "With love, your friends", "number": 30, "number_label": "years"}
    scene = make_scene(mode=mode, params=params)
    if photo:
        image = tmp_path / "photo.svg"
        image.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
                         '<rect width="10" height="10" fill="#2563EB"/></svg>', encoding="utf-8")
        monkeypatch.setattr(scene, "asset", lambda _: str(image))
    parts = scene._compose()
    hero = scene._hero(parts.D, parts.hero_center)
    monkeypatch.setattr(scene, "_hero", lambda *args: hero)
    # Exercise real animation setup/interpolation/cleanup, but never draw a frame.
    monkeypatch.setattr(scene.renderer, "update_frame", lambda *args, **kwargs: None)
    monkeypatch.setattr(scene, "_capture", lambda: None)
    monkeypatch.setattr(scene, "poster", lambda: scene.update_mobjects(0))
    scene.add(scene.clock)
    scene._intro(parts)
    parties = [mob for mob in scene.mobjects if isinstance(mob, fx.Party)]
    assert len(parties) > 1  # a 30-second video includes later bursts
    texts = parts.texts
    foreground = [texts.headline, texts.name, texts.counter, texts.label, texts.message, texts.signoff,
                  hero.badge if photo else hero.icon]
    # The counter replaces its digits while counting, including after its entrance.
    for value in (0, 9, 10, 29, 30):
        texts.counter.set_value(value)
        assert all(mob.z_index == TEXT_Z for mob in texts.counter.get_family())
    for party in parties:
        for age in (0.4, 1.15, 2.3):
            scene.clock.t = party.start + age
            scene.update_mobjects(0)
            particles = party.family_members_with_points()
            assert particles
            for group in foreground:
                assert min(mob.z_index for mob in group.get_family()) > max(mob.z_index for mob in particles)
            # Check the camera's actual sorted draw list even when bursts were added last.
            ordered = scene.camera.get_mobjects_to_display(scene.mobjects)
            positions = {id(mob): index for index, mob in enumerate(ordered)}
            for group in foreground:
                assert min(positions[id(mob)] for mob in group.family_members_with_points()) > max(
                    positions[id(mob)] for mob in particles)
