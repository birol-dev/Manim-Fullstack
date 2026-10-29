"""Pixel probes for particle compositing, using the actual Cairo render paths."""

import numpy as np
import pytest
from PIL import Image

pytest.importorskip("manim")

from manim import tempconfig  # noqa: E402
from manim.camera.camera import Camera  # noqa: E402
from manim.utils.iterables import list_update  # noqa: E402

from studio.formats import frame_size, pixel_size  # noqa: E402
from studio.kit import runtime  # noqa: E402
from studio.kit.counter import Counter  # noqa: E402
from studio.kit.shapes import Confetti  # noqa: E402
from studio.templates.celebration import fx  # noqa: E402
from studio.templates.celebration.scene import Template  # noqa: E402
from studio.templates.celebration.schema import PRESETS  # noqa: E402
from studio.templates.countdown.scene import Template as Countdown  # noqa: E402


def rgba(mobjects, *, include_submobjects=True):
    camera = Camera(background_opacity=0)
    camera.capture_mobjects(mobjects, include_submobjects=include_submobjects)
    return np.asarray(camera.get_image()).copy()


def assert_foreground_pixels(scene, actual, foreground, particles, label):
    """Render (a) normal, (b) without foreground, (c) foreground on alpha.

    Compare opaque ink in the actual render to b+c. Only current scene
    members are included: a name can enter one glyph at a time. No golden PNGs,
    layer assertions, opaque rectangles behind text, or hidden particle mocks.
    """
    displayed = scene.camera.get_mobjects_to_display(list_update(scene.mobjects, scene.foreground_mobjects))
    foreground_ids = {id(m) for root in foreground for m in root.get_family()}
    front = [m for m in displayed if id(m) in foreground_ids]
    behind = [m for m in displayed if id(m) not in foreground_ids]
    text = rgba(front, include_submobjects=False)
    background = rgba(behind, include_submobjects=False)
    # The scene camera's opaque clear color also participates in b.
    clear = Image.new("RGBA", scene.camera.get_image().size, scene.camera.background_color.to_hex())
    clear.putalpha(round(scene.camera.background_opacity * 255))
    under = Image.alpha_composite(clear, Image.fromarray(background))
    expected = np.asarray(Image.alpha_composite(under, Image.fromarray(text)))
    opaque = text[:, :, 3] == 255
    assert opaque.sum() > 10, label
    difference = np.abs(actual[:, :, :3].astype(int) - expected[:, :, :3].astype(int)).max(axis=2)
    bad = opaque & (difference > 3)
    assert not bad.any(), f"{label}: {bad.sum()} opaque foreground pixels covered (max error {difference[opaque].max()})"
    # Letter holes, spaces and the area between glyphs must stay clear too.
    # This catches the supplied screenshot even though its opaque ink is on top.
    height, width = actual.shape[:2]
    xs = (np.arange(width) + 0.5 - width / 2) * scene.camera.frame_width / width
    ys = (height / 2 - np.arange(height) - 0.5) * scene.camera.frame_height / height
    reserved = np.zeros((height, width), dtype=bool)
    for mob in foreground:
        points = mob.get_all_points()
        if len(points):
            low, high = points.min(axis=0), points.max(axis=0)
            reserved |= ((xs[None, :] >= low[0]) & (xs[None, :] <= high[0])
                         & (ys[:, None] >= low[1]) & (ys[:, None] <= high[1]))
    particle_alpha = rgba(particles)[:, :, 3]
    assert not (reserved & (particle_alpha > 0)).any(), f"{label}: confetti crosses a foreground line/mark"
    # Unhide copies solely to prove that the real trajectories would intersect
    # foreground; the actual render and references above use untouched opacity.
    natural = [m.copy().set_opacity(1) for root in particles for m in root.family_members_with_points()]
    return int((reserved & (rgba(natural)[:, :, 3] > 0)).sum())


