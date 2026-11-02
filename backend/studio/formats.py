"""Output formats: pixel sizes per aspect and quality, and Manim frame sizes. No Manim import.

Manim keeps a 14.2 x 8 frame whatever the pixel size, so a 9:16 render letterboxes a
16:9 layout into the middle third. Every studio render sets the frame itself: the short
side is always 8 units, so text sizes mean the same thing in every aspect.
"""

from __future__ import annotations

SHORT_SIDE_UNITS = 8.0

# (width, height) in aspect units
ASPECT_RATIOS = {"16:9": (16, 9), "9:16": (9, 16), "1:1": (1, 1), "4:5": (4, 5)}

# Pixels on the short side, and frames per second.
QUALITIES = {
    "preview": {"short": 360, "fps": 15},
    "draft": {"short": 480, "fps": 15},
    "720p": {"short": 720, "fps": 30},
    "1080p": {"short": 1080, "fps": 30},
    "1080p60": {"short": 1080, "fps": 60},
    "4k": {"short": 2160, "fps": 30},
}


def pixel_size(aspect: str, short: int) -> tuple:
    """Even pixel dimensions (encoders need even sizes) for *aspect* with *short* pixels on the short side."""
    w, h = ASPECT_RATIOS[aspect]
    if w >= h:
        height, width = short, short * w / h
    else:
        width, height = short, short * h / w
    return int(round(width / 2) * 2), int(round(height / 2) * 2)


def frame_size(pixel_width: int, pixel_height: int) -> tuple:
    """Manim frame (width, height) in units for these pixels, short side = 8 units."""
    if pixel_width >= pixel_height:
        return SHORT_SIDE_UNITS * pixel_width / pixel_height, SHORT_SIDE_UNITS
    return SHORT_SIDE_UNITS, SHORT_SIDE_UNITS * pixel_height / pixel_width
