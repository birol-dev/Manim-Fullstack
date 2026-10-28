"""Building blocks and motion pieces for the announcement template.

Imported by ``scene.py`` only (it uses Manim). Everything is built centered at the
origin and placed by the layouts in ``scene.py``.
"""

from __future__ import annotations

import math
import os
from functools import lru_cache

import numpy as np
from manim import (
    DOWN,
    LEFT,
    RIGHT,
    UP,
    AnimationGroup,
    Circle,
    DashedLine,
    Difference,
    FadeIn,
    ImageMobject,
    LaggedStart,
    Rectangle,
    UpdateFromAlphaFunc,
    VGroup,
    VMobject,
    rate_functions,
)

from studio.kit import fit_text as _fit_text, label, media, shapes, size_for_height

QUART = rate_functions.ease_out_quart
BACK = rate_functions.ease_out_back


def fit_text(text, **kwargs):
    """Keep the complete message when the kit's conservative height estimate clips it.

    The scene measures the resulting ink and gives space back from decoration.
    """
    mob = _fit_text(text, **kwargs)
    if is_cut(mob, text):
        retry = {**kwargs, "height": None, "size": kwargs.get("min_size", 24),
                 "max_lines": max(kwargs.get("max_lines", 3), len(text.split()))}
        mob = _fit_text(text, **retry)
    return shrink_to(mob, kwargs["width"])


# -- color -------------------------------------------------------------------
def _rgb(value: str) -> tuple:
    h = value.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def luminance(value: str) -> float:
    def channel(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in _rgb(value))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def best_on(background: str, *candidates: str) -> str:
    return max(candidates, key=lambda c: contrast(background, c))


class Palette:
    """Theme tokens plus the accent pairs this template needs, chosen for contrast."""

    def __init__(self, theme, accent: str | None = None, background: str | None = None):
        self.theme = theme
        self.font = theme.font
        self.display_weight = theme.display_weight
        self.bg = background or theme.bg
        self.bg2 = theme.bg2
        self.surface = theme.surface
        self.text = theme.text
        self.muted = theme.muted
        self.line = theme.line
        self.radius = theme.radius
        self.accent = accent or theme.accent(0)
        on = theme.on_accent
        if contrast(self.accent, on) < 3.0:
            on = best_on(self.accent, "#FFFFFF", "#111111", theme.text, theme.bg)
        self.on_accent = on
        # Accent used as text on the background (headline emphasis, big text on the stub).
        self.accent_text = self.accent if contrast(self.accent, self.bg) >= 2.2 else theme.text
        self.accent_on_surface = self.accent if contrast(self.accent, self.surface) >= 2.2 else theme.text
        # "Ink" buttons: the text color as a fill, the background color as its label.
        self.ink = theme.text
        self.on_ink = self.bg if contrast(theme.text, self.bg) >= 3 else best_on(theme.text, "#FFFFFF", "#111111")
        self.second = theme.accent(1)


# -- geometry helpers ---------------------------------------------------------
@lru_cache(maxsize=64)
def _cap_per_size(font: str, weight: str) -> float:
    return 1.0 / size_for_height(1.0, font=font, weight=weight)


def cap_height(size: float, font: str, weight: str = "BOLD") -> float:
    """Height of a capital / digit at *size* (units)."""
    return size * _cap_per_size(font, weight)


def shrink_to(mob, width: float, height: float | None = None):
    """Scale *mob* down (never up) so it fits width x height."""
    if mob.width <= 0:
        return mob
    k = width / mob.width
    if height is not None and mob.height > 0:
        k = min(k, height / mob.height)
    if k < 1:
        mob.scale(k)
    return mob


def merge(mobs, color: str, opacity: float = 1.0) -> VMobject:
    """Many filled shapes as one path (one Cairo fill instead of hundreds)."""
    points = [m.points for m in mobs if len(m.points)]
    out = VMobject()
    if points:
        out.set_points(np.concatenate(points))
    out.set_fill(color, opacity=opacity).set_stroke(width=0)
    return out


