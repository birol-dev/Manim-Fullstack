"""Measured, readable chart type and an accent-based slice palette."""
import re

from studio.kit import fit_text, fonts
from studio.kit.text import measure


MIN_TYPE = 24  # fit_text's minimum readable size; never scale below it.


def text(source, *, width, size=40, height=None, min_size=MIN_TYPE, break_words=True, **options):
    """Wrap full text, including unbroken words, without ellipses or tiny type."""
    options["font"] = fonts.resolve(options["font"])
    # Prefer intact words at a smaller readable size to splitting off a letter.
    for current in range(int(size), min_size - 1, -2):
        mob = fit_text(source, width=width, size=current, min_size=current,
                       max_lines=max(1, len(source)), line_spacing=1.08, **options)
        if mob.font_size >= min_size - .01 and (height is None or mob.height <= height + 1e-6):
            return mob
    if not break_words:
        raise ValueError("This word needs more room.")
    for current in range(int(size), min_size - 1, -2):
        pieces = []
        for token in re.findall(r"\*[^*]+\*|[^\s*]+|\s+|\*", source):
            marked = token.startswith("*") and token.endswith("*") and len(token) > 2
            word = token[1:-1] if marked else token
            lines, line = [], ""
            for char in word:
                if line and measure(line + char, size=current, font=options["font"],
                                    weight=options.get("weight", "NORMAL")) > width * .96:
                    lines.append(line)
                    line = ""
                line += char
            lines.append(line)
            pieces.append("\n".join(f"*{part}*" if marked else part for part in lines))
        mob = fit_text("".join(pieces), width=width, size=current, min_size=current,
                       max_lines=max(1, len(source)), line_spacing=1.08, **options)
        if mob.font_size >= min_size - .01 and (height is None or mob.height <= height + 1e-6):
            return mob
    raise ValueError("Shorten this line so it has room to breathe.")


def luminance(color):
    rgb = [int(color.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in rgb]
    return sum(c * w for c, w in zip(linear, (.2126, .7152, .0722)))


def contrast(a, b):
    light, dark = sorted((luminance(a), luminance(b)), reverse=True)
    return (light + .05) / (dark + .05)


def ink_on(color):
    """Choose black or white by measured WCAG contrast."""
    return max(("#000000", "#FFFFFF"), key=lambda ink: contrast(ink, color))


def slice_colors(accent, count, dark=False):
    """Alternate shades and tints, including across the closing slice boundary."""
    rgb = [int(accent.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    levels = []
    pairs = count // 2
    for i in range(pairs):
        levels.extend((.08 + .08 * i / max(1, pairs - 1),
                       .48 + .30 * i / max(1, pairs - 1)))
    if count % 2:
        levels.append(.29)
    colors = []
    for target in levels:
        target += .02 if dark else 0
        end = 1 if luminance(accent) < target else 0
        lo, hi = 0., 1.
        for _ in range(18):
            mix = (lo + hi) / 2
            color = "#" + "".join(f"{round((c * (1 - mix) + end * mix) * 255):02X}" for c in rgb)
            if (luminance(color) < target) == bool(end):
                lo = mix
            else:
                hi = mix
        colors.append(color)
    return colors


def visible_segments(start, end, labels, padding=.09):
    """Clip a connector around measured value boxes, leaving the glyphs clear."""
    delta = end - start
    visible = [(0., 1.)]
    for mob in labels:
        enter, leave = 0., 1.
        for axis, lo, hi in ((0, mob.get_left()[0] - padding, mob.get_right()[0] + padding),
                             (1, mob.get_bottom()[1] - padding, mob.get_top()[1] + padding)):
            if abs(delta[axis]) < 1e-9:
                if not lo <= start[axis] <= hi:
                    break
            else:
                a, b = sorted(((lo - start[axis]) / delta[axis], (hi - start[axis]) / delta[axis]))
                enter, leave = max(enter, a), min(leave, b)
                if enter >= leave:
                    break
        else:
            visible = [(a, b) for lo, hi in visible
                       for a, b in ((lo, min(hi, enter)), (max(lo, leave), hi)) if b - a > 1e-6]
    return [(start + lo * delta, start + hi * delta) for lo, hi in visible]
