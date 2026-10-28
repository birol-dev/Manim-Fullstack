"""Local effects for the celebration card (the kit has no burst confetti, sparkles or live shapes).

Everything here is a pure function of one clock, so the poster, the storyboard and the
exported video agree: ``Clock`` is advanced by the scene's ``dt`` every frame (also by the
single big step of a skipped preview), and ``Live`` / ``Party`` redraw themselves from it.
"""

from __future__ import annotations

import math
import random

import numpy as np
from manim import Circle, Mobject, ParametricFunction, Polygon, Star, VGroup

try:  # Manim >= 0.18
    from manim import CapStyleType
except ImportError:  # pragma: no cover
    CapStyleType = None


# -- color helpers ---------------------------------------------------------------------------
def luminance(color: str) -> float:
    c = color.lstrip("#")
    r, g, b = (int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))

    def lin(v):
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def readable(candidates, background: str, fallback: str, minimum: float = 3.0) -> str:
    """The first candidate color that reads on *background*, else *fallback*."""
    for color in candidates:
        if color and contrast(color, background) >= minimum:
            return color
    return fallback


def _rgb(color: str):
    c = color.lstrip("#")
    return [int(c[i:i + 2], 16) for i in (0, 2, 4)]


def blend(base: str, over: str, amount: float) -> str:
    a, b = _rgb(base), _rgb(over)
    return "#%02X%02X%02X" % tuple(round(x + (y - x) * amount) for x, y in zip(a, b))


def vivid(candidates, background: str, count: int = 2, amount: float = 0.3):
    """The colors that stay colorful when laid faintly over *background* (blue over yellow turns gray)."""
    usable = [c for c in candidates if luminance(c) > 0.03]
    score = lambda c: max(_rgb(blend(background, c, amount))) - min(_rgb(blend(background, c, amount)))  # noqa: E731
    ranked = sorted(usable or list(candidates), key=score, reverse=True)
    return (ranked * count)[:count]


def on_color(background: str, *options: str) -> str:
    """Whichever option has the best contrast on *background*."""
    return max(options, key=lambda c: contrast(c, background))


# -- clock and live shapes -------------------------------------------------------------------
class Clock(Mobject):
    """An invisible mobject that counts seconds (``.t``) as the scene plays."""

    def __init__(self):
        super().__init__()
        self.t = 0.0
        self.add_updater(self._tick)

    def _tick(self, mob, dt):
        self.t += dt


class Live(VGroup):
    """A group redrawn every frame from ``factory(t)``, which returns an iterable of shapes."""

    def __init__(self, clock: Clock, factory):
        super().__init__()
        self._clock = clock
        self._factory = factory
        self.add_updater(self._refresh)
        self._refresh(self)

    def _refresh(self, mob):
        self.submobjects = list(self._factory(self._clock.t) or [])