def glyph_groups(line, by: str = "word") -> list:
    """The glyphs of a fit_text/label ``Text`` line grouped by word (or char)."""
    source = getattr(line, "original_text", None)
    glyphs = list(line.submobjects)
    if not source or by == "line":
        return [line]
    if by == "char":
        return glyphs
    words = source.split()
    if sum(len(w) for w in words) != len(glyphs):
        return [line]
    out, i = [], 0
    for w in words:
        out.append(VGroup(*glyphs[i:i + len(w)]))
        i += len(w)
    return out


def text_lines(mob) -> list:
    return list(getattr(mob, "lines", None) or [mob])


def is_cut(mob, source: str) -> bool:
    """True when fit_text had to cut *source* with an ellipsis (it didn't fit)."""
    shown = "".join(getattr(line, "original_text", "") for line in text_lines(mob))
    return shown.count("…") > (source or "").count("…")


# -- blocks -------------------------------------------------------------------
def headline(text: str, pal: Palette, *, width: float, height: float, size: float, min_size: float = 34,
             max_lines: int = 3, align: str = "center", color: str | None = None, emphasis: str | None = None):
    mob = fit_text(pal.theme.display(text), width=width, height=height, size=size, min_size=min_size,
                   max_lines=max_lines, font=pal.font, weight=pal.display_weight, color=color or pal.text,
                   emphasis_color=emphasis or pal.accent_text, align=align, line_spacing=1.0)
    return shrink_to(mob, width)


def big_type(text: str, pal: Palette, *, width: float, height: float, color: str, max_cap: float | None = None,
             allow_two: bool = True, align: str = "center", weight: str = "HEAVY"):
    """Huge display text scaled to fill width x height: one line, or two when that is much bigger."""
    words = text.upper().split()
    options = [[" ".join(words)]]
    if allow_two and len(words) >= 2:
        best, best_w = None, None
        for cut in range(1, len(words)):
            a, b = " ".join(words[:cut]), " ".join(words[cut:])
            w = max(len(a), len(b))
            if best_w is None or w < best_w:
                best, best_w = [a, b], w
        options.append(best)
    ref = 120
    cap = cap_height(ref, pal.font, weight)
    chosen, chosen_k = None, -1.0
    for lines in options:
        group = VGroup(*[label(t, size=ref, font=pal.font, weight=weight, color=color) for t in lines])
        lead = cap * 1.28
        for i, line in enumerate(group):
            line.move_to([0, -i * lead, 0])
            if align == "left":
                line.align_to([0, 0, 0], LEFT)
        box_h = cap + lead * (len(lines) - 1)
        k = min(width / max(group.width, 1e-6), height / box_h)
        if max_cap is not None:
            k = min(k, max_cap / cap)
        bonus = 1.0 if len(lines) == 1 else 1.3  # two lines only when clearly bigger
        if k > chosen_k * bonus:
            chosen, chosen_k = group, k
    chosen.scale(chosen_k)
    chosen.move_to([0, 0, 0])
    chosen.lines = list(chosen)
    chosen.cap = cap * chosen_k
    return chosen


