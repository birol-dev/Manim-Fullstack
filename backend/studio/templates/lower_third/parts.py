"""Pieces of the lower third: the palette, the measured card and its text.

The strip is built in a local frame centered at the origin, so the scene can place
it for any side and tests can measure it without rendering pixels.
"""

from __future__ import annotations

import numpy as np
import re
from manim import Circle, VGroup

from studio.kit import fit_text, shapes
from studio.kit.text import measure

MIN_SIZE = 24.0


def full_text(source: str, **options):
    """Wrap unusually long names at letter boundaries instead of making tiny type."""
    chunks = []
    for token in re.split(r"(\s+)", source):
        line = ""
        for char in token:
            if line and measure(line + char, size=MIN_SIZE, font=options["font"],
                                weight=options["weight"]) > options["width"] * 0.94:
                chunks.append(line + "\n")
                line = ""
            line += char
        chunks.append(line)
    text = "".join(chunks)
    fitted = fit_text(text, min_size=MIN_SIZE, **options)
    if is_cut(fitted, source):
        # The name matters more than keeping the card to a fixed number of lines.
        fitted = fit_text(text, min_size=MIN_SIZE,
                          **{**options, "size": MIN_SIZE, "max_lines": max(len(source), 1)})
    return fitted


def _rgb(value: str) -> tuple:
    h = value.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _channel(value: float) -> float:
    return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


def luminance(value: str) -> float:
    red, green, blue = (_channel(c) for c in _rgb(value))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(first: str, second: str) -> float:
    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def best_on(background: str, *candidates: str) -> str:
    return max(candidates, key=lambda candidate: contrast(background, candidate))


class Palette:
    """Theme tokens plus the two contrast-safe colors the card needs."""

    def __init__(self, theme, accent: str | None = None):
        self.theme = theme
        self.font = theme.font
        self.display_weight = theme.display_weight
        self.surface = theme.surface
        self.text = theme.text
        self.muted = theme.muted
        self.line = theme.line
        self.radius = theme.radius
        self.accent = accent or theme.accent(0)
        self.on_accent = best_on(self.accent, theme.on_accent, "#FFFFFF", "#111111", theme.text, theme.bg)


class Strip(VGroup):
    """A placed card: the card itself, its marker, the two text lines and the underline."""

    def __init__(self):
        super().__init__()
        self.card_group = None
        self.marker = None
        self.bar = None
        self.text = None
        self.name = None
        self.role = None
        self.card = None
        self.shadow = None


def is_cut(mobject, source: str) -> bool:
    """True when fit_text had to drop words with an ellipsis."""
    shown = "".join(getattr(line, "original_text", "") for line in (mobject.lines or [mobject]))
    return shown.count("…") > (source or "").count("…")


def smallest_size(mobject) -> float:
    sizes = [getattr(line, "font_size", MIN_SIZE) for line in (mobject.lines or [mobject])]
    return min(sizes) if sizes else MIN_SIZE


def build(style: str, name_text: str, role_text: str, pal: Palette, *, unit: float,
          name_size: float, role_size: float, max_width: float) -> Strip:
    """One measured strip, centered at the origin and no wider than *max_width*."""
    pad_x, pad_y = 4.0 * unit, 2.6 * unit
    marker_w = {"panel": 1.4 * unit, "block": 1.7 * unit, "underline": 0.0}[style]
    gap = 2.0 * unit if marker_w else 0.0
    text_w = max(max_width - 2 * pad_x - marker_w - gap, 2.0 * unit)
    weight = pal.display_weight
    on_solid = style == "block"

    name = full_text(name_text, width=text_w, size=name_size, max_lines=2,
                    font=pal.font, weight=weight, color=pal.on_accent if on_solid else pal.text,
                    align="left", line_spacing=1.04)
    role = None
    if role_text.strip():
        role = full_text(role_text, width=text_w, size=role_size, max_lines=2,
                        font=pal.font, weight="NORMAL",
                        color=pal.on_accent if on_solid else pal.muted,
                        align="left", line_spacing=1.06)
        if on_solid:
            role.set_opacity(0.86)

    block = VGroup(name, *([role] if role is not None else []))
    if role is not None:
        block.arrange(np.array([0, -1.0, 0]), aligned_edge=np.array([-1.0, 0, 0]),
                      buff=max(1.2 * unit, 0.20 * name.height))
    bottom_extra = 1.6 * unit if style == "underline" else 0.0
    height = max(block.height + 2 * pad_y + bottom_extra, 2.6 * unit)
    width = max(2 * pad_x + marker_w + gap + block.width, 22.0 * unit)
    text_y = bottom_extra / 2 if style == "underline" else 0.0
    text_x = -width / 2 + pad_x + marker_w + gap

    card = shapes.card(width, height, color=pal.accent if on_solid else pal.surface,
                       radius=min(pal.radius, height / 2.4),
                       stroke=None if on_solid else pal.line, stroke_width=0 if on_solid else 1.4)
    shadow = card.copy().set_fill(pal.text, 0.16).set_stroke(width=0)
    shadow.shift([0.12 * unit, -0.28 * unit, 0])

    marker = None
    if style == "panel":
        bar_h = min(max(block.height + 0.8 * unit, 2.2 * unit), height - 1.6 * unit)
        marker = shapes.card(marker_w, bar_h, color=pal.accent, radius=marker_w / 2)
        marker.move_to([-width / 2 + pad_x + marker_w / 2, text_y, 0])
    elif style == "block":
        diameter = min(max(block.height * 0.8, 1.5 * unit), 2.2 * unit)
        marker = Circle(radius=diameter / 2).set_fill(pal.on_accent, 0.9).set_stroke(width=0)
        marker.move_to([-width / 2 + pad_x + marker_w / 2, text_y, 0])

    block.move_to([text_x + block.width / 2, text_y, 0])

    bar = None
    if style == "underline":
        bar_w = max(width - 2 * pad_x * 0.7, 2.0 * unit)
        bar = shapes.card(bar_w, 0.9 * unit, color=pal.accent, radius=0.45 * unit)
        bar.move_to([0, -height / 2 + 1.3 * unit, 0])

    strip = Strip()
    strip.card_group = VGroup(shadow, card)
    strip.shadow, strip.card = shadow, card
    strip.marker, strip.bar = marker, bar
    strip.text, strip.name, strip.role = block, name, role
    strip.add(strip.card_group)
    if marker is not None:
        strip.add(marker)
    strip.add(block)
    if bar is not None:
        strip.add(bar)
    return strip
