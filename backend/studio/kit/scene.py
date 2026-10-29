"""``StudioScene``: the base class of every template's ``Template`` scene.

A template implements ``build()`` using ``self.p`` (its validated Params), ``self.s``
(RenderSettings), ``self.theme``, ``self.layout`` and ``self.motion``. The base class
draws the background, then after ``build()`` pads the video to the requested length
and plays the ending (hold / fade / cut).

Preview modes, set by the job:

* ``poster``: animations are skipped; the frame at ``self.poster()`` (or, if the
  template never calls it, the frame before the ending) is written to ``job["output"]``.
* ``storyboard``: animations are skipped; the frame after each ``play()`` is captured
  and a contact sheet is written to ``job["output"]``.
"""

from __future__ import annotations

import math
import os

from manim import FadeOut, Scene, config
from manim.utils.exceptions import EndSceneEarlyException
from manim.utils.family import extract_mobject_family_members
from manim.utils.iterables import list_update

from ..schema import RenderSettings
from ..themes import theme_tokens
from . import fonts, media, runtime, shapes
from .layout import Layout
from .motion import Motion

MAX_STORYBOARD_FRAMES = 12


class Theme:
    """Theme tokens with helpers. ``accent(i)`` cycles the series colors."""

    def __init__(self, tokens: dict):
        self.tokens = tokens
        self.dark = tokens["dark"]
        self.bg = tokens["bg"]
        self.bg2 = tokens["bg2"]
        self.surface = tokens["surface"]
        self.text = tokens["text"]
        self.muted = tokens["muted"]
        self.line = tokens["line"]
        self.on_accent = tokens["on_accent"]
        self.accents = tokens["accent"]
        self.font = tokens["font"]
        self.display_weight = tokens["display_weight"]
        self.radius = tokens["radius"]
        self.case = tokens["case"]

    def accent(self, index: int = 0) -> str:
        return self.accents[index % len(self.accents)]

    def display(self, text: str) -> str:
        """Headline casing for this theme (Bold pop shouts in capitals)."""
        return text.upper() if self.case == "upper" else text


