"""Pieces of the steps template: palette, the header, and the three row styles.

Imported by ``scene.py`` (it uses Manim). Rows are built in a local frame with their left
edge at x=0 and their slot's top at y=0, so the scene can stack them and tests can probe
their geometry.
"""

from __future__ import annotations

from functools import lru_cache
import re

import numpy as np
from manim import DOWN, LEFT, RIGHT, UP, AnimationGroup, Circle, Create, LaggedStart, Line, Rectangle, Transform, VGroup

from studio.kit import fit_text, label, media, shapes
from studio.kit import fonts
from studio.kit.text import measure


# -- color -------------------------------------------------------------------
def _rgb(value: str) -> tuple:
    h = value.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _channel(c: float) -> float:
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(value: str) -> float:
    r, g, b = (_channel(c) for c in _rgb(value))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def best_on(background: str, *candidates: str) -> str:
    return max(candidates, key=lambda c: contrast(background, c))


class Palette:
    """Theme tokens plus the contrast-safe accent pairs the template needs."""

    def __init__(self, theme, accent: str | None = None, background: str | None = None):
        self.theme = theme
        self.font = theme.font
        self.display_weight = theme.display_weight
        self.bg = background or theme.bg
        self.surface = theme.surface
        self.text = theme.text
        self.muted = theme.muted
        self.line = theme.line
        self.dark = theme.dark
        self.accent = accent or theme.accent(0)
        on = theme.on_accent
        if contrast(self.accent, on) < 3.0:
            on = best_on(self.accent, "#FFFFFF", "#111111", theme.text, theme.bg)
        self.on_accent = on
        self.accent_text = self.accent if contrast(self.accent, self.bg) >= 2.2 else theme.text
        self.tint = 0.18 if theme.dark else 0.12


# -- text --------------------------------------------------------------------
def _lines(mob) -> list:
    return list(getattr(mob, "lines", None) or [mob])


def is_cut(mob, source: str) -> bool:
    """True when fit_text had to cut *source* with an ellipsis."""
    shown = "".join(getattr(line, "original_text", "") for line in _lines(mob))
    return shown.count("…") > (source or "").count("…")


@lru_cache(maxsize=512)
def _fit_source(source: str, **kwargs):
    return fit_text(source, **kwargs)


def _break_long_words(source, width, size, font, weight):
    """The kit wraps words only. Split an unusually long token at glyph boundaries.

    This local fallback keeps labels/URLs at their real type size; ordinary words
    still use the kit's balanced wrapping and emphasis handling.
    """
    family = fonts.resolve(font)
    out = []
    for word in re.split(r"(\s+)", source):
        plain = word.replace("*", "")
        if not plain or measure(plain, size=size, font=family, weight=weight) <= width:
            out.append(word)
            continue
        chunks, current = [], ""
        for char in plain:
            if current and measure(current + char, size=size, font=family, weight=weight) > width:
                chunks.append(current)
                current = ""
            current += char
        chunks.append(current)
        if word.startswith("*") and word.endswith("*"):
            chunks = [f"*{chunk}*" for chunk in chunks]
        out.append("\n".join(chunks))
    return "".join(out)


def full_text(source: str, **kwargs):
    """fit_text that never loses words and never slips below the size floor.

    Measure every line at the requested size, leaving a small width reserve for
    Pango. Split overlong tokens locally instead of shrinking a finished group.
    """
    # Keep all lines, including when a proposed size does not fit the scene. The
    # scene measures the result and tries a smaller TYPE size, never group.scale().
    # The small width reserve absorbs Pango/word-measurement differences.
    for reserve in (0.97, 0.92, 0.84, 0.72):
        options = {**kwargs, "width": kwargs["width"] * reserve, "height": None,
                   "size": kwargs["size"], "min_size": kwargs["size"],
                   "max_lines": max(len(source), 1)}
        wrapped = _break_long_words(source, options["width"], options["size"],
                                    options.get("font", "Inter"), options.get("weight", "NORMAL"))
        mob = _fit_source(wrapped, **options).copy()
        actual = min(line.font_size for line in mob.lines)
        restore = options["size"] / actual
        if mob.width * restore <= kwargs["width"] + 1e-6:
            # fit_text can silently scale its Text children to its estimated
            # width. Restore their REAL size within our reserved width, then
            # let the scene measure the resulting height before choosing it.
            mob.scale(restore)
            mob.font_size = options["size"]
            return mob
    raise ValueError("This text cannot wrap at its requested readable size.")


class Header(VGroup):
    def __init__(self):
        super().__init__()
        self.kick = None
        self.bar = None
        self.words = None
        self.title = None
        self.cut = False


