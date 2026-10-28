"""The template kit (imports Manim). Templates use: ``from studio.kit import *``-style imports.

    from manim import *                      # Manim itself, as usual
    from studio.kit import StudioScene, fit_text, label, Counter, shapes, media
"""

from . import media, shapes
from .counter import Counter
from .layout import Layout, Region
from .motion import Motion, ease_in_out, ease_out, overshoot
from .scene import StudioScene, Theme
from .text import fit_text, label, measure, size_for_height, wrap

__all__ = [
    "Counter",
    "Layout",
    "Motion",
    "Region",
    "StudioScene",
    "Theme",
    "ease_in_out",
    "ease_out",
    "fit_text",
    "label",
    "measure",
    "media",
    "overshoot",
    "shapes",
    "size_for_height",
    "wrap",
]
