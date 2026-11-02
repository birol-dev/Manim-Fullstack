"""An unhurried sequence: picture, caption, soft change, repeat."""
from __future__ import annotations

import logging

from manim import FadeIn, Group, Line, VGroup, linear

from studio.kit import StudioScene, label, shapes
from studio.kit.layout import Region

from . import parts as P
from .schema import META, Params

logger = logging.getLogger(__name__)


class Template(StudioScene):
    Params = Params
    META = META
    logo_region = "top-right"
    logo_height = 6

    def _compose(self):
        lay, theme, p = self.layout, self.theme, self.p
        u, S = lay.unit, lay.safe
        self.accent = p.accent or theme.accent(0)
        top = S.top - 10 * u  # a clear logo corner, with or without a logo
        self.heading = None
        if p.title:
            self.heading = P.text(theme.display(p.title), width=S.width, height=S.height * .32,
                size=54, font=theme.font, weight=theme.display_weight, color=theme.text,
                emphasis_color=self.accent)
            self.heading.move_to([S.center[0], top - self.heading.height / 2, 0])
            top -= self.heading.height + 3 * u
        self.picture_region = Region(S.left, S.right, top, S.bottom + 7 * u)
        return [self._slide(slide, index) for index, slide in enumerate(p.slides)]

    def _slide(self, slide, index):
        R, theme, u = self.picture_region, self.theme, self.layout.unit
        photo = rings = None
        path = self.asset(slide.picture)
        if path:
            try:
                photo = P.cover(path, R.width, R.height)
            except Exception as exc:  # an unreadable upload still makes a finished card
                logger.warning("Picture could not be opened; using a color panel: %s", exc)
        if photo is None:
            picture, rings = P.empty_panel(R.width, R.height, theme, self.accent, index)
        else:
            picture = photo
        picture.move_to(R.center)
        caption = None
        parts = [picture]
        if slide.caption:
            words = P.text(slide.caption, width=R.width - 8 * u, height=R.height * .72,
                size=32, font=theme.font, color=theme.text, align="left")
            box = shapes.card(R.width - 4 * u, words.height + 4 * u, color=theme.surface,
                              radius=theme.radius)
            caption = VGroup(box, words)
            y = (R.top - 2 * u - caption.height / 2 if self.p.caption_position == "top"
                 else R.bottom + 2 * u + caption.height / 2)
            caption.move_to([R.center[0], y, 0])
            parts.append(caption)
        count = label(f"{index + 1} / {len(self.p.slides)}", size=24, font=theme.font, color=theme.muted)
        count.move_to([R.right - count.width / 2, self.layout.safe.bottom + 2 * u, 0])
        rail_end = count.get_left()[0] - 4 * u
        width = (rail_end - R.left) / len(self.p.slides)
        rail = VGroup(*[Line([R.left + i * width, count.get_center()[1], 0],
                            [R.left + (i + 1) * width - u, count.get_center()[1], 0])
                        .set_stroke(self.accent if i <= index else theme.line, width=3)
                       for i in range(len(self.p.slides))])
        group = Group(*parts, rail, count)
        group.picture, group.photo, group.rings, group.caption = picture, photo, rings, caption
        return group

    def build(self):
        slides = self._compose()
        if self.heading is not None:
            self.add(self.heading)
        seconds = self.p.seconds_per_slide
        ending = self.motion.exit + .15 if self.s.ending == "fade" else 0
        self.target_length = len(slides) * seconds + ending
        transition = min(self.motion.t(.65), seconds * .3)
        previous = None
        for index, slide in enumerate(slides):
            self.cue("whoosh")
            self.play(FadeIn(slide), run_time=transition)
            if previous is not None:
                self.remove(previous)
            # Captions stay still while only the picture gently moves.
            hold = seconds - transition
            if slide.photo is not None:
                self.play(P.GentleZoom(slide.photo, run_time=hold))
            else:
                self.play(slide.rings.animate(rate_func=linear).scale(1.04), run_time=hold)
            if index == 0:
                self.poster()
            previous = slide
