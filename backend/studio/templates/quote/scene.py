"""Quote & text post: the text is the hero; header details come first, the name arrives last."""

from __future__ import annotations

import re

import numpy as np
from manim import Circle, Group, ImageMobject, Star, VGroup, VMobject

from studio.kit import StudioScene, fit_text, media, shapes

from .reveal import Choreography, Piece, Pulse
from .schema import META, Params

STAR_GOLD = "#F5A524"   # rating stars are gold in every theme (a rating colour people recognise)
DIM = 0.22               # opacity of not-yet-read text in the highlight sweep
# How much room the details take, roomiest first. ``pref`` is the smallest text size that is still
# comfortable; when a level cannot give the text that, the next one shrinks the details further
# (the decorative quote mark goes first).
LEVELS = [
    dict(mark=13, mark_l=10, star=3.9, avatar=12, name=34, role=28, kicker=30, gap=1.0, wide=False, pref=30),
    dict(mark=9, mark_l=7, star=3.3, avatar=10, name=30, role=26, kicker=27, gap=0.7, wide=False, pref=30),
    dict(mark=0, mark_l=0, star=3.0, avatar=9, name=28, role=24, kicker=24, gap=0.55, wide=True, pref=0),
]

SENTENCE_END = ".!?…"
CLAUSE_END = ",;:–—"


# --------------------------------------------------------------------------- text helpers
def clean_text(raw: str) -> str:
    """One flowing paragraph; punctuation touching a *highlight* joins it, so '*fast*.' stays '*fast.*'."""
    flat = re.sub(r"\s+", " ", raw or "").strip()
    return re.sub(r"([^\s*]*)\*([^*]+)\*([^\s*]*)", lambda m: f"*{m[1]}{m[2]}{m[3]}*", flat)


def emphasis_flags(marked: str) -> list:
    """For every word of *marked* (text with *asterisks*): is it highlighted?"""
    flags, pos = [], 0
    for match in re.finditer(r"\*([^*]+)\*", marked):
        flags += [False] * len(marked[pos:match.start()].split())
        flags += [True] * len(match.group(1).split())
        pos = match.end()
    return flags + [False] * len(marked[pos:].split())


def shout(text: str, locale: str) -> str:
    """Upper case for themes that shout; Turkish and Azeri keep their dotted and dotless i."""
    if locale[:2] in ("tr", "az"):
        text = text.replace("i", "İ").replace("ı", "I")
    return text.upper()


def initials_of(name: str) -> str:
    parts = [w for w in re.split(r"[\s._-]+", name.lstrip("@")) if w]
    if not parts:
        return ""
    letters = parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")
    return letters.upper()


def _luminance(hex_color: str) -> float:
    rgb = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def text_size_cap(chars: int) -> float:
    """Biggest type for a text of this length: short lines shout, long ones read like a paragraph."""
    return float(np.interp(chars, [10, 30, 70, 130, 240], [112, 100, 78, 60, 46]))


def words_of(line) -> list:
    """(glyph group, string) for each word of a fit_text line, or one entry for the whole line when the
    glyphs do not line up with the characters (emoji and the like)."""
    source = getattr(line, "original_text", "") or ""
    glyphs = list(line.submobjects)
    if len(source) != len(glyphs):
        return [(VGroup(*glyphs), source)]
    words, current, chars = [], [], []
    for ch, glyph in zip(source, glyphs):
        if ch.isspace():
            if current:
                words.append((VGroup(*current), "".join(chars)))
                current, chars = [], []
        else:
            current.append(glyph)
            chars.append(ch)
    if current:
        words.append((VGroup(*current), "".join(chars)))
    return words


FLAT_BOTTOM = set("hiklmnrxzıEFHIKLMNTXYZ1")


def baseline_of(line) -> float:
    """y of a line's baseline, read from glyphs that sit flat on it (falls back to the box bottom)."""
    source = getattr(line, "original_text", "") or ""
    glyphs = list(line.submobjects)
    if len(source) == len(glyphs):
        bottoms = [g.get_bottom()[1] for ch, g in zip(source, glyphs) if ch in FLAT_BOTTOM]
        if not bottoms:
            bottoms = [g.get_bottom()[1] for ch, g in zip(source, glyphs) if ch.isalnum() and ch not in "gjpqyçşQJ"]
        if bottoms:
            return float(np.median(bottoms))
    return float(line.get_bottom()[1])


