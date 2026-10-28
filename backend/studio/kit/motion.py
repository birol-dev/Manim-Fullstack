"""The shared motion language: entrance/exit styles and timings scaled by energy.

Entrances 0.4-0.8 s easing out, staggers 0.08-0.15 s, exits 0.3-0.5 s. ``energy``
(calm / normal / punchy) stretches or tightens all of them.
"""

from __future__ import annotations

from manim import (
    DOWN,
    LEFT,
    RIGHT,
    UP,
    AnimationGroup,
    FadeIn,
    FadeOut,
    GrowFromCenter,
    LaggedStart,
    Succession,
    Wait,
    Write,
    rate_functions,
)

ENERGY_SCALE = {"calm": 1.35, "normal": 1.0, "punchy": 0.72}
READING_CPS = 15  # characters per second: the usual subtitle rule


def ease_out(t: float) -> float:
    return rate_functions.ease_out_cubic(t)


def ease_in_out(t: float) -> float:
    return rate_functions.ease_in_out_cubic(t)


def overshoot(t: float) -> float:
    return rate_functions.ease_out_back(t)


class Motion:
    def __init__(self, energy: str = "normal", unit: float = 0.08):
        self.k = ENERGY_SCALE.get(energy, 1.0)
        self.energy = energy
        self.unit = unit  # 1% of the frame's short side

    # Durations
    @property
    def enter(self) -> float:
        return 0.6 * self.k

    @property
    def exit(self) -> float:
        return 0.4 * self.k

    @property
    def stagger(self) -> float:
        return 0.12 * self.k

    def t(self, seconds: float) -> float:
        """Any duration, scaled by energy."""
        return seconds * self.k

    @staticmethod
    def reading_time(text: str, minimum: float = 1.0) -> float:
        """How long *text* must stay on screen to be read."""
        return minimum + len(text or "") / READING_CPS

    # Entrances
    def appear(self, mobject, style: str = "rise", run_time: float | None = None, delay: float = 0.0):
        """Entrance animation: rise, drop, slide_left, slide_right, fade, pop, grow, write."""
        rt = run_time if run_time is not None else self.enter
        d = self.unit * 4
        if style == "rise":
            anim = FadeIn(mobject, shift=UP * d, run_time=rt, rate_func=ease_out)
        elif style == "drop":
            anim = FadeIn(mobject, shift=DOWN * d, run_time=rt, rate_func=ease_out)
        elif style == "slide_left":
            anim = FadeIn(mobject, shift=LEFT * d * 2, run_time=rt, rate_func=ease_out)
        elif style == "slide_right":
            anim = FadeIn(mobject, shift=RIGHT * d * 2, run_time=rt, rate_func=ease_out)
        elif style == "pop":
            anim = FadeIn(mobject, scale=0.6, run_time=rt, rate_func=overshoot)
        elif style == "grow":
            anim = GrowFromCenter(mobject, run_time=rt, rate_func=overshoot)
        elif style == "write":
            anim = Write(mobject, run_time=max(rt, 0.9 * self.k))
        else:
            anim = FadeIn(mobject, run_time=rt, rate_func=ease_out)
        if delay > 0:
            return Succession(Wait(delay), anim)
        return anim

    def appear_each(self, mobjects, style: str = "rise", lag: float | None = None, run_time: float | None = None):
        """Staggered entrance of several mobjects (lag in seconds between starts)."""
        mobjects = list(mobjects)
        if not mobjects:
            return Wait(0.01)
        rt = run_time if run_time is not None else self.enter
        lag = self.stagger if lag is None else lag
        return LaggedStart(*[self.appear(m, style, run_time=rt) for m in mobjects], lag_ratio=(lag / rt) if rt else 0)

    def leave(self, *mobjects, style: str = "fade", run_time: float | None = None):
        rt = run_time if run_time is not None else self.exit
        d = self.unit * 3
        shifts = {"sink": DOWN * d, "lift": UP * d}
        return AnimationGroup(*[
            FadeOut(m, shift=shifts.get(style, 0 * UP), run_time=rt, rate_func=rate_functions.ease_in_cubic)
            for m in mobjects
        ])
