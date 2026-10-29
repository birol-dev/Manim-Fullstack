"""Shared clearance for particles behind readable foreground content."""

from __future__ import annotations

import numpy as np


def _bounds(mobject):
    points = mobject.get_all_points()
    if not len(points):
        return None
    return points[:, :2].min(axis=0), points[:, :2].max(axis=0)


class ParticleClearance:
    """Hide whole pieces intersecting a foreground line/mark, without a backplate.

    Painter order protects opaque ink, but cannot protect letter counters, spaces
    or antialiased edges. Keep both the settled layout and its animated geometry
    clear. Opacities are restored *before* particle updaters run so pieces can
    leave a protected region and resume their own lifetime/fade normally.
    """

    def __init__(self, particles, foreground, padding=0.10):
        self.particles = particles
        self.foreground = tuple(m for m in foreground if m is not None)
        self.padding = padding
        self.settled = [bounds for mob in self.foreground if (bounds := _bounds(mob)) is not None]
        self._hidden = []

    def restore(self):
        for mob, fill, stroke, background_stroke in self._hidden:
            mob.fill_rgbas = fill
            mob.stroke_rgbas = stroke
            mob.background_stroke_rgbas = background_stroke
        self._hidden.clear()

    def apply(self):
        regions = self.settled + [bounds for mob in self.foreground if (bounds := _bounds(mob)) is not None]
        if not regions:
            return
        lows, highs = (np.array(values) for values in zip(*regions))
        lows -= self.padding
        highs += self.padding
        for piece in self.particles.family_members_with_points():
            bounds = _bounds(piece)
            if bounds is None:
                continue
            low, high = bounds
            if np.any(np.all(high >= lows, axis=1) & np.all(low <= highs, axis=1)):
                self._hidden.append((piece, piece.fill_rgbas.copy(), piece.stroke_rgbas.copy(),
                                     piece.background_stroke_rgbas.copy()))
                piece.set_opacity(0, family=False)
