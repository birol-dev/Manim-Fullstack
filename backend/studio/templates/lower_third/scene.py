"""Lower third: a name card that slides in at the bottom, holds, then slides away.

The poster is taken while the card is fully on screen, so the gallery shows the
finished strip. With a transparent background (the presets' default) the export is
a MOV with an alpha channel, ready to lay over a camera clip.
"""

from __future__ import annotations

from manim import DOWN, LEFT, RIGHT, UP, FadeIn, FadeOut, GrowFromCenter, LaggedStart

from studio.kit import StudioScene, ease_out, overshoot

from . import parts as P
from .schema import META, Params

SIZES = {
    "landscape": (44, 28),
    "square": (40, 27),
    "portrait": (38, 26),
}
MAX_WIDTH = {"landscape": 0.82, "square": 0.90, "portrait": 0.94}


class Template(StudioScene):
    Params = Params
    META = META
    logo_region = "top-right"
    logo_height = 6

    def build(self):
        self.pal = P.Palette(self.theme, self.p.accent)
        self.u = self.layout.unit
        strip = self._compose()
        self._play(strip)

    # ------------------------------------------------------------------ layout
    def _shape(self) -> str:
        lay = self.layout
        if lay.is_landscape:
            return "landscape"
        if lay.is_portrait:
            return "portrait"
        return "square"

    def _compose(self) -> P.Strip:
        """The strip, placed in the safe area (used by tests without animating)."""
        p, lay, u = self.p, self.layout, self.layout.unit
        shape = self._shape()
        name_size, role_size = SIZES[shape]
        if getattr(self, "pal", None) is None:
            self.pal = P.Palette(self.theme, p.accent)
        strip = P.build(p.style, p.name, p.role, self.pal, unit=u, name_size=name_size,
                        role_size=role_size, max_width=min(lay.safe.width * MAX_WIDTH[shape],
                                                         lay.safe.width - 3.2 * u))

        S = lay.safe
        inset = 1.6 * u
        x = {"left": S.left + inset + strip.width / 2,
             "right": S.right - inset - strip.width / 2,
             "center": S.center[0]}[p.side]
        y = S.bottom + 0.09 * S.height + strip.height / 2
        strip.move_to([x, y, 0])
        if strip.get_top()[1] > S.top:
            strip.shift([0, S.top - strip.get_top()[1], 0])
        if strip.get_bottom()[1] < S.bottom:
            strip.shift([0, S.bottom - strip.get_bottom()[1], 0])
        return strip

    # ------------------------------------------------------------------- motion
    def _play(self, strip: P.Strip):
        p, lay, m, u = self.p, self.layout, self.motion, self.layout.unit
        intro = m.t(0.9)
        outro = m.t(0.5)
        hold = float(p.hold)
        ending = m.exit + 0.15 if self.s.ending == "fade" else 0
        natural = intro + hold + outro + ending
        if self.s.length is None:
            self.target_length = min(self.META.max_length, max(self.META.min_length, natural))
        target_end = self.target_length - ending
        scale = min(1.0, target_end / (intro + hold + outro))
        intro, outro = intro * scale, outro * scale
        hold_time = max(0.0, target_end - intro - outro)

        if p.side == "left":
            slide = LEFT * (strip.width + 4 * u)
        elif p.side == "right":
            slide = RIGHT * (strip.width + 4 * u)
        else:
            slide = DOWN * (strip.height + 4 * u)

        pieces = [FadeIn(strip.card_group, shift=slide, run_time=intro * 0.8, rate_func=ease_out)]
        if strip.marker is not None:
            pieces.append(GrowFromCenter(strip.marker, run_time=intro * 0.6, rate_func=overshoot))
        if strip.bar is not None:
            pieces.append(GrowFromCenter(strip.bar, run_time=intro * 0.6, rate_func=overshoot))
        lines = [line for line in (strip.name, strip.role) if line is not None]
        if lines:
            pieces.append(LaggedStart(
                *[FadeIn(line, shift=UP * u * 1.4, run_time=intro * 0.55, rate_func=ease_out)
                  for line in lines], lag_ratio=0.24))
        self.cue("whoosh")
        self.cue("pop", offset=intro * 0.55)
        self.play(LaggedStart(*pieces, lag_ratio=0.22), run_time=intro)
        self.poster()

        if hold_time > 0.05:
            self.wait(hold_time)
        if outro > 0.01:
            self.cue("whoosh")
            self.play(FadeOut(strip, shift=-slide * 0.6, run_time=outro), run_time=outro)
        # The intro animates the individual pieces; remove those roots too.
        self.remove(*strip.get_family())
