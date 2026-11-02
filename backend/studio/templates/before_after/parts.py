"""Pieces of the before & after template: palette, photo covers, panels and labels.

The sweeping reveal is one image whose alpha edge moves (or one growing color
rectangle), so a picture is still drawn only once per frame. The scene owns the
animation; these helpers build and measure the still pieces.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os
import re

import numpy as np
from manim import Circle, ImageMobject, Line, Rectangle, VGroup

from studio.kit import fit_text, media, shapes
from studio.kit.text import measure


def full_text(source: str, **options):
    """Keep all words, splitting an overlong label at readable letter boundaries."""
    chunks = []
    for token in re.split(r"(\s+)", source):
        marked = token.startswith("*") and token.endswith("*") and len(token) > 2
        word = token[1:-1] if marked else token
        lines, line = [], ""
        for char in word:
            if line and measure(line + char, size=24, font=options["font"],
                                weight=options["weight"]) > options["width"] * 0.94:
                lines.append(line)
                line = ""
            line += char
        lines.append(line)
        chunks.append("\n".join(f"*{part}*" if marked else part for part in lines))
    source = "".join(chunks)
    fitted = fit_text(source, min_size=24, **options)
    if any("…" in line.original_text for line in fitted.lines) and "…" not in source:
        fitted = fit_text(source, min_size=24,
                          **{**options, "size": 24, "max_lines": max(len(source), 1)})
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


def shout(text: str, locale: str) -> str:
    """Upper case for labels; Turkish and Azeri keep their dotted and dotless i."""
    if locale[:2] in ("tr", "az"):
        text = text.replace("i", "İ").replace("ı", "I")
    return text.upper()


class Palette:
    def __init__(self, theme, accent: str | None = None):
        self.theme = theme
        self.font = theme.font
        self.display_weight = theme.display_weight
        self.surface = theme.surface
        self.text = theme.text
        self.muted = theme.muted
        self.line = theme.line
        self.bg = theme.bg
        self.before_bg = theme.bg2
        self.radius = theme.radius
        self.accent = accent or theme.accent(0)
        self.on_accent = best_on(self.accent, theme.on_accent, "#FFFFFF", "#111111", theme.text, theme.bg)
        self.on_before = best_on(self.before_bg, theme.text, "#111111", "#FFFFFF", theme.bg2)


@lru_cache(maxsize=16)
def _cover_pixels(path: str, mtime: float, ratio: float, max_px: int):
    from PIL import Image

    # Uploaded crops are already files; use the same EXIF/alpha preparation as
    # other templates before covering this template's rectangular picture area.
    img = Image.fromarray(media.image(path, max_px=max_px).pixel_array)
    width, height = img.size
    if width / height > ratio:
        new_width = max(1, int(round(height * ratio)))
        left = (width - new_width) // 2
        img = img.crop((left, 0, left + new_width, height))
    else:
        new_height = max(1, int(round(width / ratio)))
        top = max(0, int((height - new_height) * 0.4))  # keep a little more of the top
        img = img.crop((0, top, width, top + new_height))
    if max(img.size) > max_px:
        img.thumbnail((max_px, max_px), Image.LANCZOS)
    return np.array(img)


def cover(path: str, width: float, height: float, max_px: int = 1600) -> ImageMobject:
    """The picture cropped to fill *width* x *height* exactly (object-fit: cover)."""
    pixels = _cover_pixels(path, os.path.getmtime(path), width / height, max_px)
    mob = ImageMobject(pixels)
    mob.stretch_to_fit_width(width)
    mob.stretch_to_fit_height(height)
    return mob


def after_picture(path: str, width: float, height: float, max_px: int = 1600) -> ImageMobject:
    """The after picture, starting invisible: the scene raises its alpha at the sweep edge."""
    mob = cover(path, width, height, max_px)
    mob.reveal_alpha = mob.pixel_array[:, :, 3].copy()
    mob.pixel_array[:, :, 3] = 0
    return mob


def color_panel(width: float, height: float, color: str) -> Rectangle:
    rect = Rectangle(width=width, height=height).set_fill(color, 1).set_stroke(width=0)
    rect.move_to([0, 0, 0])
    return rect


def placeholder_word(text: str, color: str, pal: Palette, *, width: float, size: float,
                     max_lines: int, locale: str):
    return full_text(shout(text, locale), width=width, size=size, max_lines=max_lines,
                    font=pal.font, weight=pal.display_weight, color=color, align="center", line_spacing=1.0)


def label_pill(text: str, pal: Palette, *, unit: float, size: float, fill: str, ink: str,
               max_width: float, locale: str, stroke: bool = False):
    """A solid rounded label; None when the person left the label empty."""
    if not text.strip():
        return None
    pad_x, pad_y = 2.4 * unit, 1.5 * unit
    words = full_text(shout(text, locale), width=max_width - 2 * pad_x, size=size, max_lines=2,
                     font=pal.font, weight="BOLD", color=ink, align="center", line_spacing=1.0)
    height = words.height + 2 * pad_y
    pill = shapes.card(words.width + 2 * pad_x, height, color=fill, radius=height / 2,
                       stroke=pal.line if stroke else None, stroke_width=1.2 if stroke else 0)
    words.move_to(pill.get_center())
    return VGroup(pill, words)


def headline_block(text: str, pal: Palette, *, width: float, size: float, unit: float, locale: str):
    """Plain display text above the pictures, with the kit's highlighted words."""
    if not text.strip():
        return None
    shown = pal.theme.display(text) if pal.theme.case != "upper" else shout(text, locale)
    words = full_text(shown, width=width, size=size,
                     max_lines=3, font=pal.font, weight=pal.display_weight, color=pal.text,
                     emphasis_color=pal.accent, align="center", line_spacing=1.08)
    return VGroup(words)


