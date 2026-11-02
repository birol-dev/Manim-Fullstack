"""Building blocks: cards, pills, badges, dividers, confetti, QR codes."""

from __future__ import annotations

import random

import numpy as np
from manim import (
    Circle,
    Line,
    Rectangle,
    RoundedRectangle,
    Square,
    ValueTracker,
    VGroup,
)


def card(width: float, height: float, *, color: str, radius: float = 0.2, opacity: float = 1.0,
         stroke: str | None = None, stroke_width: float = 0.0):
    """A filled rounded rectangle (radius clamped to half the short side)."""
    r = max(0.0, min(radius, width / 2 - 1e-3, height / 2 - 1e-3))
    if r <= 0.001:
        shape = Rectangle(width=width, height=height)
    else:
        shape = RoundedRectangle(width=width, height=height, corner_radius=r)
    shape.set_fill(color, opacity=opacity)
    shape.set_stroke(stroke or color, width=stroke_width, opacity=1 if stroke_width else 0)
    return shape


def pill(width: float, height: float, *, color: str, opacity: float = 1.0):
    return card(width, height, color=color, radius=height / 2, opacity=opacity)


def badge(diameter: float, *, color: str):
    return Circle(radius=diameter / 2).set_fill(color, 1).set_stroke(width=0)


def divider(width: float, *, color: str, thickness: float = 4):
    return Line([-width / 2, 0, 0], [width / 2, 0, 0]).set_stroke(color, width=thickness)


def full_frame(width: float, height: float, color: str, color2: str | None = None, direction=None):
    """A background rectangle; with *color2*, a vertical gradient."""
    rect = Rectangle(width=width * 1.02, height=height * 1.02).set_stroke(width=0)
    if color2:
        rect.set_fill([color, color2], opacity=1)
        rect.set_sheen_direction(direction if direction is not None else np.array([0.3, -1.0, 0.0]))
    else:
        rect.set_fill(color, opacity=1)
    return rect


class Confetti(VGroup):
    """Falling, spinning pieces. ``scene.add(c)`` then ``scene.play(c.fall(run_time=3))``.

    Positions come from one tracker, so the cost per frame is small (no Pango).
    """

    def __init__(self, frame_width: float, frame_height: float, colors: list, count: int = 70, seed: int = 7,
                 size: float = 0.14):
        super().__init__()
        rng = random.Random(seed)
        self.t = ValueTracker(0)
        self._pieces = []
        for i in range(count):
            w = size * rng.uniform(0.6, 1.2)
            piece = (Square(side_length=w) if i % 3 else Circle(radius=w / 2.4))
            piece.stretch(rng.uniform(0.35, 0.7), 1)
            piece.set_fill(colors[i % len(colors)], 1).set_stroke(width=0)
            start = np.array([rng.uniform(-0.5, 0.5) * frame_width, frame_height / 2 + rng.uniform(0.2, 2.5), 0])
            velocity = np.array([rng.uniform(-0.6, 0.6), -rng.uniform(1.0, 2.2), 0]) * frame_height / 8
            spin = rng.uniform(-8, 8)
            sway = rng.uniform(0.1, 0.35) * frame_width / 14
            phase = rng.uniform(0, 6.28)
            piece.move_to(start)
            self._pieces.append((piece, start, velocity, spin, sway, phase))
            self.add(piece)
        self._fh = frame_height

        def update(group):
            t = self.t.get_value()
            for piece, start, vel, spin, sway, phase in self._pieces:
                tt = t * 4.0
                pos = start + vel * tt + np.array([sway * np.sin(phase + tt * 2.2), -0.18 * tt * tt, 0])
                piece.move_to(pos)
                piece.rotate(spin * 0.02)

        self.add_updater(update)

    def fall(self, run_time: float = 3.0):
        return self.t.animate(run_time=run_time, rate_func=lambda x: x).set_value(1)


def qr_code(data: str, *, size: float, color: str = "#000000", background: str | None = "#FFFFFF",
            quiet_zone: int = 2):
    """A QR code as squares (needs the ``segno`` package). Returns None when segno is missing."""
    try:
        import segno
    except ImportError:
        return None
    qr = segno.make(data, error="m", micro=False)
    matrix = [list(row) for row in qr.matrix]
    n = len(matrix)
    total = n + 2 * quiet_zone
    cell = size / total
    group = VGroup()
    if background:
        group.add(Square(side_length=size).set_fill(background, 1).set_stroke(width=0))
    origin = np.array([-size / 2 + quiet_zone * cell, size / 2 - quiet_zone * cell, 0])
    for r, row in enumerate(matrix):
        c = 0
        while c < n:
            if row[c]:
                start = c
                while c < n and row[c]:
                    c += 1
                run = c - start
                rect = Rectangle(width=cell * run, height=cell).set_fill(color, 1).set_stroke(width=0)
                rect.move_to(origin + np.array([(start + run / 2) * cell, -(r + 0.5) * cell, 0]))
                group.add(rect)
            else:
                c += 1
    return group
