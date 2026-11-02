"""Local helpers for the quiz template: colors, a drawn check mark, and text measuring.

Nothing here is quiz-specific except the planner; the color and text-measuring helpers are
generic and could move into the kit.
"""

from __future__ import annotations

import colorsys
from functools import lru_cache
from types import SimpleNamespace

from manim import CapStyleType, LineJointType, Text, VMobject

from studio.kit import wrap
from studio.kit.fonts import resolve as resolve_font

# --------------------------------------------------------------------------- colors


def _rgb(color: str) -> tuple:
    c = color.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb) -> str:
    return "#%02X%02X%02X" % tuple(int(round(max(0, min(255, v)))) for v in rgb)


def mix(a: str, b: str, t: float) -> str:
    """Blend two hex colors: t=0 gives a, t=1 gives b."""
    ra, rb = _rgb(a), _rgb(b)
    return _hex([x + (y - x) * t for x, y in zip(ra, rb)])


def luminance(color: str) -> float:
    def lin(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(v) for v in _rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def best_ink(on: str, candidates) -> str:
    """The candidate with the highest contrast against *on*."""
    return max(candidates, key=lambda c: contrast(c, on))


def _hsv(color: str) -> tuple:
    r, g, b = (v / 255 for v in _rgb(color))
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return h * 360, s, v


def _closest_hue(colors, target: float, exclude=()):
    best, best_d = None, 999.0
    for c in colors:
        if c in exclude:
            continue
        h, s, v = _hsv(c)
        if s < 0.3 or v < 0.35:
            continue
        d = abs(h - target) % 360
        d = min(d, 360 - d)
        if d < best_d:
            best, best_d = c, d
    return best, best_d


def palette(theme, bg: str) -> SimpleNamespace:
    """Quiz colors derived from the theme: primary, success (green-ish), warn (red-ish), ink on success."""
    primary = theme.accent(0)
    success, dist = _closest_hue(theme.accents, 150)
    if success is None or dist > 55:
        success = "#4ADE80" if theme.dark else "#16A34A"
    warn, dist = _closest_hue(theme.accents, 358, exclude=(primary, success))
    if warn is None or dist > 50:
        warn = "#FB7185" if theme.dark else "#E11D48"
    ink = best_ink(success, [theme.text, theme.bg, "#FFFFFF", "#0B0B0F"])
    return SimpleNamespace(
        bg=bg, surface=theme.surface, text=theme.text, muted=theme.muted, line=theme.line,
        primary=primary, on_primary=theme.on_accent, success=success, warn=warn, ink=ink,
        success_deep=mix(success, "#000000", 0.28),
        dim=lambda c: mix(bg, c, 0.36),
    )


# --------------------------------------------------------------------------- shapes


def check_mark(size: float, color: str, width: float) -> VMobject:
    """A rounded check mark about *size* units wide, centered at the origin."""
    pts = [(-0.5, -0.02), (-0.14, -0.38), (0.5, 0.34)]
    mark = VMobject(joint_type=LineJointType.ROUND, cap_style=CapStyleType.ROUND)
    mark.set_points_as_corners([[x * size, y * size, 0] for x, y in pts])
    mark.set_fill(opacity=0).set_stroke(color, width=width)
    # center the ink box on the origin
    mark.move_to([0, 0, 0])
    return mark


# --------------------------------------------------------------------------- text measuring


@lru_cache(maxsize=64)
def _ref_line(font: str, weight: str) -> float:
    return Text("ÁgjÉ", font=font, weight=weight, font_size=48).height


EXPLANATION_SPACING = 1.06  # tighter than fit_text's default: the explanation is a small paragraph


def line_height(size: float, font: str, weight: str, spacing: float = 1.12) -> float:
    """Distance between baselines of consecutive lines, as fit_text spaces them."""
    return _ref_line(resolve_font(font), weight) * size / 48 * spacing


def lines_at(text: str, width: float, size: float, font: str, weight: str) -> int:
    return len(wrap(text, size=size, width=width, font=resolve_font(font), weight=weight, balance=False))


def fit_size(text: str, width: float, size: float, min_size: float, max_lines: int, font: str, weight: str):
    """(size, lines): what fit_text(width=, size=, min_size=, max_lines=) would choose."""
    current = size
    while True:
        n = lines_at(text, width, current, font, weight)
        if n <= max_lines or current <= min_size:
            return current, min(n, max_lines)
        current = max(min_size, current * 0.92)


@lru_cache(maxsize=64)
def _descender(font: str, weight: str) -> float:
    """How far below the baseline a 'g' reaches at 48pt."""
    both = Text("Hg", font=font, weight=weight, font_size=48).height
    return both - Text("H", font=font, weight=weight, font_size=48).height


DESCENDERS = set("gjpqyQ,;()[]{}|/@$")


def baseline_shift(text: str, size: float, font: str, weight: str) -> float:
    """Upward shift for a single ink-centered line so that every line sits on one baseline.

    Text boxes are the ink of the glyphs, so a line with descenders (g, p, y...) is dragged
    down by half the descender depth; lines without descenders are lifted by the same amount.
    """
    if any(ch in DESCENDERS for ch in text):
        return 0.0
    return _descender(resolve_font(font), weight) * size / 48 / 2


def slot_diameter(letter_size: float, font: str) -> float:
    """Diameter of the letter badge: the cap height of a bold letter, doubled."""
    cap = Text("B", font=resolve_font(font), weight="BOLD", font_size=letter_size).height
    return cap * 2.15
