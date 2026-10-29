"""Text that fits: wrapping, shrinking, balanced lines, and *emphasis* in one call.

Pango is slow (every ``Text`` is a layout plus SVG conversion), so words are measured
once at a reference size and scaled; measurements are cached for the whole process,
which makes repeat previews in the warm worker nearly free.
"""

from __future__ import annotations

import re
from functools import lru_cache

from manim import LEFT, RIGHT, Text, VGroup

from . import fonts

REF_SIZE = 48
_EMPHASIS = re.compile(r"\*([^*]+)\*")


@lru_cache(maxsize=8192)
def _word_width(word: str, font: str, weight: str) -> float:
    return Text(word, font=font, weight=weight, font_size=REF_SIZE, disable_ligatures=True).width


@lru_cache(maxsize=64)
def _metrics(font: str, weight: str) -> tuple:
    """(space width, line height) at REF_SIZE."""
    spaced = Text("n n", font=font, weight=weight, font_size=REF_SIZE).width
    tight = Text("nn", font=font, weight=weight, font_size=REF_SIZE).width
    tall = Text("ÁgjÉ", font=font, weight=weight, font_size=REF_SIZE).height
    return max(spaced - tight, REF_SIZE * 0.004), tall


def measure(text: str, *, size: float, font: str, weight: str = "NORMAL") -> float:
    """Approximate width of one line (kerning between words ignored)."""
    words = text.split()
    if not words:
        return 0.0
    space, _ = _metrics(font, weight)
    total = sum(_word_width(w, font, weight) for w in words) + space * (len(words) - 1)
    return total * size / REF_SIZE


def _greedy(words, widths, space, limit):
    lines, current, width = [], [], 0.0
    for word, w in zip(words, widths):
        extra = w if not current else space + w
        if current and width + extra > limit:
            lines.append(current)
            current, width = [word], w
        else:
            current.append(word)
            width += extra
    if current:
        lines.append(current)
    return lines


def wrap(text: str, *, size: float, width: float, font: str, weight: str = "NORMAL", balance: bool = True) -> list:
    """Lines (strings) no wider than *width*; with ``balance`` the lines come out even
    ("a long title" / "that wraps" rather than "a long title that" / "wraps")."""
    paragraphs = [p for p in text.split("\n")]
    space, _ = _metrics(font, weight)
    scale = size / REF_SIZE
    out = []
    for para in paragraphs:
        words = para.split()
        if not words:
            out.append("")
            continue
        widths = [_word_width(w, font, weight) * scale for w in words]
        lines = _greedy(words, widths, space * scale, width)
        if balance and len(lines) > 1:
            lo, hi = max(widths), width
            for _ in range(14):
                mid = (lo + hi) / 2
                if len(_greedy(words, widths, space * scale, mid)) <= len(lines):
                    hi = mid
                else:
                    lo = mid
            lines = _greedy(words, widths, space * scale, hi + 1e-6)
        out.extend(" ".join(line) for line in lines)
    return out


def _strip_emphasis(text: str) -> tuple:
    """Text without the asterisks, and the (start, end) character spans that were emphasized.

    Spans may cover part of a word ("Kadı*köy*", "*today*!"), so punctuation stays attached.
    """
    plain, spans, pos = [], [], 0
    length = 0
    for match in _EMPHASIS.finditer(text):
        before = text[pos:match.start()]
        plain.append(before)
        length += len(before)
        inner = match.group(1)
        spans.append((length, length + len(inner)))
        plain.append(inner)
        length += len(inner)
        pos = match.end()
    plain.append(text[pos:])
    return "".join(plain), spans