@pytest.fixture(scope="module")
def particle_media(tmp_path_factory):
    return tmp_path_factory.mktemp("particle-pixels")


class CelebrationProbe(Template):
    def setup(self):
        super().setup()
        self.overlaps = 0
        self.samples = set()
        add_frame = self.renderer.add_frame

        def record(frame, num_frames=1):
            if self.mode in ("motion", "video") and hasattr(self, "parts"):
                parties = [m for m in self.mobjects if isinstance(m, fx.Party)]
                for index, party in enumerate(parties):
                    for age in (0.5, 1.15, 2.3):
                        key = (index, age)
                        if key not in self.samples and age <= self.clock.t - party.start < age + 0.26:
                            self.check(frame, f"{self.mode} burst {key}")
                            self.samples.add(key)
            add_frame(frame, num_frames)

        self.renderer.add_frame = record

    def _compose(self):
        self.parts = super()._compose()
        return self.parts

    def _hero(self, *args):
        self.hero = super()._hero(*args)
        return self.hero

    def check(self, frame, label):
        t = self.parts.texts
        foreground = [line for group in (t.headline, t.name, t.label, t.message, t.signoff)
                      if group is not None for line in group.lines]
        foreground += [m for m in (t.counter, self.hero.icon, self.hero.badge) if m is not None]
        self.overlaps += assert_foreground_pixels(
            self, np.asarray(frame), foreground,
            [m for m in self.mobjects if isinstance(m, fx.Party)], label)

    def _write_still(self):
        self.check(self._image(), "poster")

    def _capture(self):
        self.check(self._image(), "storyboard")


@pytest.mark.parametrize("aspect", ["9:16", "16:9", "1:1", "4:5"])
@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.id)
@pytest.mark.parametrize("mode", ["poster", "storyboard"])
def test_celebration_still_pixels(particle_media, aspect, preset, mode):
    width, height = pixel_size(aspect, 180)
    fw, fh = frame_size(width, height)
    runtime.set_job({"params": preset.params, "settings": {**preset.settings, "aspect": aspect}, "mode": mode})
    try:
        with tempconfig({"pixel_width": width, "pixel_height": height, "frame_width": fw, "frame_height": fh,
                         "frame_rate": 4,
                         "dry_run": True, "skip_animations": True, "media_dir": str(particle_media),
                         "disable_caching": True, "verbosity": "ERROR", "progress_bar": "none"}):
            scene = CelebrationProbe(skip_animations=True)
            scene.render()
            # The birthday poster reproduces the supplied message/signature.
            if preset.id == "happy-birthday" and mode == "poster" and aspect in ("9:16", "16:9"):
                assert scene.overlaps > 0, "The probe must exercise real particle/glyph intersections"
    finally:
        runtime.set_job(None)


@pytest.mark.parametrize("aspect", ["9:16", "16:9"])
@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.id)
@pytest.mark.parametrize("mode", ["motion", "video"])
def test_celebration_animated_pixels(particle_media, aspect, preset, mode):
    width, height = pixel_size(aspect, 180)
    fw, fh = frame_size(width, height)
    runtime.set_job({"params": preset.params,
                     "settings": {**preset.settings, "aspect": aspect, "length": 30, "ending": "hold"},
                     "mode": mode, "max_duration": 30})
    try:
        with tempconfig({"pixel_width": width, "pixel_height": height, "frame_width": fw, "frame_height": fh,
                         "frame_rate": 4, "dry_run": True, "media_dir": str(particle_media),
                         "disable_caching": True, "verbosity": "ERROR", "progress_bar": "none"}):
            scene = CelebrationProbe()
            scene.render()
            assert {index for index, _ in scene.samples} == {0, 1, 2, 3}, scene.samples
            assert scene.overlaps > 0, "Must exercise real intersections, including later bursts"
    finally:
        runtime.set_job(None)


