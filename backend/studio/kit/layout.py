"""Layout in the safe area, in relative coordinates, so one template fits every aspect."""

from __future__ import annotations

import numpy as np


class Layout:
    """The frame and its safe area.

    ``point(x, y)`` takes fractions of the safe area: (0, 0) is its top-left corner,
    (1, 1) the bottom-right. ``unit`` is 1% of the short side (0.08 frame units).
    """

    def __init__(self, frame_width: float, frame_height: float, safe_zone: bool = False):
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.short = min(frame_width, frame_height)
        self.unit = self.short / 100
        margin = 6 * self.unit
        self.left = -frame_width / 2 + margin
        self.right = frame_width / 2 - margin
        self.top = frame_height / 2 - margin
        self.bottom = -frame_height / 2 + margin
        if safe_zone and self.is_portrait:
            # TikTok / Reels / Shorts overlay their buttons and caption here (roughly).
            self.bottom += 0.16 * frame_height
            self.right -= 0.10 * frame_width
            self.top -= 0.05 * frame_height

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.top - self.bottom

    @property
    def center(self) -> np.ndarray:
        return np.array([(self.left + self.right) / 2, (self.top + self.bottom) / 2, 0.0])

    @property
    def aspect(self) -> float:
        return self.frame_width / self.frame_height

    @property
    def is_portrait(self) -> bool:
        return self.frame_height > self.frame_width * 1.05

    @property
    def is_landscape(self) -> bool:
        return self.frame_width > self.frame_height * 1.05

    @property
    def is_square(self) -> bool:
        return not self.is_portrait and not self.is_landscape

    def point(self, x: float, y: float) -> np.ndarray:
        return np.array([self.left + x * self.width, self.top - y * self.height, 0.0])

    def region(self, x0: float, y0: float, x1: float, y1: float) -> "Region":
        """A sub-rectangle of the safe area, in the same fractions."""
        a, b = self.point(x0, y0), self.point(x1, y1)
        return Region(a[0], b[0], a[1], b[1])

    @property
    def safe(self) -> "Region":
        return Region(self.left, self.right, self.top, self.bottom)


class Region:
    def __init__(self, left: float, right: float, top: float, bottom: float):
        self.left, self.right, self.top, self.bottom = left, right, top, bottom

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.top - self.bottom

    @property
    def center(self) -> np.ndarray:
        return np.array([(self.left + self.right) / 2, (self.top + self.bottom) / 2, 0.0])

    def point(self, x: float, y: float) -> np.ndarray:
        return np.array([self.left + x * self.width, self.top - y * self.height, 0.0])

    def split_rows(self, weights, gap: float = 0.0) -> list:
        """Stack of regions top to bottom with heights proportional to *weights*."""
        total = sum(weights)
        usable = self.height - gap * (len(weights) - 1)
        out, top = [], self.top
        for w in weights:
            h = usable * w / total
            out.append(Region(self.left, self.right, top, top - h))
            top -= h + gap
        return out

    def split_cols(self, weights, gap: float = 0.0) -> list:
        total = sum(weights)
        usable = self.width - gap * (len(weights) - 1)
        out, left = [], self.left
        for w in weights:
            wd = usable * w / total
            out.append(Region(left, left + wd, self.top, self.bottom))
            left += wd + gap
        return out

    def fit(self, mobject, *, scale_up: bool = False, align: str = "center"):
        """Scale *mobject* to fit inside, then place it (center / top / bottom / left / right)."""
        if mobject.width > 0 and mobject.height > 0:
            factor = min(self.width / mobject.width, self.height / mobject.height)
            if factor < 1 or scale_up:
                mobject.scale(factor)
        target = self.center.copy()
        if align == "top":
            target[1] = self.top - mobject.height / 2
        elif align == "bottom":
            target[1] = self.bottom + mobject.height / 2
        elif align == "left":
            target[0] = self.left + mobject.width / 2
        elif align == "right":
            target[0] = self.right - mobject.width / 2
        mobject.move_to(target)
        return mobject