def line_parts(frame_width: float, frame_height: float, accent: str, unit: float) -> tuple:
    """A visible sweep line: dark casing, white core and a colored handle."""
    casing = Line([-frame_width / 2, -frame_height / 2, 0], [-frame_width / 2, frame_height / 2, 0])
    casing.set_stroke("#000000", width=8, opacity=0.32)
    core = Line([-frame_width / 2, -frame_height / 2, 0], [-frame_width / 2, frame_height / 2, 0])
    core.set_stroke("#FFFFFF", width=4)
    radius = 2.8 * unit
    disc = Circle(radius=radius).set_fill(accent, 1).set_stroke("#FFFFFF", width=3)
    ink = best_on(accent, "#FFFFFF", "#111111")
    grips = VGroup(*[Line([x * unit, -1.0 * unit, 0], [x * unit, 1.0 * unit, 0])
                     .set_stroke(ink, width=2.4) for x in (-0.6, 0.6)])
    handle = VGroup(disc, grips)
    casing.set_z_index(3)
    core.set_z_index(3.1)
    handle.set_z_index(3.2)
    return casing, core, handle, VGroup(casing, core, handle)


@dataclass
class Plan:
    before_visual: object
    after_visual: object
    after_image: object | None
    after_panel: object | None
    after_group: object | None
    labels: object | None
    headline: object | None
    line_group: object
    line_casing: object
    line_core: object
    handle: object
    frame_width: float
    frame_height: float
    direction: str
    center: object
    before_label: object | None
    after_label: object | None
    progress: object
    pictures: int
    before_word: object | None = None


def reveal(plan: Plan, value: float) -> None:
    """Reveal After from the far edge, keeping Before first in reading order."""
    p = float(np.clip(value, 0.0, 1.0))
    horizontal = plan.direction == "horizontal"
    cx, cy, _ = plan.center
    fw, fh = plan.frame_width, plan.frame_height
    edge = cx + fw / 2 - p * fw if horizontal else cy - fh / 2 + p * fh
    if plan.after_image is not None:
        alpha = plan.after_image.pixel_array[:, :, 3]
        if horizontal:
            cut = int(round((1 - p) * alpha.shape[1]))
            alpha[:, :cut] = 0
            alpha[:, cut:] = plan.after_image.reveal_alpha[:, cut:]
        else:
            cut = int(round((1 - p) * alpha.shape[0]))
            alpha[:cut, :] = 0
            alpha[cut:, :] = plan.after_image.reveal_alpha[cut:, :]
    elif plan.after_panel is not None:
        if horizontal:
            plan.after_panel.stretch_to_fit_width(max(fw * p, 1e-3))
            plan.after_panel.move_to([cx + (1 - p) * fw / 2, cy, 0])
        else:
            plan.after_panel.stretch_to_fit_height(max(fh * p, 1e-3))
            plan.after_panel.move_to([cx, cy - (1 - p) * fh / 2, 0])
        plan.after_panel.set_fill(opacity=1 if p > 0 else 0)

    # Empty panels have no picture to anchor to: centre their words in the
    # visible panel, continuously, including the full Before/After endpoints.
    after_word = getattr(plan.after_group, "word", None)
    for word, after in ((plan.before_word, False), (after_word, True)):
        if word is None:
            continue
        fraction = p if after else 1 - p
        if horizontal:
            x = cx + (1 - p) * fw / 2 if after else cx - p * fw / 2
            x = float(np.clip(x, cx - fw / 2 + word.width / 2, cx + fw / 2 - word.width / 2))
            word.move_to([x, cy, 0])
            fits = fraction * fw >= word.width + 0.16
        else:
            y = cy - (1 - p) * fh / 2 if after else cy + p * fh / 2
            y = float(np.clip(y, cy - fh / 2 + word.height / 2, cy + fh / 2 - word.height / 2))
            word.move_to([cx, y, 0])
            fits = fraction * fh >= word.height + 0.16
        word.set_opacity(1 if fits else 0)

    # Photo pills never move with the divider; fade only as their own corner is
    # covered/uncovered. A solid pill remains legible against any photograph.
    for label, after in ((plan.before_label, False), (plan.after_label, True)):
        if label is not None:
            label.set_opacity(_label_opacity(plan, label, p, after=after))
    if horizontal:
        start, end = [edge, cy - fh / 2, 0], [edge, cy + fh / 2, 0]
        plan.handle.move_to([edge, cy, 0])
    else:
        start, end = [cx - fw / 2, edge, 0], [cx + fw / 2, edge, 0]
        plan.handle.move_to([cx, edge, 0])
    plan.line_casing.put_start_and_end_on(start, end)
    plan.line_core.put_start_and_end_on(start, end)


def _label_opacity(plan: Plan, label, value: float, *, after: bool) -> float:
    cx, cy, _ = plan.center
    fw, fh = plan.frame_width, plan.frame_height
    if plan.direction == "horizontal":
        start = (cx + fw / 2 - label.get_right()[0]) / fw
        end = (cx + fw / 2 - label.get_left()[0]) / fw
    else:
        start = (label.get_bottom()[1] - cy + fh / 2) / fh
        end = (label.get_top()[1] - cy + fh / 2) / fh
    return float(np.clip((value - end) / 0.05 if after else (start - value) / 0.05, 0, 1))
