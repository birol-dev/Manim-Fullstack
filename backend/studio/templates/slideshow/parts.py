"""Local text and picture fitting; zooms keep the picture's frame fixed."""
from __future__ import annotations

import re

import numpy as np
from manim import Animation, Circle, ImageMobject, Rectangle, VGroup, linear
from PIL import Image

from studio.kit import fit_text, fonts, media
from studio.kit.text import measure


def text(source, *, width, size=40, height=None, **options):
    """Preserve every character, even in an unusually long unbroken word."""
    options["font"] = fonts.resolve(options["font"])
    for current in range(int(size), 23, -2):
        pieces = []
        for token in re.split(r"(\s+)", source):
            marked = token.startswith("*") and token.endswith("*") and len(token) > 2
            word = token[1:-1] if marked else token
            lines, line = [], ""
            for char in word:
                if line and measure(line + char, size=current, font=options["font"],
                                    weight=options.get("weight", "NORMAL")) > width * .9:
                    lines.append(line)
                    line = ""
                line += char
            lines.append(line)
            pieces.append("\n".join(f"*{part}*" if marked else part for part in lines))
        mob = fit_text("".join(pieces), width=width, size=current, min_size=current,
                       max_lines=max(1, len(source)), line_spacing=1.08, **options)
        if height is None or mob.height <= height + 1e-6:
            return mob
    raise ValueError("Shorten this line so it has room to breathe.")


def cover(path, width, height, max_px=1400):
    """Use kit upload preparation (including EXIF and alpha), then cover the slot."""
    pixels = media.image(path, max_px=max_px).pixel_array
    h, w = pixels.shape[:2]
    ratio = width / height
    if w / h > ratio:
        target = max(1, round(h * ratio))
        pixels = pixels[:, (w - target) // 2:(w - target) // 2 + target]
    else:
        target = max(1, round(w / ratio))
        pixels = pixels[(h - target) // 2:(h - target) // 2 + target, :]
    mob = ImageMobject(pixels.copy())
    mob.stretch_to_fit_width(width).stretch_to_fit_height(height)
    return mob


class GentleZoom(Animation):
    """A 5% zoom inside an unchanged rectangular frame; no pixels spill out."""
    def __init__(self, picture, **kwargs):
        self.source = Image.fromarray(picture.pixel_array.copy())
        super().__init__(picture, rate_func=linear, **kwargs)

    def interpolate_mobject(self, alpha):
        w, h = self.source.size
        inset = .025 * alpha
        box = (round(w * inset), round(h * inset), round(w * (1 - inset)), round(h * (1 - inset)))
        self.mobject.pixel_array = np.array(self.source.crop(box).resize((w, h), Image.Resampling.BILINEAR))


def empty_panel(width, height, theme, accent, index):
    """Soft color and quiet geometry give an empty picture an intentional finish."""
    panel = Rectangle(width=width, height=height).set_stroke(width=0)
    panel.set_fill([theme.bg2, accent], opacity=1).set_sheen_direction(np.array([.4, -1, 0]))
    d = min(width, height)
    rings = VGroup()
    for i in range(3):
        ring = Circle(radius=d * (.18 + i * .09)).set_fill(opacity=0)
        ring.set_stroke(theme.text, width=1.5, opacity=.12)
        ring.shift([width * (.08 if index % 2 else -.08), height * .06, 0])
        rings.add(ring)
    return VGroup(panel, rings), rings
