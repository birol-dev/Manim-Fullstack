"""Shared clearance for particles behind readable foreground content."""

from __future__ import annotations

import numpy as np
import cairo
from manim import Circle
from manim.camera.camera import Camera


def _bounds(mobject):
    points = mobject.get_all_points()
    if not len(points):
        return None
    return points[:, :2].min(axis=0), points[:, :2].max(axis=0)


class ParticleClearance:
    """Clip every decoration's paint around settled and animated foreground.

    Painter order protects opaque ink, but cannot protect letter counters, spaces
    or antialiased edges. Clip fills AND strokes: a ring's empty interior must not
    cause the entire ring to disappear. No opacity/style changes are needed, so
    native lifetime, twinkle and ending fades remain intact.
    """

    def __init__(self, particles, foreground, padding=0.10):
        self.particles = particles
        own_family = {id(m) for m in particles.get_family()}
        self.foreground = tuple(m for m in foreground if m is not None and id(m) not in own_family)
        self.padding = padding
        self.settled = self._regions()
        self._tagged = []

    def _regions(self):
        regions = []
        for mob in self.foreground:
            bounds = _bounds(mob)
            if bounds is not None:
                low, high = bounds
                regions.append((float(low[0] - self.padding), float(low[1] - self.padding),
                                float(high[0] + self.padding), float(high[1] + self.padding),
                                isinstance(mob, Circle)))
        return regions

    def restore(self):
        for mob in self._tagged:
            if hasattr(mob, "_studio_clearance_regions"):
                del mob._studio_clearance_regions
        self._tagged.clear()

    def apply(self):
        regions = tuple(dict.fromkeys(self.settled + self._regions()))
        for piece in self.particles.family_members_with_points():
            # Store only immutable coordinates. Animation copies must not copy a
            # clearance manager and all its references to the rest of the scene.
            piece._studio_clearance_regions = regions
            self._tagged.append(piece)


class ClearanceCamera(Camera):
    """Cairo's native vector drawing with foreground cutouts for decorations."""

    def display_vectorized(self, vmobject, ctx):
        # Manim's AUTO cap/join inherits Cairo state. Isolate every path so a
        # rounded underline cannot change a later icon's pixels (or a fresh
        # reference camera's pixels) when draw batches/cache boundaries change.
        ctx.save()
        try:
            return self._display_clearance_vectorized(vmobject, ctx)
        finally:
            ctx.restore()

    def _display_clearance_vectorized(self, vmobject, ctx):
        regions = getattr(vmobject, "_studio_clearance_regions", ())
        if not regions:
            return super().display_vectorized(vmobject, ctx)
        bounds = _bounds(vmobject)
        if bounds is None:
            return super().display_vectorized(vmobject, ctx)
        low, high = bounds
        stroke = max(vmobject.get_stroke_width(), vmobject.get_stroke_width(background=True))
        extra = stroke * self.cairo_line_width_multiple / 2
        regions = [r for r in regions if high[0] + extra >= r[0] and low[0] - extra <= r[2]
                   and high[1] + extra >= r[1] and low[1] - extra <= r[3]]
        if not regions:
            return super().display_vectorized(vmobject, ctx)
        ctx.save()
        try:
            fill_rule = ctx.get_fill_rule()
            ctx.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
            for x0, y0, x1, y1, ellipse in regions:
                # Subtract one region at a time: overlapping cutouts must form a
                # union, rather than cancel each other under the even/odd rule.
                left, bottom, right, top = ctx.clip_extents()
                ctx.new_path()
                ctx.rectangle(left, bottom, right - left, top - bottom)
                if ellipse:
                    ctx.save()
                    ctx.translate((x0 + x1) / 2, (y0 + y1) / 2)
                    ctx.scale(max((x1 - x0) / 2, 1e-6), max((y1 - y0) / 2, 1e-6))
                    ctx.new_sub_path()
                    ctx.arc(0, 0, 1, 0, 2 * np.pi)
                    ctx.restore()
                else:
                    ctx.rectangle(x0, y0, x1 - x0, y1 - y0)
                ctx.clip()
            ctx.set_fill_rule(fill_rule)
            return super().display_vectorized(vmobject, ctx)
        finally:
            ctx.restore()
