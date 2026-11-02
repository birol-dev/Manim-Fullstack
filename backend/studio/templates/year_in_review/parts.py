"""Pieces of the year-in-review template: stat formatting, a counting number with a smaller unit, badges.

Kept local to the template; see the report for what could move into the kit.
"""

from __future__ import annotations

import os

from manim import RIGHT, Circle, ValueTracker, VGroup

from studio.kit import Counter, label, media
from studio.numfmt import format_number

# Letters that sit on the baseline (no descender, no round overshoot to speak of).
_FLAT = set("abdfhiklmnrtvwxzABDEFHIKLMNPRTUVWXYZ%0123456789")


def has_icon(name) -> bool:
    if not name:
        return False
    base = os.path.basename(name)
    return base == name and os.path.isfile(os.path.join(media.ICONS_DIR, base + ".svg"))


def _infer_decimals(value: float) -> int:
    for d in (0, 1, 2):
        if abs(value * 10 ** d - round(value * 10 ** d)) < 1e-6:
            return d
    return 2


class StatSpec:
    """One stat, ready to draw: how its number is written while it counts."""

    def __init__(self, stat, index: int, locale: str):
        self.index = index
        self.value = float(stat.value)
        self.decimals = _infer_decimals(self.value)
        self.prefix = (stat.prefix or "").strip()
        suffix = (stat.suffix or "").strip()
        # One-character suffixes (%, +, ★) stay with the digits; words become a smaller unit.
        self.inline = suffix if len(suffix) <= 1 else ""
        self.unit = "" if self.inline else suffix
        self.compact = bool(stat.compact) and self.value >= 1000
        self.label = stat.label or ""
        self.icon = stat.icon if has_icon(stat.icon) else None
        self.locale = locale

    def _rollover(self, v: float) -> float:
        """With compact numbers, 999,960 must read 1M, not "1,000K"."""
        d = self.decimals
        if v < 1000:
            return 1000.0 if round(v, d) >= 1000 else v
        for p in (9, 6, 3):
            if v >= 10 ** p:
                scaled = v / 10 ** p
                dd = max(d, 1)
                if p < 9 and round(scaled, dd) >= 1000:
                    return float(10 ** (p + 3))
                return v
        return v

    def fmt(self, v: float) -> str:
        v = max(0.0, float(v))
        d = self.decimals
        if self.compact:
            v = self._rollover(v)
            if v >= 1000:
                d = max(d, 1)
        return format_number(v, decimals=d, locale=self.locale, prefix=self.prefix, suffix=self.inline,
                             compact=self.compact)

    def samples(self) -> tuple:
        out = [0.0, self.value]
        for p in (3, 6, 9):
            if self.value >= 10 ** p:
                out.append(1.5 * 10 ** p)
        return tuple(out)

    def drop_affixes(self):
        """Fallback when the font can't render the prefix/suffix as separate glyphs (e.g. emoji)."""
        self.unit = (self.inline + " " + self.unit).strip() if self.inline else self.unit
        self.prefix, self.inline = "", ""


def _counter(spec: StatSpec, value: float, size: float, font: str, weight: str, color: str) -> Counter:
    try:
        return Counter(value, size=size, font=font, weight=weight, color=color, anchor="left",
                       formatter=spec.fmt, sample_values=spec.samples())
    except RuntimeError:
        spec.drop_affixes()
        return Counter(value, size=size, font=font, weight=weight, color=color, anchor="left",
                       formatter=spec.fmt, sample_values=spec.samples())


def _baseline_offset(text_mob, text: str) -> float:
    """Height of the baseline above the bottom of a Text (descenders hang below it)."""
    chars = [c for c in text if not c.isspace()]
    glyphs = list(text_mob.submobjects)
    if len(chars) == len(glyphs):
        bottoms = [g.get_bottom()[1] for c, g in zip(chars, glyphs) if c in _FLAT]
        if bottoms:
            return max(bottoms) - text_mob.get_bottom()[1]
    return 0.0