class StudioScene(Scene):
    Params = None  # the template's Params model; set by each template's scene.py
    META = None  # the template's TemplateMeta

    # -- setup -----------------------------------------------------------------
    def setup(self):
        job = runtime.current_job()
        self.job = job
        self.mode = job.get("mode", "video")
        self.p = self.Params(**(job.get("params") or {}))
        self.s = RenderSettings(**(job.get("settings") or {}))
        self.theme = Theme(theme_tokens(self.s.theme, self.s.brand))
        self.layout = Layout(config.frame_width, config.frame_height, safe_zone=self.s.safe_zone)
        self.motion = Motion(self.s.energy, unit=self.layout.unit)
        default = self.META.default_length if self.META is not None else 8
        self.target_length = self.s.length or default
        self.assets_dir = job.get("assets_dir")
        self._frames = []
        self._poster_done = False
        self._particle_clearances = []
        fonts.register_bundled()
        self.bg = self._background()
        if self.bg is not None:
            self.add(self.bg)

    def _background(self):
        bg = self.s.background
        if bg.kind == "transparent":
            return None
        width, height = config.frame_width, config.frame_height
        if bg.kind == "solid" and bg.color:
            return shapes.full_frame(width, height, bg.color)
        if bg.kind == "gradient":
            return shapes.full_frame(width, height, bg.color or self.theme.bg, bg.color2 or self.theme.bg2)
        return shapes.full_frame(width, height, self.theme.bg)

    # -- helpers for templates -------------------------------------------------
    def asset(self, name):
        """Path of an uploaded asset named in the params, or None."""
        return media.resolve_asset(self.assets_dir, name)

    def keep_particles_clear(self, particles, foreground, *, padding=0.10):
        """Reserve readable space for lines/marks in every render mode."""
        from .fx import ParticleClearance

        clearance = ParticleClearance(particles, foreground, padding)
        self._particle_clearances.append(clearance)
        return particles

    def update_mobjects(self, dt):
        clearances = getattr(self, "_particle_clearances", ())
        for clearance in clearances:
            clearance.restore()
        super().update_mobjects(dt)
        # Run after ALL updaters, including counters that change their width.
        # poster() also calls this method when jumping to its selected frame.
        for clearance in clearances:
            clearance.apply()

    @property
    def elapsed(self) -> float:
        return self.renderer.time

    def remaining(self, reserve_ending: bool = True) -> float:
        """Seconds left before the requested length (minus the ending's exit)."""
        end = self.target_length - (self.motion.exit if reserve_ending and self.s.ending == "fade" else 0)
        return max(0.0, end - self.elapsed)

    def content(self):
        """Everything on screen except the background."""
        return [m for m in self.mobjects if m is not self.bg]

    def poster(self):
        """Mark the frame that best shows this template (used for thumbnails)."""
        if self.mode == "poster" and not self._poster_done:
            self.update_mobjects(0)
            self._write_still()
            self._poster_done = True
            raise EndSceneEarlyException()

    # -- construct -------------------------------------------------------------
    def build(self):  # pragma: no cover - templates implement it
        raise NotImplementedError

    def construct(self):
        self.build()
        if self.mode == "poster" and not self._poster_done:
            self.poster()
        hold = self.remaining()
        if hold > 0.01:
            self.wait(hold)
        if self.s.ending == "fade":
            items = self.content()
            if items:
                self.play(*[FadeOut(m) for m in items], run_time=self.motion.exit)
            self.wait(0.15)

    def play(self, *args, **kwargs):
        if self.mode == "motion" and self.elapsed >= self.job["max_duration"] - 1e-6:
            raise EndSceneEarlyException()
        super().play(*args, **kwargs)
        if self.mode == "motion" and self.elapsed >= self.job["max_duration"] - 1e-6:
            raise EndSceneEarlyException()
        if self.mode == "storyboard":
            self._capture()

    def get_moving_and_static_mobjects(self, animations):
        # Cairo normally snapshots a flattened family, retaining obsolete
        # descendants when an updater rebuilds a counter or a live effect.
        # Render whole live roots instead. Cache only a complete painter-order
        # prefix, so a root crossing z layers cannot be drawn twice or in front
        # of content that should cover it. This applies to previews AND exports.
        moving, _ = super().get_moving_and_static_mobjects(animations)
        moving_ids = {id(m) for m in moving}
        roots = list_update(self.mobjects, self.foreground_mobjects)
        families = [{id(m) for m in root.get_family()} for root in roots]
        active = {i for i, family in enumerate(families) if family & moving_ids}
        # Include empty live groups: they can emit lower-layer children on a
        # later frame, so their own z position must already bound the prefix.
        order = {id(m): i for i, m in enumerate(extract_mobject_family_members(
            roots, use_z_index=self.camera.use_z_index))}
        positions = [{order[mid] for mid in family if mid in order} for family in families]
        while active:
            cutoff = min((p for i in active for p in positions[i]), default=len(order))
            promoted = {i for i, indexes in enumerate(positions) if any(p >= cutoff for p in indexes)} | active
            if promoted == active:
                break
            active = promoted
        return ([root for i, root in enumerate(roots) if i in active],
                [root for i, root in enumerate(roots) if i not in active])

    def get_time_progression(self, run_time, *args, **kwargs):
        # Limit sampled frames without changing animation.run_time: a countdown
        # still counts in real seconds, rather than squeezing five minutes into 20s.
        if self.mode == "motion":
            run_time = min(run_time, max(0, self.job["max_duration"] - self.elapsed))
        return super().get_time_progression(run_time, *args, **kwargs)

    def wait(self, duration=1, *args, **kwargs):
        # Manim's frozen-frame waits bypass get_time_progression.
        if self.mode == "motion":
            duration = min(duration, max(0, self.job["max_duration"] - self.elapsed))
            if duration <= 1e-6:
                raise EndSceneEarlyException()
        return super().wait(duration, *args, **kwargs)

    def add_sound(self, *args, **kwargs):
        if self.mode != "motion":
            return super().add_sound(*args, **kwargs)

    def tear_down(self):
        super().tear_down()
        if self.mode == "storyboard":
            self._write_storyboard()

    # -- preview output --------------------------------------------------------
    def _image(self):
        self.renderer.update_frame(self, ignore_skipping=True)
        return self.camera.get_image().copy()

    def _write_still(self):
        out = self.job.get("output")
        if out:
            os.makedirs(os.path.dirname(out), exist_ok=True)
            self._image().save(out)

    def _capture(self):
        img = self._image()
        img.thumbnail((480, 480))
        self._frames.append((round(self.elapsed, 2), img))

    def _write_storyboard(self):
        out = self.job.get("output")
        if not out:
            return
        from PIL import Image

        frames = self._frames
        plays = len(frames)
        if not frames:
            frames = [(0.0, self._image())]
        if len(frames) > MAX_STORYBOARD_FRAMES:
            step = (len(frames) - 1) / (MAX_STORYBOARD_FRAMES - 1)
            frames = [frames[round(i * step)] for i in range(MAX_STORYBOARD_FRAMES)]
        tw, th = frames[0][1].size
        cols = min(len(frames), 4 if tw >= th else 6)
        rows = math.ceil(len(frames) / cols)
        gap = 8
        sheet = Image.new("RGBA", (cols * tw + (cols + 1) * gap, rows * th + (rows + 1) * gap), (24, 24, 27, 255))
        for i, (_, img) in enumerate(frames):
            r, c = divmod(i, cols)
            sheet.paste(img, (gap + c * (tw + gap), gap + r * (th + gap)))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        sheet.save(out)
        times = [t for t, _ in frames]
        meta_path = os.path.splitext(out)[0] + ".json"
        import json

        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump({"frames": len(frames), "plays": plays, "columns": cols, "times": times,
                       "frame_size": [tw, th], "length": round(self.elapsed, 2)}, f)