def header(kicker_text: str, title_text: str, pal: Palette, *, width: float, title_size: float,
           title_lines: int, kicker_size: float = 24) -> Header:
    """The top line (an accent bar + small caps) above the title, both left-aligned at x=0, top at y=0."""
    head = Header()
    y = 0.0
    if kicker_text:
        bar_w, gap = 0.34, 0.16
        words = full_text(kicker_text.upper(), width=max(width - bar_w - gap, 1.0), size=kicker_size,
                          min_size=24, max_lines=1, font=pal.font, weight="BOLD", color=pal.accent_text,
                          align="left", line_spacing=1.0)
        bar = Rectangle(width=bar_w, height=0.045).set_fill(pal.accent, 1).set_stroke(width=0)
        bar.next_to(words.lines[0], LEFT, buff=gap)
        bar.set_y(words.get_center()[1])
        kick = VGroup(bar, words)
        kick.align_to([0, 0, 0], LEFT).align_to([0, 0, 0], UP)
        head.add(kick)
        head.kick, head.bar, head.words = kick, bar, words
        head.cut = is_cut(words, kicker_text.upper())
        y = -kick.height - 0.18

    if not title_text.strip():
        return head
    title = full_text(pal.theme.display(title_text), width=width, size=title_size, min_size=24,
                      max_lines=title_lines, font=pal.font, weight=pal.display_weight, color=pal.text,
                      emphasis_color=pal.accent_text, align="left", line_spacing=1.05)
    title.align_to([0, 0, 0], LEFT).align_to([0, 0, 0], UP).shift(DOWN * -y)
    head.title = title
    head.cut = head.cut or is_cut(title, pal.theme.display(title_text))
    head.add(title)
    return head


# -- rows --------------------------------------------------------------------
class StepRow(VGroup):
    """One item: marker, text, optional detail/time/icon, and the optional 'now' card."""

    def __init__(self):
        super().__init__()
        self.card = self.marker = self.text = self.detail = self.time = self.icon = None
        self.box = self.filled = self.tick = None
        self.tick_anim = None
        self.segment = None
        self.cut = False
        self.dot_center = None


@lru_cache(maxsize=1024)
def _actual_width(source, size, font):
    return label(source, size=size, font=font, weight="NORMAL").width


def compact_text(step, pal, width, first_width, size):
    """A short first line leaves a time slot; continuation lines use the full measure.

    Keep step/detail colours while flowing the detail into the spare line. Each
    actual line still goes through fit_text; this is a local kit extension.
    """
    words = [(word, True) for word in step.text.split()]
    if step.detail:
        words += [("·", False)] + [(word, False) for word in step.detail.split()]
    lines, current = [], []
    for word in words:
        limit = first_width if not lines else width
        proposed = " ".join(w for w, _ in [*current, word])
        if current and _actual_width(proposed, size, pal.font) > limit:
            lines.append(current)
            current = []
        current.append(word)
    if current:
        lines.append(current)
    mob = VGroup()
    for i, line in enumerate(lines):
        source = " ".join(f"*{w}*" if primary else w for w, primary in line)
        # Already wrapped against real Pango widths. Give the kit room for its
        # estimate so it does not rewrap an accurately measured physical line.
        mob.add(full_text(source, width=(first_width if i == 0 else width) * 1.3, size=size,
                          font=pal.font, weight="NORMAL", color=pal.muted,
                          emphasis_color=pal.text, align="left"))
    mob.arrange(DOWN, aligned_edge=LEFT, buff=0.05)
    mob.lines = [line for block in mob for line in block.lines]
    mob.font_size = size
    return mob


@lru_cache(maxsize=128)
def _icon_source(name, size, color):
    return media.icon(name, size=size, color=color, stroke_width=3.0)


def _icon(name, *, size: float, color: str):
    if not name:
        return None
    mob = _icon_source(name, size, color).copy()
    return mob if len(getattr(mob, "submobjects", [])) else None