def level_baselines(text) -> None:
    """fit_text spaces line *centres* evenly, so leading wobbles with ascenders and descenders;
    this moves each line so the baselines are evenly spaced instead."""
    lines = text.lines
    if len(lines) < 2:
        return
    pitch = (lines[0].get_center()[1] - lines[-1].get_center()[1]) / (len(lines) - 1)
    first = baseline_of(lines[0])
    for i, line in enumerate(lines):
        line.shift([0, (first - i * pitch) - baseline_of(line), 0])
    text.move_to(np.zeros(3))


# --------------------------------------------------------------------------- shapes
def _comma(height: float, color: str) -> VMobject:
    """One half of a quote mark: a teardrop whose tail curls to the upper right."""
    k = 0.5523
    pts = lambda x, y: np.array([x, y, 0.0])
    comma = VMobject()
    comma.start_new_path(pts(-1, 0))
    comma.add_cubic_bezier_curve_to(pts(-1, 1.0), pts(-0.2, 2.0), pts(1.5, 2.3))     # outer edge up to the tip
    comma.add_cubic_bezier_curve_to(pts(0.4, 1.6), pts(1.0, 0.9), pts(1, 0))          # inner edge back down
    comma.add_cubic_bezier_curve_to(pts(1, -k), pts(k, -1), pts(0, -1))               # the round bowl
    comma.add_cubic_bezier_curve_to(pts(-k, -1), pts(-1, -k), pts(-1, 0))
    comma.set_fill(color, 1).set_stroke(width=0)
    return comma


def quote_mark(height: float, color: str) -> VGroup:
    """A big opening quote mark (two commas) drawn from shapes, so it looks the same in every font."""
    first, second = _comma(1, color), _comma(1, color)
    second.next_to(first, np.array([1.0, 0, 0]), buff=0.5)
    mark = VGroup(first, second)
    mark.scale_to_fit_height(height)
    return mark


def star_row(count: int, radius: float, gap: float, gold: str, empty: str) -> VGroup:
    """Five stars, the first *count* filled. Soft corners keep them friendly."""
    row = VGroup()
    for i in range(5):
        star = Star(n=5, outer_radius=radius, inner_radius=radius * 0.47)
        star.round_corners(radius * 0.13)
        if i < count:
            star.set_fill(gold, 1)
        else:
            star.set_fill(empty, 0.16)
        star.set_stroke(width=0)
        row.add(star)
    row.arrange(buff=gap)
    return row