def ease_out(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def ease_out_back(x: float, s: float = 1.9) -> float:
    x = min(max(x, 0.0), 1.0)
    return 1 + (s + 1) * (x - 1) ** 3 + s * (x - 1) ** 2


# -- decoration ------------------------------------------------------------------------------
def sparkle(center, radius: float, color: str, opacity: float = 0.95, angle: float = 0.0):
    """A four-point twinkle star."""
    star = Star(n=4, outer_radius=radius, inner_radius=radius * 0.27, start_angle=math.pi / 2 + angle)
    star.set_fill(color, opacity=opacity).set_stroke(width=0)
    return star.move_to(center)


def glow(center, radius: float, color: str, steps: int = 24, total: float = 0.18):
    """A soft round glow: many stacked, very faint discs, so the edge fades out smoothly."""
    group = VGroup()
    for i in range(steps):
        disc = Circle(radius=radius * (1 - i * 0.85 / steps))
        disc.set_fill(color, opacity=total / steps * 1.7).set_stroke(width=0)
        group.add(disc)
    return group.move_to(center)


def squiggle(width: float, color: str, stroke: float = 7.0, amplitude: float = 0.075, waves: float | None = None):
    """A hand-drawn looking wavy underline of the given width, centered at the origin."""
    waves = waves if waves is not None else max(2.0, width / 0.62)
    curve = ParametricFunction(
        lambda t: np.array([(t - 0.5) * width, amplitude * math.sin(t * waves * 2 * math.pi), 0.0]),
        t_range=[0, 1, 1 / (waves * 10)],
    )
    curve.set_fill(opacity=0).set_stroke(color, width=stroke)
    if CapStyleType is not None:
        try:
            curve.set_cap_style(CapStyleType.ROUND)
        except Exception:  # pragma: no cover - cosmetic only
            pass
    return curve


# -- confetti --------------------------------------------------------------------------------
class _Piece:
    __slots__ = ("mob", "base", "x0", "y0", "vx", "vy", "k", "g", "delay", "life", "spin", "theta0", "flip", "phi0",
                 "sway", "sway_w", "sway_ph", "alive", "alpha")


def _piece_shape(kind: str, size: float):
    if kind == "circle":
        return Circle(radius=size * 0.34)
    if kind == "tri":
        r = size * 0.5
        pts = [[r * math.cos(a), r * math.sin(a), 0] for a in (math.pi / 2, math.pi / 2 + 2.094, math.pi / 2 + 4.189)]
        return Polygon(*pts)
    w, h = (size, size * 0.46) if kind == "rect" else (size * 1.9, size * 0.2)  # rect / ribbon
    return Polygon([-w / 2, -h / 2, 0], [w / 2, -h / 2, 0], [w / 2, h / 2, 0], [-w / 2, h / 2, 0])


class Party(VGroup):
    """Confetti from the bottom corners ("cannons"), out of one point ("burst") or from above ("rain").

    Each piece's position, tumble and fade are closed-form functions of its age, so the group
    can be drawn at any moment (the poster jumps straight to the best one).
    """

    def __init__(self, clock: Clock, start: float, *, colors, frame_w: float, frame_h: float, mode: str = "cannons",
                 origin=(0.0, 0.0), count: int = 64, seed: int = 3, size: float = 0.3):
        super().__init__()
        self.clock = clock
        self.start = start
        self.end = start
        rng = random.Random(seed)
        reach = min(frame_w, frame_h)
        pieces = []
        for i in range(count):
            kind = rng.choices(["rect", "tri", "circle", "ribbon"], weights=[5, 2, 2, 1.4])[0]
            p = _Piece()
            p.mob = _piece_shape(kind, size * rng.uniform(0.75, 1.3))
            p.mob.move_to([0, 0, 0])
            p.mob.set_fill(colors[i % len(colors)], opacity=1).set_stroke(width=0)
            p.base = p.mob.points.copy()
            p.k, p.g = 1.75, 5.0
            if mode == "cannons":
                side = -1 if i % 2 == 0 else 1
                p.x0 = side * (frame_w / 2 - 0.25)
                p.y0 = -frame_h / 2 + 0.25
                angle = math.radians(rng.uniform(52, 82))
                speed = max(frame_h, reach * 1.5) * rng.uniform(0.5, 1.15) * 0.92
                p.vx, p.vy = -side * speed * math.cos(angle), speed * math.sin(angle)
                p.delay = rng.uniform(0.0, 0.18)
                p.life = rng.uniform(3.6, 5.0)
            elif mode == "burst":
                p.x0, p.y0 = origin
                angle = rng.uniform(0, math.tau)
                speed = reach * rng.uniform(0.35, 1.35)
                p.vx, p.vy = speed * math.cos(angle), speed * math.sin(angle) + reach * 0.25
                p.delay = rng.uniform(0.0, 0.1)
                p.life = rng.uniform(3.2, 4.6)
            else:  # rain
                p.x0 = rng.uniform(-frame_w / 2, frame_w / 2)
                p.y0 = frame_h / 2 + rng.uniform(0.3, 1.4)
                p.vx, p.vy = rng.uniform(-0.7, 0.7), -rng.uniform(0.5, 1.6)
                p.k, p.g = 1.3, 3.2
                p.delay = rng.uniform(0.0, 1.7)
                p.life = rng.uniform(4.4, 6.0)
            p.spin = rng.uniform(-6, 6)
            p.theta0 = rng.uniform(0, math.tau)
            p.flip = rng.uniform(5, 11)
            p.phi0 = rng.uniform(0, math.tau)
            p.sway = rng.uniform(0.05, 0.28)
            p.sway_w = rng.uniform(2.0, 4.0)
            p.sway_ph = rng.uniform(0, math.tau)
            p.alive = True
            p.alpha = 1.0
            self.end = max(self.end, start + p.delay + p.life)
            pieces.append(p)
            self.add(p.mob)
        self._pieces = pieces
        self.add_updater(self._refresh)
        self._refresh(self)

    def _refresh(self, mob):
        t = self.clock.t - self.start
        for p in self._pieces:
            age = t - p.delay
            if age < 0 or age > p.life:
                if p.alive:
                    p.mob.points = np.zeros((0, 3))
                    p.alive = False
                continue
            e = 1 - math.exp(-p.k * age)
            x = p.x0 + p.vx * e / p.k + p.sway * math.sin(p.sway_ph + p.sway_w * age) * (1 - math.exp(-2 * age))
            y = p.y0 + (p.vy + p.g / p.k) * e / p.k - p.g * age / p.k
            theta = p.theta0 + p.spin * age
            sy = math.cos(p.phi0 + p.flip * age)
            c, s = math.cos(theta), math.sin(theta)
            pts = p.base * np.array([1.0, sy, 1.0])
            rot = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
            p.mob.points = pts @ rot.T + np.array([x, y, 0.0])
            left = p.life - age
            alpha = 1.0 if left > 0.8 else max(left / 0.8, 0.0)
            if not p.alive or abs(alpha - p.alpha) > 0.03:
                p.mob.set_fill(opacity=alpha)
                p.alpha = alpha
            p.alive = True