def kicker(text: str, pal: Palette, *, max_width: float, size: float = 28, style: str = "pill"):
    """The small top line: in a pill (``pill``), or after an accent bar (``bar``)."""
    upper = text.upper()
    cap = cap_height(size, pal.font, "BOLD")
    if style == "pill":
        pad_x = cap * 1.35
        words = fit_text(upper, width=max_width - 2 * pad_x, size=size, min_size=24, max_lines=2, font=pal.font,
                         weight="BOLD", color=pal.on_accent, line_spacing=1.05)
        cap = cap_height(words.font_size, pal.font, "BOLD")
        h = max(cap * 2.7, words.height + cap * 1.6)
        w = words.width + 2 * pad_x
        radius = h / 2 if len(words.lines) == 1 else cap * 0.9
        bg = shapes.card(w, h, color=pal.accent, radius=radius)
        words.move_to(bg.get_center())
        group = VGroup(bg, words)
        group.bg, group.words, group.radius = bg, words, radius
        group.cut = is_cut(words, upper)
        return group
    bar_w, gap = cap * 2.6, cap * 1.1
    words = fit_text(upper, width=max_width - bar_w - gap, size=size, min_size=24, max_lines=2, font=pal.font,
                     weight="BOLD", color=pal.accent_text, align="left", line_spacing=1.05)
    bar = Rectangle(width=bar_w, height=max(cap * 0.32, 0.035)).set_fill(pal.accent_text, 1).set_stroke(width=0)
    bar.next_to(words.lines[0], LEFT, buff=gap)
    group = VGroup(bar, words)
    group.bg, group.words, group.radius = bar, words, 0
    group.cut = is_cut(words, upper)
    return group


def marker(name, pal: Palette, *, size: float, color: str):
    """An icon, or a small dot when the icon is missing (so rows still line up)."""
    ico = media.icon(name, size=size, color=color, stroke_width=max(2.0, size * 9)) if name else VGroup()
    if len(ico.submobjects) or len(getattr(ico, "points", [])):
        box = Rectangle(width=size, height=size).set_opacity(0)
        ico.move_to(box.get_center())
        return VGroup(box, ico)
    dot = Circle(radius=size * 0.17).set_fill(color, 1).set_stroke(width=0)
    box = Rectangle(width=size, height=size).set_opacity(0)
    return VGroup(box, dot)


def detail_row(item, pal: Palette, *, width: float, size: float, color: str, icon_color: str,
               max_lines: int = 2):
    cap = cap_height(size, pal.font, "SEMIBOLD")
    icon_size = cap * 1.9
    gap = cap * 1.0
    words = fit_text(item.text, width=width - icon_size - gap, size=size, min_size=24, max_lines=max_lines,
                     font=pal.font, weight="SEMIBOLD", color=color, align="left", line_spacing=1.08)
    mark = marker(item.icon, pal, size=icon_size, color=icon_color)
    mark.next_to(words.lines[0], LEFT, buff=gap)
    mark.set_y(words.lines[0].get_center()[1])
    row = VGroup(mark, words)
    row.mark, row.words = mark, words
    return row


