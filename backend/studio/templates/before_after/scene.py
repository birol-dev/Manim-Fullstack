"""Before & after: two pictures, one sweeping line, and a result worth holding on.

The before picture (or a labeled color panel) is the full frame. The after picture
starts transparent and its alpha edge follows the line; without a picture, a color
panel grows behind the same line. The poster is taken halfway through the sweep, so
the gallery shows both sides and both labels.
"""

from __future__ import annotations

import logging

import numpy as np
from manim import UP, FadeIn, FadeOut, LaggedStart, ValueTracker, VGroup, linear

from studio.kit import StudioScene, ease_out
from studio.kit.layout import Region

from . import parts as P
from .schema import META, Params

logger = logging.getLogger(__name__)

SWEEP = {"slow": 3.0, "normal": 2.0, "fast": 1.3}
POSTER_AT = 0.5


class Template(StudioScene):
    Params = Params
    META = META
    logo_region = "top-right"
    logo_height = 7
    logo_reserved_aspects = ("16:9", "9:16", "1:1", "4:5")

    def build(self):
        self.pal = P.Palette(self.theme, self.p.accent)
        self.u = self.layout.unit
        if self.brand_logo is not None:
            self.reserve_logo_band()
        plan = self._compose()
        self._play(plan)

    # ------------------------------------------------------------------ layout
    def _word_point(self, fraction: float) -> np.ndarray:
        region = self.picture_region
        if self.p.direction == "horizontal":
            return region.center + [(fraction - 0.5) * region.width, 0.0, 0.0]
        return region.center + [0.0, (0.5 - fraction) * region.height, 0.0]

    def _asset(self, name):
        path = self.asset(name) if name else None
        if name and path is None:
            logger.warning("Picture %r is missing; using a color panel.", name)
        return path

    def _placeholder(self, label: str, color: str, panel_color: str, fraction: float) -> VGroup:
        """A color panel with its label, filling the frame."""
        fw, fh = self.picture_region.width, self.picture_region.height
        horizontal = self.p.direction == "horizontal"
        point = self._word_point(fraction)
        group = VGroup(P.color_panel(fw, fh, panel_color).move_to(self.picture_region.center))
        if label.strip():
            word = P.placeholder_word(
                label, color, self.pal,
                width=(0.36 * fw if horizontal else 0.78 * fw),
                size=84.0,
                max_lines=2 if horizontal else 1,
                locale=self.s.locale)
            word.move_to(point)
            group.add(word)
            group.word = word
        return group

    def _compose(self) -> P.Plan:
        """Every still piece, placed for this shape and direction (tests use this too)."""
        p, lay, pal, u = self.p, self.layout, self.pal, self.layout.unit
        S = lay.safe
        landscape = lay.is_landscape
        pictures = 0

        headline = P.headline_block(p.headline, pal, width=0.96 * S.width,
                                    size=64 if landscape else 54, unit=u, locale=self.s.locale)
        picture_top = S.top
        if headline is not None:
            headline.move_to([S.center[0], S.top - headline.height / 2, 0])
            headline.set_z_index(5)
            picture_top = headline.get_bottom()[1] - 3 * u
        self.picture_region = R = Region(S.left, S.right, picture_top, S.bottom)
        fw, fh = R.width, R.height

        before_path = self._asset(p.before)
        before_visual = None
        before_picture = False
        if before_path:
            try:
                before_visual = P.cover(before_path, fw, fh)
                before_visual.move_to(R.center)
                before_visual.set_z_index(0)
                before_picture = True
                pictures += 1
            except Exception as exc:  # noqa: BLE001 - an unreadable upload falls back to a panel
                logger.warning("Before picture %r could not be read (%s); using a panel.", p.before, exc)
        if before_visual is None:
            before_visual = self._placeholder(p.before_label, pal.on_before, pal.before_bg, 0.25)
            before_visual.set_z_index(0)

        after_path = self._asset(p.after)
        after_image = None
        after_panel = None
        after_group = None
        after_visual = None
        after_picture = False
        if after_path:
            try:
                after_image = P.after_picture(after_path, fw, fh)
                after_image.move_to(R.center)
                after_image.set_z_index(1)
                after_visual = after_image
                after_picture = True
                pictures += 1
            except Exception as exc:  # noqa: BLE001 - an unreadable upload falls back to a panel
                logger.warning("After picture %r could not be read (%s); using a panel.", p.after, exc)
        if after_visual is None:
            after_panel = P.color_panel(fw, fh, pal.accent)
            after_panel.move_to(R.center)
            after_panel.set_z_index(1)
            after_visual = after_panel
            if p.after_label.strip():
                point = self._word_point(0.75)
                horizontal = p.direction == "horizontal"
                word = P.placeholder_word(
                    p.after_label, pal.on_accent, pal,
                    width=(0.36 * fw if horizontal else 0.78 * fw),
                    size=84.0,
                    max_lines=2 if horizontal else 1,
                    locale=self.s.locale)
                word.move_to(point)
                after_group = VGroup(word)
                after_group.word = word
                after_group.set_z_index(2)
                after_group.set_opacity(0)

        labels = []
        before_label = after_label = None
        label_width = 0.42 * S.width
        inset = 1.8 * u
        horizontal = p.direction == "horizontal"
        # Only a real photo needs a caption: an empty side already shows its word in the panel.
        if before_picture:
            before_label = P.label_pill(p.before_label, pal, unit=u, size=26 if landscape else 24,
                                        fill=pal.surface, ink=pal.text, max_width=label_width,
                                        locale=self.s.locale, stroke=True)
            if before_label is not None:
                point = self._word_point(0.25)
                x = R.left + inset + before_label.width / 2
                y = R.top - inset - before_label.height / 2
                before_label.move_to([x, y, 0])
                before_label.set_z_index(5)
                labels.append(before_label)
        if after_picture:
            after_label = P.label_pill(p.after_label, pal, unit=u, size=26 if landscape else 24,
                                       fill=pal.accent, ink=pal.on_accent, max_width=label_width,
                                       locale=self.s.locale)
            if after_label is not None:
                point = self._word_point(0.75)
                x = R.right - inset - after_label.width / 2
                y = (R.top - inset - after_label.height / 2 if horizontal
                     else R.bottom + inset + after_label.height / 2)
                after_label.move_to([x, y, 0])
                after_label.set_z_index(5)
                labels.append(after_label)
        label_group = VGroup(*labels) if labels else None

        # Two placeholder words sit together: give them one type size, so the shorter
        # word does not look louder than the longer one.
        before_word = getattr(before_visual, "word", None)
        after_word = getattr(after_group, "word", None)
        if before_word is not None and after_word is not None:
            shared = min(before_word.font_size, after_word.font_size)
            for word in (before_word, after_word):
                if word.font_size > shared + 1e-6:
                    word.scale(shared / word.font_size)
                    word.font_size = shared

        casing, core, handle, line_group = P.line_parts(fw, fh, pal.accent, u)
        progress = ValueTracker(0)
        plan = P.Plan(before_visual=before_visual, after_visual=after_visual, after_image=after_image,
                      after_panel=after_panel, after_group=after_group, labels=label_group,
                      headline=headline, line_group=line_group, line_casing=casing, line_core=core,
                      handle=handle, frame_width=fw, frame_height=fh, direction=p.direction,
                      center=R.center, before_label=before_label, after_label=after_label,
                      progress=progress, pictures=pictures, before_word=before_word)
        P.reveal(plan, 0)
        return plan

    # ------------------------------------------------------------------- motion
    def _play(self, plan: P.Plan):
        p, m, u = self.p, self.motion, self.layout.unit
        intro = m.t(0.8)
        sweep = m.t(SWEEP[p.speed])
        line_fade = m.t(0.3)
        hold = 1.8 + 1.0 * plan.pictures + (0.5 if plan.headline is not None else 0.0)
        hold += 0.35 if plan.labels is not None else 0.0
        ending = m.exit + 0.15 if self.s.ending == "fade" else 0
        natural = intro + sweep + line_fade + hold + ending
        if self.s.length is None:
            self.target_length = min(self.META.max_length, max(self.META.min_length, natural))
        target_end = self.target_length - ending
        scale = min(1.0, target_end / (natural - ending))
        intro, sweep, line_fade = intro * scale, sweep * scale, line_fade * scale
        hold_time = max(0.0, target_end - intro - sweep - line_fade)

        self.add(plan.before_visual, plan.after_visual)
        if plan.after_group is not None:
            self.add(plan.after_group)
        if plan.labels is not None:
            self.add(plan.labels)
        self.add(plan.line_group, plan.progress)
        intro_parts = [FadeIn(plan.before_visual, scale=1.03, run_time=intro * 0.75, rate_func=ease_out)]
        if plan.headline is not None:
            intro_parts.append(FadeIn(plan.headline, shift=UP * u * 1.5, run_time=intro * 0.55,
                                      rate_func=ease_out))
        self.cue("whoosh")
        self.play(LaggedStart(*intro_parts, lag_ratio=0.28), run_time=intro)

        # Updating the visible root keeps Cairo redrawing it while the tracker animates.
        # A tracker's own updater is suspended by its animation on Manim 0.18.
        plan.after_visual.add_updater(lambda _: P.reveal(plan, plan.progress.get_value()))

        self.cue("whoosh")
        self.cue("pop", offset=sweep * POSTER_AT)
        self.play(plan.progress.animate.set_value(POSTER_AT), run_time=sweep * POSTER_AT,
                  rate_func=linear)
        self.poster()
        self.play(plan.progress.animate.set_value(1.0), run_time=sweep * (1 - POSTER_AT),
                  rate_func=linear)
        plan.after_visual.clear_updaters()
        P.reveal(plan, 1.0)
        self.play(FadeOut(plan.line_group, run_time=line_fade))
        if hold_time > 0.05:
            self.wait(hold_time)