def fit_text(
    text: str,
    *,
    width: float,
    height: float | None = None,
    size: float = 48,
    min_size: float = 24,
    max_lines: int = 3,
    font: str = "Inter",
    weight: str = "NORMAL",
    color: str = "#FFFFFF",
    emphasis_color: str | None = None,
    align: str = "center",
    line_spacing: float = 1.12,
    balance: bool = True,
) -> VGroup:
    """Text wrapped to *width*, shrunk until it fits *max_lines* (and *height*).

    Words wrapped in ``*asterisks*`` get *emphasis_color* (when given). Returns a VGroup
    of line ``Text`` objects (``.lines`` holds them) centered at the origin. Explicit
    newlines in *text* are kept. At *min_size* the last line is cut with an ellipsis.
    """
    family = fonts.resolve(font)
    if emphasis_color is not None and "*" in text:
        source, spans = _strip_emphasis(text)
    else:
        source, spans = text, []
    _, ref_line = _metrics(family, weight)

    chosen, chosen_size = None, size
    current = size
    while True:
        lines = wrap(source, size=current, width=width, font=family, weight=weight, balance=balance)
        line_h = ref_line * current / REF_SIZE * line_spacing
        fits_lines = len(lines) <= max_lines
        fits_height = height is None or line_h * len(lines) <= height
        # one word longer than the line can't wrap: shrink for it too
        fits_width = all(measure(line, size=current, font=family, weight=weight) <= width for line in lines)
        if fits_lines and fits_height and fits_width:
            chosen, chosen_size = lines, current
            break
        if current <= min_size:
            keep = max_lines if height is None else max(1, min(max_lines, int(height // line_h)))
            chosen = lines[:keep]
            if len(lines) > keep:
                last = chosen[-1]
                while last and measure(last + "…", size=current, font=family, weight=weight) > width:
                    last = last.rsplit(" ", 1)[0] if " " in last else last[:-1]
                chosen[-1] = (last or "").rstrip(" ,.;:") + "…"
            chosen_size = current
            break
        current = max(min_size, current * 0.92)

    # Lines are the source's words joined by single spaces, in order: map each word back
    # to its characters in the source to color the emphasized parts.
    word_spans = [m.span() for m in re.finditer(r"\S+", source)]
    group = VGroup()
    word_index = 0
    for line in chosen:
        if not line:
            group.add(Text(" ", font=family, font_size=chosen_size))
            continue
        t2c = {}
        offset = 0
        for w in line.split(" "):
            if word_index < len(word_spans):
                start, end = word_spans[word_index]
                for es, ee in spans:
                    lo, hi = max(es, start), min(ee, end)
                    if lo < hi:
                        a, b = offset + lo - start, min(offset + hi - start, offset + len(w))
                        if a < b:
                            t2c[f"[{a}:{b}]"] = emphasis_color
            offset += len(w) + 1
            word_index += 1
        group.add(Text(line, font=family, weight=weight, font_size=chosen_size, color=color, t2c=t2c,
                       disable_ligatures=True))
    line_h = ref_line * chosen_size / REF_SIZE * line_spacing
    for i, line in enumerate(group):
        line.move_to([0, -i * line_h, 0])
        if align == "left":
            line.align_to([0, 0, 0], LEFT)
        elif align == "right":
            line.align_to([0, 0, 0], RIGHT)
    group.move_to([0, 0, 0])
    if group.width > width * 1.001:  # a word too long even at min_size: never overflow the box
        chosen_size *= width / group.width
        group.scale_to_fit_width(width)
    group.lines = list(group)
    group.font_size = chosen_size
    return group


def label(text: str, *, size: float = 28, font: str = "Inter", weight: str = "NORMAL", color: str = "#FFFFFF",
          max_width: float | None = None) -> Text:
    """A single line, shrunk (never wrapped) to *max_width*."""
    family = fonts.resolve(font)
    if max_width is not None:
        w = measure(text, size=size, font=family, weight=weight)
        if w > max_width:
            size = max(10, size * max_width / w)
    return Text(text or " ", font=family, weight=weight, font_size=size, color=color, disable_ligatures=True)



@lru_cache(maxsize=256)
def _digit_height(font: str, weight: str) -> float:
    return Text("0", font=font, weight=weight, font_size=REF_SIZE).height


def size_for_height(height: float, *, font: str = "Inter", weight: str = "NORMAL") -> float:
    """The font size whose digits ("0") are *height* units tall."""
    family = fonts.resolve(font)
    return REF_SIZE * height / _digit_height(family, weight)