class StatNumber(VGroup):
    """A counting number with its unit written smaller after it, on the same baseline.

    ``align`` is ``center`` (the whole thing stays centered while the digits grow) or ``left``.
    Position it with ``place(x, baseline)``; count with ``counting(start, end, run_time, rate)``
    and call ``stop()`` when the count is over (lets Manim freeze the frame in holds).
    """

    UNIT_RATIO = 0.42

    def __init__(self, spec: StatSpec, *, size: float, font: str, weight: str, color: str, unit_color: str,
                 unit_weight: str = "BOLD", align: str = "center", start: float | None = None):
        super().__init__()
        self.spec = spec
        self.align = align
        self.size = size
        value = spec.value if start is None else start
        self.counter = _counter(spec, value, size, font, weight, color)
        self.add(self.counter)
        self.unit = None
        if spec.unit:
            unit_size = max(24.0, size * self.UNIT_RATIO)
            self.unit = label(spec.unit, size=unit_size, font=font, weight=unit_weight, color=unit_color)
            self._unit_h0 = max(self.unit.height, 1e-6)
            self._unit_base0 = _baseline_offset(self.unit, spec.unit)
            self.add(self.unit)
        self._gap0 = size / 48 * 0.12
        self._relayout(self.counter.get_left()[0] if align == "left" else self.counter.get_center()[0])

    # geometry ---------------------------------------------------------------
    def _scale(self) -> float:
        try:
            return float(self.counter._state()[1])
        except Exception:  # pragma: no cover - defensive
            return 1.0

    def baseline(self) -> float:
        try:
            return float(self.counter._state()[0][1])
        except Exception:  # pragma: no cover - defensive
            return self.counter.get_bottom()[1]

    def digit_height(self) -> float:
        return self.counter.height

    def _ref_x(self) -> float:
        return self.get_left()[0] if self.align == "left" else self.get_center()[0]

    def _relayout(self, ref_x: float) -> None:
        gap = self._gap0 * self._scale()
        w_num = self.counter.width
        total = w_num + ((gap + self.unit.width) if self.unit is not None else 0.0)
        left = ref_x - total / 2 if self.align == "center" else ref_x
        self.counter.shift(RIGHT * (left - self.counter.get_left()[0]))
        if self.unit is not None:
            k = self.unit.height / self._unit_h0
            ux = self.counter.get_right()[0] + gap
            bottom = self.baseline() - self._unit_base0 * k
            self.unit.shift([ux - self.unit.get_left()[0], bottom - self.unit.get_bottom()[1], 0])

    def place(self, x: float, baseline: float) -> "StatNumber":
        """Put the reference point (center or left edge) at *x* and the digits' baseline at *baseline*."""
        self.shift([x - self._ref_x(), baseline - self.baseline(), 0])
        return self

    def width_at(self, value: float) -> float:
        """Width the number would have at *value* (restores the current value)."""
        current = self.counter.value
        ref = self._ref_x()
        self.counter.set_value(value)
        self._relayout(ref)
        w = self.width
        self.counter.set_value(current)
        self._relayout(ref)
        return w

    # animation --------------------------------------------------------------
    def set_value(self, value: float) -> "StatNumber":
        ref = self._ref_x()
        self.counter.set_value(value)
        self._relayout(ref)
        return self

    def counting(self, start: float, end: float, run_time: float, rate_func):
        tracker = ValueTracker(start)
        self.set_value(start)
        self.add_updater(lambda m: m.set_value(tracker.get_value()))
        return tracker, tracker.animate(run_time=run_time, rate_func=rate_func).set_value(end)

    def stop(self) -> "StatNumber":
        self.clear_updaters()
        self.set_value(self.spec.value)
        return self


def badge(icon_name, diameter: float, *, fill: str, icon_color: str):
    """A filled circle with a line icon in it, or None when there's no (bundled) icon."""
    if not icon_name:
        return None
    size = diameter * 0.5
    ic = media.icon(icon_name, size=size, color=icon_color, stroke_width=max(2.5, min(9.0, size * 7.0)))
    if not ic.submobjects:
        return None
    disc = Circle(radius=diameter / 2).set_fill(fill, 1).set_stroke(width=0)
    ic.move_to(disc.get_center())
    return VGroup(disc, ic)


def number_width_per_size(spec: StatSpec, font: str, weight: str, ref: float = 100.0) -> float:
    """Width of the stat's final number (with its unit) per point of font size."""
    probe = StatNumber(spec, size=ref, font=font, weight=weight, color="#FFFFFF", unit_color="#FFFFFF")
    return probe.width / ref