# --------------------------------------------------------------------------- the scene
class Template(StudioScene):
    Params = Params
    META = META

    def build(self):
        p, theme, lay, m = self.p, self.theme, self.layout, self.motion
        u = lay.unit
        stage = lay.safe
        left = p.align == "left"
        accent = p.accent or theme.accent(0)

        # ---- the text, cleaned
        marked = clean_text(p.text) or "…"
        plain = marked.replace("*", "")
        n = len(plain)
        if theme.case == "upper" and n <= 120:
            marked = shout(marked, self.s.locale)

        # ---- compose at the roomiest density where the whole text still reads comfortably;
        #      a crowded post (every field filled, long text) gets smaller details, never a cut-off text
        for level, lv in enumerate(LEVELS):
            parts = self._compose(lv, marked, plain, accent, left)
            if level == len(LEVELS) - 1 or (not parts["cut"] and parts["text"].font_size >= lv["pref"]):
                break
        header, attribution, text = parts["header"], parts["attribution"], parts["text"]
        mark, kicker, stars = parts["mark"], parts["kicker"], parts["stars"]
        gap_footer = parts["gap_footer"]

        # ---- stack everything, centered in the safe area
        stack = [(item, gap) for _, item, gap in header]
        stack.append((text, gap_footer))
        if attribution is not None:
            stack.append((attribution["group"], 0.0))
        total = sum(item.height + gap for item, gap in stack)
        y = stage.center[1] + total / 2
        cx = stage.center[0]
        for item, gap in stack:
            x = stage.left + item.width / 2 if left else cx
            item.move_to([x, y - item.height / 2, 0])
            y -= item.height + gap

        self.blocks = {name: item for name, item, _ in header}
        self.blocks["text"] = text
        if attribution is not None:
            self.blocks["attribution"] = attribution["group"]

        # ---- the choreography
        pieces = []
        t0 = 0.0
        if mark is not None:
            for i, comma in enumerate(mark):
                pieces.append(Piece(comma, m.t(0.06 * i), m.t(0.6), "pop"))
            t0 = m.t(0.3)
        if kicker is not None:
            pieces.append(Piece(kicker, m.t(0.1), m.t(0.5), "rise", dist=2 * u))
            t0 = max(t0, m.t(0.4))
        if stars is not None:
            for i, star in enumerate(stars):
                pieces.append(Piece(star, m.t(0.2 + 0.08 * i), m.t(0.45), "pop"))
            t0 = max(t0, m.t(0.55))
        t0 = max(t0, m.t(0.15))
        text_end = self._schedule_text(pieces, text, marked, plain, t0, accent, u)

        t_name = text_end + m.t(0.2)
        if attribution is not None:
            self._schedule_attribution(pieces, attribution, t_name, u)

        timeline_end = max(piece.end for piece in pieces)
        needed = max(timeline_end + m.t(1.2), t0 + m.reading_time(plain) + 0.5)
        if self.s.ending == "fade":
            needed += m.exit + 0.15
        self.target_length = max(self.target_length, needed)

        # play it in a few windows (header, the text in thirds, the name): one frame each in the storyboard
        choreo = Choreography(self, pieces, [item for item, _ in stack])
        span = max(text_end - t0, 0.0)
        cuts = [0.0, t0, t0 + span / 3, t0 + 2 * span / 3, text_end, choreo.end]
        edges = [cuts[0]]
        for c in cuts[1:]:
            if c - edges[-1] >= 0.05:
                edges.append(c)
        if edges[-1] < choreo.end:
            edges[-1] = choreo.end
        self.cue("whoosh")  # studio-audio
        for a, b in zip(edges, edges[1:]):
            choreo.play(a, b)
        self.poster()

    def _compose(self, lv: dict, marked: str, plain: str, accent: str, left: bool) -> dict:
        """Build header, attribution and the fitted text at one density level."""
        p, theme, lay = self.p, self.theme, self.layout
        u, stage = lay.unit, lay.safe
        compact = lay.is_landscape
        bg = self.s.background.color if self.s.background.kind in ("solid", "gradient") and self.s.background.color             else theme.bg
        gold = STAR_GOLD if contrast(STAR_GOLD, bg) >= 1.7 else accent
        wrap_w = stage.width * (1.0 if lay.is_portrait else (0.92 if lv["wide"] else 0.8) if compact else 0.94)
        k = lv["gap"]
        n = len(plain)
        weight = theme.display_weight if n <= 110 else ("BOLD" if theme.display_weight == "HEAVY" else "SEMIBOLD")

        header = []  # (name, mobject, gap below)
        mark_h = lv["mark_l"] if compact else lv["mark"]
        mark = quote_mark(mark_h * u, accent) if (p.quote_marks and mark_h > 0) else None
        if mark is not None:
            header.append(("mark", mark, 4 * u * k))
        kicker = None
        if p.kicker:
            kicker = self._kicker(p.kicker, accent, stage.width, u, theme.case == "upper", lv["kicker"])
            header.append(("kicker", kicker, 4.5 * u * k))
        stars = None
        if p.stars:
            stars = star_row(p.stars, lv["star"] * u, lv["star"] * 0.44 * u, gold, theme.text)
            header.append(("stars", stars, 5 * u * k))

        attribution = self._attribution(p, accent, stage.width if not compact else wrap_w, u, left, lv)
        gap_footer = (8 if not compact else 6) * u * k if attribution is not None else 0.0
        used = sum(item.height + gap for _, item, gap in header) + gap_footer
        used += attribution["group"].height if attribution is not None else 0.0
        box_h = max(stage.height - used, 3 * u)
        cap = text_size_cap(n) * (0.8 if marked == marked.upper() and theme.case == "upper" else 1.0)
        text = self._best_fit(marked, wrap_w, box_h, cap, weight, accent, left)
        if text.width > wrap_w:  # one very long word: shrink rather than leave the frame
            text.scale(wrap_w / text.width)
        cut = text.lines[-1].original_text.endswith("…") and not plain.endswith("…")
        return {"header": header, "mark": mark, "kicker": kicker, "stars": stars, "attribution": attribution,
                "text": text, "gap_footer": gap_footer, "cut": cut}

    def _best_fit(self, marked, width, height, cap, weight, accent, left):
        """fit_text at the biggest size, unless a slightly smaller one wraps into more even lines
        (no lone short word on the first lines)."""
        theme = self.theme
        best, best_score = None, -1.0
        for factor in (1.0, 0.92, 0.85, 0.78):
            text = fit_text(marked, width=width, height=height, size=cap * factor, min_size=24, max_lines=24,
                            font=theme.font, weight=weight, color=theme.text, emphasis_color=accent,
                            align="left" if left else "center", line_spacing=1.16)
            widths = [line.width for line in text.lines]
            score = 1.0 if len(widths) < 3 else min(widths[:-1]) / max(widths)
            if score > best_score + 0.02:
                best, best_score = text, score
            if score >= 0.55 or text.font_size <= 24:
                break
        level_baselines(best)
        if best.height > height:  # levelling can add a hair of height
            best.scale(height / best.height)
        return best

    # ------------------------------------------------------------------ pieces of the post
    def _kicker(self, label_text: str, accent: str, max_w: float, u: float, shout_it: bool, size: float):
        theme = self.theme
        pad_x, pad_y = 2.6 * u, 1.6 * u
        shown = shout(label_text, self.s.locale) if shout_it else label_text
        words = fit_text(shown, width=max_w - 2 * pad_x, size=size, min_size=24, max_lines=2, font=theme.font,
                         weight="BOLD", color=theme.on_accent, align="center", line_spacing=1.1)
        w, h = words.width + 2 * pad_x, words.height + 2 * pad_y
        pill = shapes.card(w, h, color=accent, radius=min(h / 2, h * theme.radius * 2.2))
        words.move_to(pill.get_center())
        return VGroup(pill, words)

    def _attribution(self, p, accent: str, max_w: float, u: float, left: bool, lv: dict):
        """A row: round photo / initials disc / thin bar, then the name over the role. None if nothing to show."""
        theme = self.theme
        photo_path = self.asset(p.avatar) if p.avatar else None
        d = lv["avatar"] * u
        lead = ring = None
        if photo_path:
            lead = media.image(photo_path, height=d, shape="circle", max_px=512)
            ring = Circle(radius=d / 2 + 0.7 * u).set_stroke(accent, width=3).set_fill(opacity=0)
        elif p.initials and (p.author or p.role):
            disc = Circle(radius=d / 2).set_fill(accent, 1).set_stroke(width=0)
            letters = fit_text(initials_of(p.author or p.role), width=d * 0.7, height=d * 0.5, size=32, min_size=24,
                               max_lines=1, font=theme.font, weight="BOLD", color=theme.on_accent)
            letters.move_to(disc.get_center())
            lead = VGroup(disc, letters)
        if not (p.author or p.role or lead is not None):
            return None

        gap = 2.6 * u
        lead_w = (ring.width if ring is not None else lead.width) if lead is not None else 0.0
        text_w = max_w - ((lead_w + gap) if lead is not None else 3 * u)
        # centered and no photo: a short bar over centered lines; otherwise a row (photo / bar, then the lines)
        stacked = lead is None and not left
        align = "center" if stacked else "left"
        if stacked:
            text_w = max_w
        lines = []
        if p.author:
            lines.append(fit_text(p.author, width=text_w, size=lv["name"], min_size=24, max_lines=2, font=theme.font,
                                  weight="BOLD", color=theme.text, align=align, line_spacing=1.1))
        if p.role:
            lines.append(fit_text(p.role, width=text_w, size=lv["role"], min_size=24, max_lines=2, font=theme.font,
                                  weight="NORMAL", color=theme.muted if p.author else theme.text, align=align,
                                  line_spacing=1.1))
        for line in lines:
            if line.width > text_w:
                line.scale(text_w / line.width)
        info = None
        if lines:
            edge = np.array([0, 0, 0.0]) if stacked else np.array([-1.0, 0, 0])
            info = VGroup(*lines).arrange(np.array([0, -1.0, 0]), aligned_edge=edge, buff=1 * u)
        if stacked and info is not None:
            bar = shapes.pill(6 * u, 1.1 * u, color=accent)
            bar.next_to(info, np.array([0, 1.0, 0]), buff=3.4 * u)
            group = Group(bar, info).move_to(np.zeros(3))
            return {"group": group, "ring": None, "lead": bar, "info": info, "lines": lines, "bar": "pop"}
        if lead is None and info is not None:  # left aligned, no photo: a thin accent bar, like a block-quote rule
            lead = shapes.pill(0.95 * u, max(info.height, 4 * u), color=accent)
            lead_w = lead.width
        x = 0.0
        if lead is not None:
            lead.move_to([lead_w / 2, 0, 0])
            if ring is not None:
                ring.move_to(lead.get_center())
            x = lead_w + gap
        if info is not None:
            info.move_to([x + info.width / 2, 0, 0])
        members = [o for o in (ring, lead, info) if o is not None]
        group = Group(*members).move_to(np.zeros(3))
        return {"group": group, "ring": ring, "lead": lead, "info": info, "lines": lines, "bar": "slide"}

    # ------------------------------------------------------------------ the timing
    def _schedule_text(self, pieces, text, marked, plain, t0, accent, u) -> float:
        """Add the text's pieces; returns the time the last word has arrived."""
        p, theme, m = self.p, self.theme, self.motion
        flags = emphasis_flags(marked)
        reveal_time = m.t(float(np.clip(len(plain) / 24, 1.2, 11.0)))
        rise = 2.6 * u
        pop_for = lambda start: Pulse(start, m.t(0.5), 0.07, theme.text, accent)

        # flatten to words, keeping which line each belongs to
        words, index = [], 0
        for li, line in enumerate(text.lines):
            line_words = words_of(line)
            whole_line = len(line_words) == 1 and len(getattr(line, "original_text", "").split()) > 1
            count = len(getattr(line, "original_text", "").split())
            for group, string in line_words:
                words.append({"mob": group, "str": string, "line": li, "host": line,
                              "emph": (not whole_line) and index < len(flags) and flags[index]})
                index += 1 if not whole_line else 0
            if whole_line:
                index += count
        end = t0

        if p.reveal == "lines":
            weights = [len(line.original_text) + 6 for line in text.lines]
            total = float(sum(weights))
            starts, acc = [], 0.0
            for w in weights:
                starts.append(t0 + reveal_time * acc / total)
                acc += w
            dur = m.t(0.6)
            for li, line in enumerate(text.lines):
                pieces.append(Piece(line, starts[li], dur, "rise", dist=rise))
                end = max(end, starts[li] + dur)
            for w in words:
                if w["emph"]:
                    pieces.append(Piece(w["mob"], starts[w["line"]], 0.0, "none", host=w["host"],
                                        pulse=pop_for(starts[w["line"]] + dur * 0.85)))
            return end

        # words and sweep walk the words with a reading rhythm: longer words and punctuation take longer
        def weight(s: str) -> float:
            tail = s[-1:] if s else ""
            return len(s) + 1 + (4 if tail in SENTENCE_END else 2 if tail in CLAUSE_END else 0)

        total = float(sum(weight(w["str"]) for w in words)) or 1.0
        acc = 0.0
        if p.reveal == "sweep":
            enter = m.t(0.6)
            for li, line in enumerate(text.lines):  # the dimmed text comes in first, line by line
                pieces.append(Piece(line, t0 + m.t(0.1) * li, enter, "rise", dist=rise, to=DIM))
            t0 = t0 + m.t(0.1) * len(text.lines) + enter
            end = t0
        for w in words:
            start = t0 + reveal_time * acc / total
            acc += weight(w["str"])
            dur = m.t(0.5) if p.reveal == "words" else m.t(0.35)
            if p.reveal == "sweep":
                piece = Piece(w["mob"], start, dur, "dim", dim=DIM, host=w["host"])
            else:
                piece = Piece(w["mob"], start, dur, "rise", dist=rise, host=w["host"])
            if w["emph"]:
                piece.pulse = pop_for(start + dur * 0.6)
            pieces.append(piece)
            end = max(end, piece.end)
        return end

    def _schedule_attribution(self, pieces, attribution, t, u) -> None:
        m = self.motion
        ring, lead = attribution["ring"], attribution["lead"]
        if ring is not None:  # a photo: pop in with its ring
            pieces.append(Piece(ring, t, m.t(0.55), "pop"))
            pieces.append(Piece(lead, t, m.t(0.55), "pop"))
        elif lead is not None and isinstance(lead, ImageMobject):
            pieces.append(Piece(lead, t, m.t(0.55), "pop"))
        elif lead is not None and len(lead.submobjects) > 1:  # initials disc
            pieces.append(Piece(lead, t, m.t(0.55), "pop"))
        elif lead is not None:  # the accent bar
            pieces.append(Piece(lead, t, m.t(0.5), attribution["bar"], dist=2 * u))
        for i, line in enumerate(attribution["lines"]):
            pieces.append(Piece(line, t + m.t(0.12 * (i + 1)), m.t(0.5), "rise", dist=2 * u))
