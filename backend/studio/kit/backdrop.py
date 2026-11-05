"""Quiet vector backgrounds for the graphic themes. Geometry scales with the frame."""

import math

from manim import Line, VGroup

from .shapes import full_frame


def _line(x1, y1, x2, y2, color, *, width=1.2, opacity=1.0):
    return Line((x1, y1, 0), (x2, y2, 0)).set_stroke(color, width=width, opacity=opacity)


def _registration(width, height, theme):
    """A modular print grid with registration corners outside the content area."""
    left, right = -width * .465, width * .465
    bottom, top = -height * .463, height * .463
    mark = min(width, height) * .037
    lines = VGroup(
        *(_line(x * width, bottom, x * width, top, theme.line, opacity=.42)
          for x in (-.31, -.155, 0, .155, .31)),
        *(_line(left, y * height, right, y * height, theme.line, opacity=.37)
          for y in (-.31, -.155, 0, .155, .31)),
    )
    for x, dx in ((left, 1), (right, -1)):
        for y, dy in ((top, -1), (bottom, 1)):
            lines.add(_line(x, y, x + mark * dx, y, theme.accent(), width=2, opacity=.82),
                      _line(x, y, x, y + mark * dy, theme.text, width=1.4, opacity=.65))
    return VGroup(full_frame(width, height, theme.bg), lines)


def _horizon(width, height, theme):
    """A receding floor and scan-lined sun behind the content."""
    horizon, bottom = -height * .16, -height * .5
    sun_x, sun_y = width * .27, height * .245
    radius = min(width, height) * .125
    rays = VGroup(*(_line(x * width * .22, horizon, x * width, bottom,
                           theme.accent(1), opacity=.22) for x in (-.8, -.6, -.4, -.2, 0, .2, .4, .6, .8)))
    for depth in (0, .08, .19, .36, .61, .92):
        y = horizon + (bottom - horizon) * depth
        rays.add(_line(-width / 2, y, width / 2, y, theme.accent(1), opacity=.21))
    for offset in (-.90, -.70, -.48, -.24, .02, .27, .52, .76, .91):
        span = math.sqrt(1 - offset * offset) * radius
        y = sun_y + offset * radius
        rays.add(_line(sun_x - span, y, sun_x + span, y, theme.accent(), width=2.5, opacity=.27))
    return VGroup(full_frame(width, height, theme.bg, theme.bg2), rays)


def art_background(width, height, theme):
    artwork = theme.tokens.get("artwork")
    if artwork == "registration":
        return _registration(width, height, theme)
    if artwork == "horizon":
        return _horizon(width, height, theme)
    return full_frame(width, height, theme.bg)