def details_block(items_, pal: Palette, *, width: float, size: float, columns: int = 1, chips: bool = False,
                  align: str = "left", gap_scale: float = 1.0):
    """Detail rows as a column (or a grid / a row with ``columns``), optionally on chips."""
    if not items_:
        return None
    cap = cap_height(size, pal.font, "SEMIBOLD")
    col_gap = cap * (2.2 if chips else 3.2)
    col_w = (width - col_gap * (columns - 1)) / columns
    pad_x, pad_y = (cap * 1.3, cap * 0.95) if chips else (0, 0)
    inner = col_w - 2 * pad_x
    # One font size for every row: the smallest any row needs.
    trial = [detail_row(it, pal, width=inner, size=size, color=pal.text, icon_color=pal.accent_on_surface
                        if chips else pal.accent_text) for it in items_]
    common = min(r.words.font_size for r in trial)
    rows = trial if all(abs(r.words.font_size - common) < 0.01 for r in trial) else [
        detail_row(it, pal, width=inner, size=common, color=pal.text,
                   icon_color=pal.accent_on_surface if chips else pal.accent_text) for it in items_]
    cells = []
    if chips:
        chip_w = max(r.width for r in rows) + 2 * pad_x
        if columns > 1:
            chip_w = col_w
        chip_h = max(r.height for r in rows) + 2 * pad_y
        radius = min(chip_h / 2, max(pal.radius * 1.4, cap * 0.6)) if max(len(r.words.lines) for r in rows) == 1 \
            else max(pal.radius * 1.4, cap * 0.6)
        for r in rows:
            bg = shapes.card(chip_w, chip_h, color=pal.surface, radius=radius, stroke=pal.line, stroke_width=2)
            r.move_to(bg.get_center())
            r.align_to(bg.get_left() + RIGHT * pad_x, LEFT)
            cell = VGroup(bg, r)
            cell.bg, cell.row = bg, r
            cells.append(cell)
    else:
        for r in rows:
            cell = VGroup(r)
            cell.bg, cell.row = None, r
            cells.append(cell)
    row_gap = cap * (0.9 if chips else 1.25) * gap_scale
    grid = VGroup()
    nrows = math.ceil(len(cells) / columns)
    cell_h = max(c.height for c in cells)
    for i, cell in enumerate(cells):
        r, c = divmod(i, columns)
        x = c * (col_w + col_gap)
        y = -r * (cell_h + row_gap)
        if align == "center" and columns == 1:
            cell.move_to([0, y, 0])
        else:
            cell.move_to([x, y, 0]).align_to([x, 0, 0], LEFT)
        grid.add(cell)
    # A short last grid row is centered under the others.
    if columns > 1 and len(cells) % columns and align == "center":
        last = [g for i, g in enumerate(grid) if i // columns == nrows - 1]
        span = VGroup(*last)
        span.set_x(VGroup(*grid[:columns]).get_center()[0])
    grid.move_to([0, 0, 0])
    grid.cells = cells
    grid.font_size = common
    grid.cut = any(is_cut(r.words, it.text) for r, it in zip(rows, items_))
    grid.max_lines = max(len(r.words.lines) for r in rows)
    return grid


def button(text: str, pal: Palette, *, max_width: float, size: float = 32, fill: str, color: str,
           radius: float | None = None):
    cap = cap_height(size, pal.font, "BOLD")
    pad_x = cap * 1.9
    words = fit_text(text, width=max_width - 2 * pad_x, size=size, min_size=24, max_lines=1, font=pal.font,
                     weight="BOLD", color=color)
    if words.font_size < size * 0.84 or words.width > max_width - 2 * pad_x + 1e-3 or "…" in words.lines[0].original_text:
        words = fit_text(text, width=max_width - 2 * pad_x, size=size, min_size=24, max_lines=2, font=pal.font,
                         weight="BOLD", color=color, line_spacing=1.06)
    cap = cap_height(words.font_size, pal.font, "BOLD")
    h = max(cap * 3.3, words.height + cap * 2.2)
    w = words.width + 2 * pad_x
    r = h / 2 if (radius is None and len(words.lines) == 1) else (radius if radius is not None else cap * 1.2)
    bg = shapes.card(w, h, color=fill, radius=r)
    words.move_to(bg.get_center())
    group = VGroup(bg, words)
    group.bg, group.words, group.radius, group.fill = bg, words, r, fill
    group.cut = is_cut(words, text)
    return group


def qr_card(data: str, *, size: float, radius: float = 0.1):
    """A QR code on a white card (always dark on white, so phones can scan it)."""
    raw = shapes.qr_code(data, size=size, color="#111111", background=None, quiet_zone=2)
    card = shapes.card(size, size, color="#FFFFFF", radius=min(radius, size * 0.08))
    if raw is None:
        return None
    modules = merge(list(raw.submobjects), "#111111")
    modules.move_to(card.get_center())
    group = VGroup(card, modules)
    group.card, group.modules = card, modules
    return group


def sticker(text: str, pal: Palette, *, diameter: float, fill: str, color: str):
    """A round badge with the big text, for the photo layout."""
    disc = Circle(radius=diameter / 2).set_fill(fill, 1).set_stroke(width=0)
    ring = Circle(radius=diameter / 2 * 0.88).set_fill(opacity=0).set_stroke(color, width=2.5, opacity=0.55)
    side = diameter * 0.64
    words = big_type(text, pal, width=side, height=side * 0.78, color=color)
    group = VGroup(disc, ring, words)
    group.disc, group.ring, group.words = disc, ring, words
    return group


def logo(path: str, *, height: float, max_width: float):
    if path.lower().endswith(".svg"):
        mob = media.svg_logo(path, height=height)
    else:
        mob = media.image(path, height=height, max_px=900)
    if mob.width > max_width:
        mob.scale(max_width / mob.width)
    return mob


@lru_cache(maxsize=16)
def _cover_pixels(path: str, mtime: float, ratio: float, max_px: int):
    from PIL import Image, ImageOps

    img = ImageOps.exif_transpose(Image.open(path)).convert("RGBA")
    w, h = img.size
    if w / h > ratio:
        nw = int(round(h * ratio))
        left = (w - nw) // 2
        img = img.crop((left, 0, left + nw, h))
    else:
        nh = int(round(w / ratio))
        top = max(0, int((h - nh) * 0.4))  # keep a little more of the top (faces, product tops)
        img = img.crop((0, top, w, top + nh))
    if max(img.size) > max_px:
        img.thumbnail((max_px, max_px), Image.LANCZOS)
    return np.array(img)


def photo_cover(path: str, *, width: float, height: float, max_px: int = 1600):
    """The photo cropped to fill width x height exactly (like CSS object-fit: cover)."""
    pixels = _cover_pixels(path, os.path.getmtime(path), width / height, max_px)
    mob = ImageMobject(pixels)
    mob.stretch_to_fit_width(width)
    mob.stretch_to_fit_height(height)
    return mob


def ticket(width: float, height: float, *, split: float, vertical: bool, notch: float, radius: float,
           color: str, stroke: str):
    """A card with two half-round notches at the perforation (``split`` = fraction along the card)."""
    from manim import RoundedRectangle

    body = RoundedRectangle(width=width, height=height, corner_radius=min(radius, width / 2.2, height / 2.2))
    if vertical:  # perforation across the card (top part / stub below)
        y = height / 2 - height * split
        cuts = [Circle(radius=notch).move_to([-width / 2, y, 0]), Circle(radius=notch).move_to([width / 2, y, 0])]
    else:
        x = -width / 2 + width * split
        cuts = [Circle(radius=notch).move_to([x, height / 2, 0]), Circle(radius=notch).move_to([x, -height / 2, 0])]
    shape = Difference(body, cuts[0])
    shape = Difference(shape, cuts[1])
    shape.set_fill(color, 1).set_stroke(stroke, width=2)
    return shape


def perforation(start, end, *, color: str, dash: float):
    line = DashedLine(start, end, dash_length=dash, dashed_ratio=0.55)
    line.set_stroke(color, width=3)
    return line


def dot_grid(width: float, height: float, *, step: float, radius: float, color: str, opacity: float):
    dots = []
    cols, rows = int(width / step) + 2, int(height / step) + 2
    for r in range(rows):
        for c in range(cols):
            x = -width / 2 + c * step + (step / 2 if r % 2 else 0)
            y = height / 2 - r * step
            dots.append(Circle(radius=radius, num_components=7).move_to([x, y, 0]))
    return merge(dots, color, opacity)


def rings(radius: float, *, count: int, color: str, opacity: float, thickness: float, clip=None):
    """Concentric rings as filled bands (so they can be clipped to *clip*, a Rectangle)."""
    out = VGroup()
    for i in range(count):
        r = radius * (i + 1) / count
        band = Difference(Circle(radius=r + thickness / 2), Circle(radius=max(r - thickness / 2, 1e-3)))
        out.add(band)
    shape = merge(list(out), color, opacity)
    return shape


def clip_to(mob, rect, color: str, opacity: float):
    """*mob* (one path) cut to the rectangle *rect*."""
    from manim import Intersection

    shape = Intersection(mob, rect)
    shape.set_fill(color, opacity).set_stroke(width=0)
    return shape


# -- motion -------------------------------------------------------------------
def rise_words(mob, *, unit: float, run_time: float, lag: float, by: str = "word", distance: float = 1.0):
    """Lines of a fit_text block coming up word by word (or char by char)."""
    pieces = []
    for line in text_lines(mob):
        pieces += glyph_groups(line, by)
    shift = max(mob.height / max(len(text_lines(mob)), 1), unit * 4) * 0.55 * distance
    anims = [FadeIn(p, shift=UP * shift, run_time=run_time, rate_func=QUART) for p in pieces]
    anim = LaggedStart(*anims, lag_ratio=lag / run_time if run_time else 0)
    anim.pieces = pieces
    return anim


def slam_chars(mob, *, run_time: float, lag: float, scale: float = 1.7):
    pieces = []
    for line in text_lines(mob):
        pieces += glyph_groups(line, "char")
    anims = [FadeIn(p, scale=scale, run_time=run_time, rate_func=QUART) for p in pieces]
    return LaggedStart(*anims, lag_ratio=lag / run_time if run_time else 0)


def grow_width(mob, *, run_time: float, edge=None, rate_func=QUART):
    """Stretch *mob* open from its center (or an edge: LEFT / RIGHT / UP / DOWN) to its final shape."""
    target = mob.copy()
    dim = 1 if edge is not None and (edge is UP or edge is DOWN or np.allclose(np.abs(edge), [0, 1, 0])) else 0

    def update(m, alpha):
        k = max(rate_func(alpha), 0.002)
        m.become(target.copy().stretch(k, dim, about_edge=edge if edge is not None else np.zeros(3)))

    return UpdateFromAlphaFunc(mob, update, run_time=run_time)


def open_shape(mob, rebuild, *, run_time: float, anchor: str = "center", rate_func=QUART):
    """Grow a rounded shape horizontally without squashing its corners: ``rebuild(width)`` makes it."""
    full_w = mob.width
    left, center = mob.get_left()[0], mob.get_center()

    def update(m, alpha):
        w = max(full_w * rate_func(alpha), mob.height * 0.02 + 1e-3)
        shape = rebuild(w)
        if anchor == "left":
            shape.move_to([left + w / 2, center[1], 0])
        else:
            shape.move_to(center)
        m.become(shape)

    return UpdateFromAlphaFunc(mob, update, run_time=run_time)


def pop(mob, *, run_time: float, scale: float = 0.6):
    return FadeIn(mob, scale=scale, run_time=run_time, rate_func=BACK)


def breathe(mob, *, run_time: float, period: float = 1.6, amount: float = 0.035, delay: float = 0.2):
    """A gentle repeating pulse (for the call to action while the video holds)."""
    state = {"k": 1.0}
    center = mob.get_center()

    def update(m, alpha):
        t = alpha * run_time - delay
        k = 1.0 if t <= 0 else 1.0 + amount * (0.5 - 0.5 * math.cos(2 * math.pi * t / period))
        if alpha >= 1:
            k = 1.0
        m.scale(k / state["k"], about_point=center)
        state["k"] = k

    return UpdateFromAlphaFunc(mob, update, run_time=run_time)


def drift(mob, *, run_time: float, scale: float = 1.0, angle: float = 0.0, shift=None):
    """Slow continuous motion over the hold (linear, so it never stops abruptly before the end)."""
    state = {"a": 0.0}
    center = mob.get_center()
    shift = np.zeros(3) if shift is None else np.array(shift)

    def update(m, alpha):
        da = alpha - state["a"]
        if da == 0:
            return
        k_prev = scale ** state["a"]
        k_new = scale ** alpha
        c = center + shift * state["a"]
        m.scale(k_new / k_prev, about_point=c)
        m.rotate(angle * da, about_point=c)
        m.shift(shift * da)
        state["a"] = alpha

    return UpdateFromAlphaFunc(mob, update, run_time=run_time, rate_func=lambda t: t)


def together(*anims):
    anims = [a for a in anims if a is not None]
    return AnimationGroup(*anims) if anims else None