class CountdownProbe(Countdown):
    def setup(self):
        super().setup()
        self.samples = set()
        self.overlaps = 0
        self.finish_message = None
        add_frame = self.renderer.add_frame

        def record(frame, num_frames=1):
            for confetti in [m for m in self.mobjects if isinstance(m, Confetti)]:
                for fraction in (0.25, 0.5, 0.75):
                    if fraction not in self.samples and fraction <= confetti.t.get_value() < fraction + 0.1:
                        self.check(frame, f"countdown {self.mode} {fraction}")
                        self.samples.add(fraction)
            add_frame(frame, num_frames)

        self.renderer.add_frame = record

    def keep_particles_clear(self, particles, foreground, **kwargs):
        self.finish_message = foreground[-1]
        return super().keep_particles_clear(particles, foreground, **kwargs)

    def check(self, frame, label):
        foreground = [line for group in self._confetti_foreground for line in group.lines]
        if self.finish_message is not None:
            foreground.extend(self.finish_message.lines)
        foreground.extend(m for m in self.mobjects if isinstance(m, Counter))
        self.overlaps += assert_foreground_pixels(
            self, np.asarray(frame), foreground,
            [m for m in self.mobjects if isinstance(m, Confetti)], label)

    def _write_still(self):
        self.check(self._image(), "countdown poster")

    def _capture(self):
        self.check(self._image(), "countdown storyboard")


@pytest.mark.parametrize("aspect", ["9:16", "16:9"])
@pytest.mark.parametrize("mode", ["poster", "storyboard", "motion", "video"])
def test_countdown_particle_pixels(particle_media, aspect, mode):
    width, height = pixel_size(aspect, 180)
    fw, fh = frame_size(width, height)
    runtime.set_job({"params": {"seconds": 3, "style": "big", "title": "Launch time",
                                 "subtitle": "Together we begin", "finish_text": "Here we go!", "confetti": True},
                     "settings": {"theme": "pastel", "aspect": aspect, "ending": "hold"},
                     "mode": mode, "max_duration": 15})
    try:
        with tempconfig({"pixel_width": width, "pixel_height": height, "frame_width": fw, "frame_height": fh,
                         "frame_rate": 4, "dry_run": True, "media_dir": str(particle_media),
                         "skip_animations": mode in ("poster", "storyboard"),
                         "disable_caching": True, "verbosity": "ERROR", "progress_bar": "none"}):
            scene = CountdownProbe(skip_animations=mode in ("poster", "storyboard"))
            scene.render()
            if mode in ("motion", "video"):
                assert scene.samples == {0.25, 0.5, 0.75}
                assert scene.overlaps > 0
    finally:
        runtime.set_job(None)


@pytest.mark.parametrize("aspect,mode", [("9:16", "poster"), ("16:9", "video")])
def test_photo_badge_and_number_without_name_stay_clear(particle_media, aspect, mode):
    Image.new("RGB", (32, 32), "#5588AA").save(particle_media / "portrait.png")
    width, height = pixel_size(aspect, 180)
    fw, fh = frame_size(width, height)
    runtime.set_job({"params": {**PRESETS[0].params, "name": "", "number": 30, "number_label": "years",
                                 "photo": "portrait.png"}, "assets_dir": str(particle_media),
                     "settings": {"theme": "pastel", "aspect": aspect, "length": 30, "ending": "hold",
                                  "background": {"kind": "transparent"}}, "mode": mode})
    try:
        with tempconfig({"pixel_width": width, "pixel_height": height, "frame_width": fw, "frame_height": fh,
                         "frame_rate": 4, "dry_run": True, "media_dir": str(particle_media), "transparent": True,
                         "disable_caching": True, "verbosity": "ERROR", "progress_bar": "none"}):
            scene = CelebrationProbe(skip_animations=mode == "poster")
            scene.render()
            assert scene.hero.badge is not None
            assert scene.overlaps > 0
            if mode == "video":
                assert {index for index, _ in scene.samples} == {0, 1, 2, 3}
    finally:
        runtime.set_job(None)
