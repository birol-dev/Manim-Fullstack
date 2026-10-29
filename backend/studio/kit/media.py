"""Uploaded images (with circle / rounded crops done in Pillow) and bundled icons."""

from __future__ import annotations

import os
from functools import lru_cache

import numpy as np
from manim import ImageMobject, SVGMobject, VGroup

ICONS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "icons")
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")


def resolve_asset(assets_dir: str | None, name: str | None) -> str | None:
    """Path of uploaded asset *name* inside *assets_dir*, or None (base names only)."""
    if not name or not assets_dir:
        return None
    base = os.path.basename(str(name))
    if base != name or base.startswith("."):
        return None
    root = os.path.realpath(assets_dir)
    path = os.path.realpath(os.path.join(root, base))
    try:
        if os.path.commonpath([root, path]) != root:
            return None
    except ValueError:
        return None
    return path if os.path.isfile(path) else None


@lru_cache(maxsize=64)
def _prepared(path: str, mtime: float, shape: str, max_px: int):
    from PIL import Image, ImageDraw, ImageOps

    img = Image.open(path)
    img = ImageOps.exif_transpose(img).convert("RGBA")
    if max(img.size) > max_px:
        img.thumbnail((max_px, max_px), Image.LANCZOS)
    if shape in ("circle", "square", "rounded"):
        side = min(img.size)
        left = (img.width - side) // 2
        top = (img.height - side) // 2
        img = img.crop((left, top, left + side, top + side))
    if shape in ("circle", "rounded"):
        mask = Image.new("L", img.size, 0)
        draw = ImageDraw.Draw(mask)
        if shape == "circle":
            draw.ellipse((0, 0, img.width - 1, img.height - 1), fill=255)
        else:
            r = img.width // 8
            draw.rounded_rectangle((0, 0, img.width - 1, img.height - 1), radius=r, fill=255)
        img.putalpha(Image.composite(img.getchannel("A"), mask, mask))
    return np.array(img)


def image(path: str, *, height: float | None = None, width: float | None = None, shape: str = "any",
          max_px: int = 1600):
    """An ImageMobject from *path*; ``shape``: any, square, circle, rounded.

    An SVG (the upload field accepts them) comes back as vectors, uncropped: inside a circle
    it is shrunk to fit within it instead.
    """
    vector = path.lower().endswith(".svg")
    if vector:
        mob = SVGMobject(path)
    else:
        mob = ImageMobject(_prepared(path, os.path.getmtime(path), shape, max_px))
    if height is not None and width is not None:
        mob.scale(min(height / mob.height, width / mob.width))
    elif height is not None:
        mob.scale_to_fit_height(height)
    elif width is not None:
        mob.scale_to_fit_width(width)
    if vector and shape == "circle":
        mob.scale(0.7)  # a square's corners touch a circle at 1/sqrt(2)
    return mob


def svg_logo(path: str, *, height: float, color: str | None = None):
    """An SVG logo as vectors (can be drawn on with ``Write``/``DrawBorderThenFill``)."""
    mob = SVGMobject(path)
    if color:
        mob.set_color(color)
    return mob.scale_to_fit_height(height)


def icon_names() -> list:
    if not os.path.isdir(ICONS_DIR):
        return []
    return sorted(n[:-4] for n in os.listdir(ICONS_DIR) if n.endswith(".svg"))


def icon(name: str | None, *, size: float, color: str, stroke_width: float = 3.0):
    """A bundled line icon (stroked, no fill). Missing icons give an empty group."""
    if not name:
        return VGroup()
    base = os.path.basename(name)
    path = os.path.join(ICONS_DIR, base + ".svg")
    if base != name or not os.path.isfile(path):
        return VGroup()
    mob = SVGMobject(path, stroke_color=color, stroke_width=stroke_width, fill_opacity=0)
    mob.set_fill(opacity=0).set_stroke(color, width=stroke_width)
    return mob.scale_to_fit_height(size)