def build_row(style: str, step, index: int, pal: Palette, *, width: float, time_width: float,
              highlighted: bool, text_size: float, detail_size: float, text_lines: int,
              detail_lines: int, stacked_time: bool = False, show_icon: bool = True,
              compact_detail: bool = False) -> StepRow:
    row = StepRow()
    marker_size = {"numbered": 0.42, "checklist": 0.42, "timeline": 0.22}[style]
    gap, icon_size, time_size, right_gap = 0.2, 0.4, 24, 0.16

    icon = _icon(step.icon, size=icon_size, color=pal.accent_text) if show_icon else None
    icon_w = icon_size if icon is not None else 0.0
    time_w = time_width if style == "timeline" else (
        label(step.time, size=time_size, font=pal.font, weight="SEMIBOLD").width if step.time else 0.0)

    if style == "timeline":
        gutter = 0.54 if stacked_time else time_width + 0.58
        right = (icon_w + 0.12) if icon is not None else 0.0
    else:
        gutter = marker_size + gap
        if stacked_time:
            right = 0.0
        elif step.detail:
            right = (max(icon_w, time_w) + right_gap) if (icon is not None or time_w) else 0.0
        else:
            right = (icon_w + (0.12 + time_w if time_w else 0.0) + right_gap) \
                if (icon is not None or time_w) else 0.0
    # Keep the rail and marker outside the highlight, with padding for all text.
    # Stacked/compact timestamps sit inside the band with their own clear slot.
    if compact_detail:
        gutter, right = 0.44, 0
    text_left = gutter + (0.06 if compact_detail else 0.10)
    text_w = max(width - text_left - right - (0.06 if compact_detail else 0.10), 1.0)
    stamp = (label(step.time, size=time_size, font=pal.font, weight="SEMIBOLD",
                   color=pal.accent_text if highlighted else pal.muted) if step.time else None)
    text_top = -(stamp.height + 0.14) if stacked_time and stamp is not None else 0.0

    row.compact_detail = compact_detail
    if row.compact_detail:
        text = compact_text(step, pal, text_w, text_w - (stamp.width + 0.06 if stamp is not None else 0),
                            text_size)
    else:
        text = full_text(step.text, width=text_w, size=text_size, min_size=24, max_lines=text_lines,
                         font=pal.font, weight="SEMIBOLD", color=pal.text, align="left", line_spacing=1.02)
    text.align_to([text_left, text_top, 0], LEFT).align_to([0, text_top, 0], UP)
    row.text = text
    row.cut = is_cut(text, step.text)

    detail = None
    if step.detail and not row.compact_detail:
        detail = full_text(step.detail, width=text_w, size=detail_size, min_size=24, max_lines=detail_lines,
                           font=pal.font, weight="NORMAL", color=pal.muted, align="left", line_spacing=1.06)
        detail.align_to([text_left, 0, 0], LEFT).align_to([0, text_top - text.height - 0.06, 0], UP)
        row.detail = detail
        row.cut = row.cut or is_cut(detail, step.detail)

    block_h = -text_top + text.height + ((0.06 + detail.height) if detail is not None else 0.0)
    block_center = -block_h / 2
    first_center = text.lines[0].get_center()[1]

    if highlighted:
        left = gutter
        card = shapes.card(width - left, block_h + 0.12, color=pal.accent, opacity=pal.tint,
                           radius=min(pal.theme.radius, 0.12), stroke=pal.accent,
                           stroke_width=0.9)
        card.set_stroke(opacity=0.45)
        card.move_to([left + (width - left) / 2, block_center, 0])
        row.card = card
        row.add(card)

    if style == "numbered":
        disc = Circle(radius=marker_size / 2).set_fill(pal.accent, 1).set_stroke(width=0)
        num = label(str(index + 1), size=24, font=pal.font, weight="BOLD", color=pal.on_accent)
        num.move_to(disc.get_center())
        marker = VGroup(disc, num)
        marker.move_to([marker_size / 2, first_center, 0])
        row.marker = marker
    elif style == "checklist":
        radius = min(marker_size * 0.24, 0.12)
        box = shapes.card(marker_size, marker_size, color=pal.surface, radius=radius,
                          stroke=pal.accent if highlighted else pal.muted, stroke_width=2.2)
        box.move_to([marker_size / 2, first_center, 0])
        filled = shapes.card(marker_size, marker_size, color=pal.accent, radius=radius)
        filled.move_to(box.get_center())
        c = box.get_center()
        tick = VGroup(Line(c + np.array([-0.10, 0.01, 0]), c + np.array([-0.03, -0.07, 0])),
                      Line(c + np.array([-0.03, -0.07, 0]), c + np.array([0.11, 0.08, 0])))
        tick.set_stroke(pal.on_accent, width=3.2)
        row.box, row.filled, row.tick = box, filled, tick
        row.tick_anim = AnimationGroup(Transform(box, filled),
                                       LaggedStart(Create(tick[0]), Create(tick[1]), lag_ratio=0.25))
        row.marker = box
    else:
        x = 0.20 if stacked_time or compact_detail else time_width + 0.25
        outer = Circle(radius=marker_size * 0.9).set_fill(pal.bg, 1).set_stroke(width=0)
        dot = Circle(radius=marker_size * (0.55 if highlighted else 0.45)).set_fill(pal.accent, 1)
        parts = [outer, dot]
        if highlighted:
            ring = Circle(radius=marker_size * 0.8).set_stroke(pal.accent, width=2.6)
            parts.append(ring)
        marker = VGroup(*parts)
        marker.move_to([x, -stamp.height / 2 if stacked_time and stamp is not None else first_center, 0])
        row.marker = marker
        row.dot_center = marker.get_center().copy()
        if stamp is not None and not stacked_time and not compact_detail:
            stamp.align_to([time_width, 0, 0], RIGHT).set_y(first_center)
            row.time = stamp

    if icon is not None:
        icon.move_to([width - icon_size / 2, first_center, 0])
        row.icon = icon

    if compact_detail and stamp is not None:
        stamp.set_y(first_center).set_x(width - 0.06 - stamp.width / 2)
        row.time = stamp
    elif stacked_time and stamp is not None:
        stamp.align_to([text_left, 0, 0], LEFT).align_to([0, 0, 0], UP)
        row.time = stamp
    elif style != "timeline" and stamp is not None:
        if detail is not None:
            stamp.set_y(detail.get_center()[1])
        else:
            stamp.set_y(first_center)
        stamp.set_x(width - stamp.width / 2 - (icon_size + 0.14 if icon is not None and detail is None else 0))
        row.time = stamp

    for mob in (row.marker, row.text, row.detail, row.icon, row.time):
        if mob is not None:
            row.add(mob)
    return row
