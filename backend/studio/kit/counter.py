"""A fast animated number: glyphs are rendered once and copied each frame.

Rebuilding a ``Text`` every frame made a 6 s chart render 2.7x slower in our benchmark,
and Manim's ``DecimalNumber``/``Integer`` need LaTeX. ``Counter`` renders each needed
character once (cached per font, weight, size and color) and composes copies.

Each ``set_value`` reads the counter's current position, scale and opacity from its
geometry, so it can be moved, scaled or faded like any mobject between updates. Start
counting after an entrance animation; don't ``Transform`` a counter that is tracking.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from manim import Text, ValueTracker, VGroup

from . import fonts
from ..numfmt import format_number

DIGITS = "0123456789"


@lru_cache(maxsize=64)
def _glyph_set(chars: str, font: str, weight: str, size: float, color: str) -> dict:
    """char -> (glyph at the origin or None for spaces, bottom offset from the baseline, advance)."""
    source = DIGITS + "".join(sorted(set(chars) - set(DIGITS) - {" ", " "}))
    text = Text(source, font=font, weight=weight, font_size=size, color=color, disable_ligatures=True)
    glyphs = list(text.submobjects)
    if len(glyphs) != len(source):
        raise RuntimeError(f"font {font!r} produced {len(glyphs)} glyphs for {len(source)} characters")
    baseline = glyphs[0].get_bottom()[1]  # "0" sits on the baseline
    digit_advance = max(g.width for g in glyphs[: len(DIGITS)])
    gap = size / 48 * 0.035
    space = Text("n n", font=font, font_size=size).width - Text("nn", font=font, font_size=size).width
    out = {}
    for ch, glyph in zip(source, glyphs):
        offset = glyph.get_bottom()[1] - baseline
        advance = (digit_advance if ch in DIGITS else glyph.width) + gap
        out[ch] = (glyph.copy().move_to(np.zeros(3)), offset, advance)
    out[" "] = (None, 0.0, space)
    out[" "] = (None, 0.0, space * 0.6)
    return out


class Counter(VGroup):
    """``c = Counter(0, size=96, fmt={"suffix": "%"})``; animate with
    ``tracker, anim = c.counting(0, 87)`` then ``scene.play(anim, run_time=2)``.

    ``fmt`` takes ``studio.numfmt.format_number`` keywords (decimals, locale, prefix,
    suffix, compact, sign); ``formatter`` (value -> str) replaces it, e.g. for "04:59".
    Characters the formatter can produce should appear in ``sample_values``' output. ``anchor`` (left / center / right) is the edge that stays put
    while the width changes.
    """

    def __init__(self, value: float = 0, *, size: float = 72, font: str = "Inter", weight: str = "BOLD",
                 color: str = "#FFFFFF", anchor: str = "center", fmt: dict | None = None,
                 formatter=None, sample_values: tuple = ()):
        super().__init__()
        self.fmt = dict(fmt or {})
        self.formatter = formatter
        self.family = fonts.resolve(font)
        self.weight = weight
        self.size = size
        self.color_hex = color
        self.anchor = anchor
        samples = [self.text_for(v) for v in (value, *sample_values)]
        if formatter is None:
            samples += [format_number(v, **self.fmt) for v in (-1, 1234567.891)]
        self._chars = "".join(sorted(set("".join(samples))))
        self._glyphs = _glyph_set(self._chars, self.family, weight, size, color)
        self._shown = ""
        self.value = value
        self._compose(value, np.zeros(3), 1.0, None)

    def text_for(self, value: float) -> str:
        if self.formatter is not None:
            return self.formatter(value)
        return format_number(value, **self.fmt)

    def _ensure_glyphs(self, text: str) -> None:
        missing = set(text) - set(self._glyphs)
        if missing:
            self._chars = "".join(sorted(set(self._chars) | missing))
            self._glyphs = _glyph_set(self._chars, self.family, self.weight, self.size, self.color_hex)

    def _compose(self, value: float, anchor_point: np.ndarray, scale: float, opacity) -> None:
        text = self.text_for(value)
        self._ensure_glyphs(text)
        parts, shown, x = [], [], 0.0
        for ch in text:
            glyph, offset, advance = self._glyphs[ch]
            if glyph is not None:
                g = glyph.copy()
                g.move_to([x + (advance - self._gap()) / 2, offset + g.height / 2, 0])
                parts.append(g)
                shown.append(ch)
            x += advance
        width = max(x - self._gap(), 0.0)
        edge = {"left": 0.0, "right": width}.get(self.anchor, width / 2)
        delta = anchor_point - np.array([edge, 0.0, 0.0])
        for p in parts:
            p.shift(delta)
            if scale != 1.0:
                p.scale(scale, about_point=anchor_point)
            if opacity is not None:
                p.set_opacity(opacity)
        self.submobjects = parts
        self._shown = "".join(shown)
        self.value = value

    def _gap(self) -> float:
        return self.size / 48 * 0.035

    def _state(self) -> tuple:
        """(anchor point, scale, opacity) read from the current glyphs."""
        ref_index = next((i for i, ch in enumerate(self._shown) if ch in DIGITS), 0)
        ref = self.submobjects[ref_index]
        ch = self._shown[ref_index]
        natural, offset, _ = self._glyphs[ch]
        scale = ref.height / natural.height if natural.height else 1.0
        baseline = ref.get_bottom()[1] - offset * scale
        if self.anchor == "left":
            x = self.get_left()[0]
        elif self.anchor == "right":
            x = self.get_right()[0]
        else:
            x = self.get_center()[0]
        return np.array([x, baseline, 0.0]), scale, ref.get_fill_opacity()

    def set_value(self, value: float) -> "Counter":
        if self.submobjects:
            point, scale, opacity = self._state()
        else:
            point, scale, opacity = np.zeros(3), 1.0, None
        self._compose(value, point, scale, opacity)
        return self

    def track(self, tracker: ValueTracker) -> "Counter":
        """Follow *tracker* every frame."""
        self.add_updater(lambda m: m.set_value(tracker.get_value()))
        return self

    def counting(self, start: float, end: float):
        """``tracker, animation = counter.counting(0, 500)``: play the animation to count."""
        tracker = ValueTracker(start)
        self.set_value(start)
        self.track(tracker)
        return tracker, tracker.animate.set_value(end)
