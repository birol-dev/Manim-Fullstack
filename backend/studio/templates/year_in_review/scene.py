"""Year in numbers: the year big, each number counting up, then a recap grid and a closing line.

Timeline (``moments``): intro (year + title) -> the year shrinks into a header -> one full-screen
beat per stat (badge, number counting, label; a ring and a progress segment fill with the count)
-> the header grows into the recap header, the cards rise in -> closing line -> hold.
``grid``: intro -> recap header, then the cards come in one by one, each counting as the next one
arrives -> closing line -> hold. Pacing is solved from the requested length (see ``_plan``).
"""

from __future__ import annotations

import math
import re

import numpy as np
from manim import (
    PI,
    RIGHT,
    TAU,
    UP,
    Arc,
    Circle,
    FadeIn,
    FadeOut,
    Group,
    LaggedStart,
    ReplacementTransform,
    ValueTracker,
    VGroup,
    rate_functions,
)

from studio.kit import Region, StudioScene, fit_text, label, measure, media, shapes, size_for_height, wrap
from studio.kit import fonts
from studio.kit.motion import ease_out, overshoot

from .parts import StatNumber, StatSpec, badge, number_width_per_size
from .schema import META, Params

# Descender room under the digits' baseline (commas), as a fraction of the digit height.
DESC = 0.24
_TRAILING = re.compile(r"\*([^*]+)\*([!?.,;:…]+)")


def glue_punctuation(text: str) -> str:
    """"Here's to *2027*!" -> "Here's to *2027!*" (fit_text would put a space before the "!")."""
    return _TRAILING.sub(lambda mt: f"*{mt.group(1)}{mt.group(2)}*", text)


def count_rate(t: float) -> float:
    """Fast start, long soft landing: the last digits settle instead of stopping dead."""
    return 1 - (1 - t) ** 4


def _solve(budget: float, flex: list) -> list:
    """Durations for flexible segments [(ideal, minimum, maximum, weight)] that sum to *budget* if possible."""
    ideal = sum(f[0] for f in flex)
    low = sum(f[1] for f in flex)
    if budget <= ideal:
        if ideal - low < 1e-9:
            return [f[1] for f in flex]
        frac = max(0.0, min(1.0, (budget - low) / (ideal - low)))
        return [f[1] + frac * (f[0] - f[1]) for f in flex]
    out = [f[0] for f in flex]
    extra = budget - ideal
    for _ in range(4):  # hand out the extra by weight, respecting maximums
        room = [(i, f[3]) for i, f in enumerate(flex) if out[i] < f[2] - 1e-6 and f[3] > 0]
        if extra <= 1e-6 or not room:
            break
        total = sum(w for _, w in room)
        given = 0.0
        for i, w in room:
            add = min(extra * w / total, flex[i][2] - out[i])
            out[i] += add
            given += add
        extra -= given
    return out


class Template(StudioScene):
    Params = Params
    META = META

    # ------------------------------------------------------------------ build
    def build(self):
        p, theme = self.p, self.theme
        self.u = self.layout.unit
        self.specs = [StatSpec(s, i, self.s.locale) for i, s in enumerate(p.stats)]
        self.font = theme.font
        self.dw = theme.display_weight
        self.moments = p.style == "moments"
        self.photo = self.asset(p.photo)
        self.plan = self._plan()
        if self.mode == "poster":
            self.moments = False  # the poster is the recap: same final frame, skip building the beats
        self._intro()
        if self.moments:
            self._to_header()
            for i, spec in enumerate(self.specs):
                self._beat(i, spec)
        self._recap()

    # ------------------------------------------------------------------ timing
    def _plan(self) -> dict:
        m, n = self.motion, len(self.specs)
        k = m.k
        length = self.target_length - (m.exit if self.s.ending == "fade" else 0)
        closing_read = m.reading_time(self.p.closing, minimum=0.6) * 0.5 if self.p.closing else 0.0
        fixed = {
            "year_in": 0.9 * k,
            "title_in": 0.6 * k,
            "move": 0.7 * k,
            "enter": 0.55 * k,
            "leave": 0.4 * k,
            "card_in": 0.5 * k,
            "recap_in": 0.7 * k,
            "closing_in": 0.6 * k,
        }
        if self.moments:
            used = (fixed["year_in"] + fixed["title_in"] + fixed["move"] + n * (fixed["enter"] + fixed["leave"])
                    + fixed["recap_in"] + 0.08 * k * (n - 1) + fixed["closing_in"])
            flex = ([(0.8 * k, 0.25, 1.8, 0.4)] + [(1.4 * k, 0.7, 2.4, 0.7)] * n + [(0.9 * k, 0.3, 2.0, 1.0)] * n
                    + [(2.4 + closing_read, 1.6 + closing_read, 99, 1.5)])
        else:
            used = (fixed["year_in"] + fixed["title_in"] + fixed["move"] + fixed["card_in"]
                    + fixed["closing_in"])
            flex = ([(0.8 * k, 0.25, 1.8, 0.4)] + [(1.25 * k, 0.6, 2.2, 1.0)] * n
                    + [(2.4 + closing_read, 1.6 + closing_read, 99, 1.5)])
        # Too short for the content: tighten the animations too (never below 65 %), then overrun.
        squeeze = 1.0
        minimum = used + sum(f[1] for f in flex)
        if minimum > length:
            squeeze = max(0.65, (length - sum(f[1] for f in flex)) / used) if used else 1.0
        fixed = {key: v * squeeze for key, v in fixed.items()}
        durations = _solve(length - used * squeeze, flex)
        plan = dict(fixed)
        plan["intro_hold"] = durations[0]
        plan["count"] = durations[1:1 + n]
        plan["hold"] = durations[1 + n:1 + 2 * n] if self.moments else [0.0] * n
        plan["final_hold"] = durations[-1]
        plan["final_min"] = flex[-1][1]
        plan["stagger"] = 0.08 * k * squeeze
        return plan

    # ------------------------------------------------------------------ shared pieces
    def _sized(self, text: str, *, height: float, max_width: float, weight: str) -> float:
        """Font size whose digits are *height* tall, reduced so *text* fits *max_width*."""
        size = size_for_height(height, font=self.font, weight=weight)
        w = measure(text, size=size, font=self.font, weight=weight)
        if w > max_width:
            size *= max_width / w
        return size

    def _year(self, height: float, max_width: float):
        text = self.theme.display(self.p.year or " ")
        size = self._sized(text, height=height, max_width=max_width, weight=self.dw)
        return label(text, size=size, font=self.font, weight=self.dw, color=self.theme.text)

    def _name(self, size: float, max_width: float):
        if not self.p.name:
            return None
        return self._full_text(self.p.name, width=max_width, size=size, min_size=24, max_lines=2,
                               font=self.font, weight="BOLD", color=self.theme.muted, align="left")

    @staticmethod
    def _full_text(source, **kwargs):
        mob = fit_text(source, **kwargs)
        if any("…" in line.original_text for line in mob.lines) and "…" not in source:
            mob = fit_text(source, **{**kwargs, "height": None, "size": 24, "min_size": 24,
                                      "max_lines": max(8, len(source.split()))})
        if mob.width > kwargs["width"]:
            mob.scale(kwargs["width"] / mob.width)
        return mob

    def _avatar(self, diameter: float):
        if not self.photo:
            return None
        img = media.image(self.photo, height=diameter, shape="circle", max_px=800)
        ring = Circle(radius=diameter / 2 + self.u * 0.9).set_stroke(self.theme.accent(0), width=diameter * 3.2)
        ring.move_to(img.get_center())
        return Group(ring, img)

    def _title(self, *, width: float, size: float, max_lines: int, align: str = "center", height=None):
        if not self.p.title:
            return None
        return self._full_text(glue_punctuation(self.theme.display(self.p.title)), width=width, height=height, size=size, min_size=24,
                        max_lines=max_lines, font=self.font, weight=self.dw, color=self.theme.text,
                        emphasis_color=self.theme.accent(0), align=align)

    def _closing(self, *, width: float, size: float, max_lines: int, align: str, height=None):
        if not self.p.closing:
            return None
        return self._full_text(glue_punctuation(self.theme.display(self.p.closing)), width=width, height=height, size=size, min_size=24,
                        max_lines=max_lines, font=self.font, weight=self.dw, color=self.theme.text,
                        emphasis_color=self.theme.accent(0), align=align)

    @staticmethod
    def _move_onto(mob, target):
        """Animation: scale and move *mob* onto *target*'s box (same text, other size/place)."""
        return ReplacementTransform(mob, target)

    # ------------------------------------------------------------------ intro
    def _intro(self):
        lay, theme, m, u = self.layout, self.theme, self.motion, self.u
        safe = lay.safe
        portrait = lay.is_portrait
        land = lay.is_landscape
        avatar = self._avatar((22 if portrait else 17) * u)
        name = self._name(36 if not land else 34, safe.width * 0.8)
        year_h = min(safe.height * (0.17 if portrait else 0.27), 34 * u)
        year = self._year(year_h, safe.width * 0.86)
        n = len(self.specs)
        bar_h, bar_gap = 1.8 * u, 1.2 * u
        seg = (22 * u - bar_gap * (n - 1)) / n
        bar = VGroup(*[shapes.pill(seg, bar_h, color=theme.accent(i)) for i in range(n)])
        bar.arrange(RIGHT, buff=bar_gap)
        title = self._title(width=safe.width * (0.86 if not land else 0.7), size=60 if portrait else 56,
                            max_lines=2)

        stack = [(avatar, 4 * u), (name, 5 * u), (year, 4.5 * u), (bar, 4.5 * u), (title, 0)]
        stack = [(mob, gap) for mob, gap in stack if mob is not None]
        total = sum(mob.height for mob, _ in stack) + sum(gap for _, gap in stack[:-1])
        y = safe.center[1] + total / 2 + (2 * u if portrait else 0)
        for mob, gap in stack:
            mob.move_to([safe.center[0], y - mob.height / 2, 0])
            y -= mob.height + gap

        d = u * 5
        year_in = LaggedStart(*[FadeIn(ch, shift=UP * d, run_time=self.plan["year_in"] * 0.7, rate_func=ease_out)
                                for ch in year], lag_ratio=0.12, run_time=self.plan["year_in"])
        first = [year_in]
        if avatar is not None:
            first.append(FadeIn(avatar, scale=0.7, run_time=self.plan["year_in"] * 0.8, rate_func=overshoot))
        if name is not None:
            first.append(m.appear(name, "drop", run_time=self.plan["year_in"] * 0.8))
        self.cue("pop")
        self.play(*first)
        second = [LaggedStart(*[FadeIn(b, scale=0.3, run_time=self.plan["title_in"] * 0.6, rate_func=ease_out)
                                for b in bar], lag_ratio=0.15, run_time=self.plan["title_in"])]
        if title is not None:
            second.append(m.appear(title, "rise", run_time=self.plan["title_in"]))
        self.play(*second)
        self.wait(self.plan["intro_hold"])
        self.year_mob, self.name_mob, self.avatar_mob, self.bar_mob, self.title_mob = year, name, avatar, bar, title

    # ------------------------------------------------------------------ moments
    def _header_targets(self):
        """Small year (top left) and name (top right) shown during the beats."""
        lay, u = self.layout, self.u
        safe = lay.safe
        year = self._year(3.6 * u, safe.width * 0.4)
        year.move_to([safe.left + year.width / 2, safe.top - year.height / 2, 0])
        name = None
        if self.p.name:
            room = safe.width - year.width - 6 * u
            name = self._name(28, room)
            if name.width > room:
                name = None
            else:
                name.move_to([safe.right - name.width / 2, safe.top - name.height / 2, 0])
        return year, name

    def _to_header(self):
        lay, theme, u = self.layout, self.theme, self.u
        safe = lay.safe
        n = len(self.specs)
        year_t, name_t = self._header_targets()
        self.header_top = safe.top
        self.header_bottom = min(year_t.get_bottom()[1], name_t.get_bottom()[1] if name_t is not None else safe.top)

        # progress segments along the bottom: one per stat, filled as its number counts
        seg_h = 1.1 * u
        gap = 1.6 * u
        seg_w = (safe.width - gap * (n - 1)) / n
        y = safe.bottom + seg_h / 2
        self.seg_y = y
        self.seg_w, self.seg_h = seg_w, seg_h
        self.seg_x = [safe.left + seg_w / 2 + i * (seg_w + gap) for i in range(n)]
        tracks = VGroup(*[shapes.pill(seg_w, seg_h, color=theme.text, opacity=0.14).move_to([x, y, 0])
                          for x in self.seg_x])
        self.tracks = tracks
        self.fills = VGroup()

        anims = [self._move_onto(self.year_mob, year_t), FadeIn(tracks, run_time=self.plan["move"])]
        outgoing = [mob for mob in (self.bar_mob, self.title_mob, self.avatar_mob) if mob is not None]
        anims += [FadeOut(mob, shift=UP * 3 * u, run_time=self.plan["move"] * 0.7) for mob in outgoing]
        if self.name_mob is not None:
            if name_t is not None:
                anims.append(self._move_onto(self.name_mob, name_t))
            else:
                anims.append(FadeOut(self.name_mob, run_time=self.plan["move"] * 0.7))
                self.name_mob = None
        self.play(*anims, run_time=self.plan["move"])
        self.year_mob, self.name_mob = year_t, name_t
        self.bar_mob = self.title_mob = self.avatar_mob = None

    def _body(self) -> Region:
        safe, u = self.layout.safe, self.u
        return Region(safe.left, safe.right, self.header_bottom - 4 * u, self.seg_y + self.seg_h / 2 + 4 * u)

    def _beat(self, i: int, spec: StatSpec):
        lay, theme, m, u = self.layout, self.theme, self.motion, self.u
        body = self._body()
        color = theme.accent(i)
        icon_color = theme.on_accent
        use_row = lay.is_landscape and spec.icon is not None

        # badge with a ring that fills with the count
        if use_row:
            ring_d = min(body.height * 0.5, body.width * 0.26)
        else:
            ring_d = min(body.height * (0.27 if lay.is_portrait else 0.30), body.width * 0.42)
        disc_d = ring_d * 0.76
        bdg = badge(spec.icon, disc_d, fill=color, icon_color=icon_color)
        if bdg is None:
            ring_d = 0.0

        # number and label sizes
        per_size = number_width_per_size(spec, self.font, self.dw)
        if use_row:
            text_w = body.width - ring_d - 8 * u
            digit_h = min(body.height * 0.24, 22 * u)
            label_w = text_w
        else:
            text_w = body.width * 0.92
            digit_h = min(body.height * (0.145 if lay.is_portrait else 0.17), 26 * u)
            label_w = body.width * (0.86 if not lay.is_landscape else 0.7)
        size = size_for_height(digit_h, font=self.font, weight=self.dw)
        if per_size * size > text_w:
            size = text_w / per_size
        number = StatNumber(spec, size=size, font=self.font, weight=self.dw, color=theme.text, unit_color=color,
                            align="left" if use_row else "center", start=0)
        dh = number.digit_height()
        lbl = None
        if spec.label:
            lbl = fit_text(spec.label, width=label_w, size=54 if lay.is_portrait else 50, min_size=30, max_lines=2,
                           font=self.font, weight="NORMAL", color=theme.text,
                           align="left" if use_row else "center")
        lbl_h = lbl.height if lbl is not None else 0.0
        num_gap = 3.5 * u

        # place
        cx, cy = body.center[0], body.center[1]
        if use_row:
            final_w = max(per_size * size, lbl.width if lbl is not None else 0)
            total_w = ring_d + 8 * u + final_w
            left = cx - total_w / 2
            ring_center = np.array([left + ring_d / 2, cy, 0])
            block_h = dh + DESC * dh + (num_gap + lbl_h if lbl is not None else 0)
            top = cy + block_h / 2
            tx = left + ring_d + 8 * u
            number.place(tx, top - dh)
            if lbl is not None:
                lbl.move_to([tx + lbl.width / 2, top - dh - DESC * dh - num_gap - lbl_h / 2, 0])
        else:
            ring_gap = 7 * u if ring_d else 0.0
            block_h = ring_d + ring_gap + dh + DESC * dh + (num_gap + lbl_h if lbl is not None else 0)
            top = cy + block_h / 2
            ring_center = np.array([cx, top - ring_d / 2, 0])
            base = top - ring_d - ring_gap - dh
            number.place(cx, base)
            if lbl is not None:
                lbl.move_to([cx, base - DESC * dh - num_gap - lbl_h / 2, 0])

        prog = ValueTracker(0.0)
        pieces = []
        enter = []
        if bdg is not None:
            bdg.move_to(ring_center)
            ring_r = ring_d / 2 - u * 0.6
            ring_w = max(4.0, ring_d * 5.0)
            halo = Circle(radius=ring_d * 0.64).set_fill(color, opacity=0.13 if theme.dark else 0.16)
            halo.set_stroke(width=0).move_to(ring_center)
            track = Circle(radius=ring_r).set_stroke(theme.text, width=ring_w, opacity=0.12).move_to(ring_center)

            def make_arc():
                frac = max(prog.get_value(), 1e-4)
                return Arc(radius=ring_r, start_angle=PI / 2, angle=-TAU * frac,
                           arc_center=ring_center).set_stroke(color, width=ring_w)

            arc = make_arc()
            arc.add_updater(lambda a: a.become(make_arc()))
            pieces += [halo, track, arc, bdg]
            enter += [FadeIn(halo, scale=0.6, run_time=self.plan["enter"] * 1.2, rate_func=ease_out),
                      FadeIn(track, run_time=self.plan["enter"]),
                      FadeIn(bdg, scale=0.5, run_time=self.plan["enter"], rate_func=overshoot)]
            self.add(arc)
        else:
            arc = None
        enter.append(m.appear(number, "rise", run_time=self.plan["enter"]))
        pieces.append(number)
        if lbl is not None:
            enter.append(m.appear(lbl, "rise", run_time=self.plan["enter"], delay=self.plan["enter"] * 0.15))
            pieces.append(lbl)

        # this stat's progress segment
        x0 = self.seg_x[i] - self.seg_w / 2

        def make_fill():
            w = max(self.seg_w * prog.get_value(), self.seg_h)
            return shapes.pill(w, self.seg_h, color=color).move_to([x0 + w / 2, self.seg_y, 0])

        fill = make_fill()
        fill.add_updater(lambda f: f.become(make_fill()))
        self.add(fill)
        self.fills.add(fill)

        self.play(*enter)
        count = self.plan["count"][i]
        _, counting = number.counting(0, spec.value, count, count_rate)
        self.play(counting, prog.animate(run_time=count, rate_func=count_rate).set_value(1.0))
        number.stop()
        self.cue("tick")
        fill.clear_updaters()
        if arc is not None:
            arc.clear_updaters()
        self.wait(self.plan["hold"][i])
        self.play(*[FadeOut(pc, shift=UP * 4 * u, run_time=self.plan["leave"], rate_func=rate_functions.ease_in_cubic)
                    for pc in pieces])

    # ------------------------------------------------------------------ recap
    def _name_row(self, x: float, y_center: float, row_h: float, max_right: float, size: float):
        """Avatar + name on one line starting at *x*; returns (avatar, name)."""
        avatar = self._avatar(row_h - 1.8 * self.u) if self.photo else None
        if avatar is not None:
            avatar.move_to([x + avatar.width / 2, y_center, 0])
            x += avatar.width + 2.5 * self.u
        name = self._name(size, max_right - x)
        if name is not None:
            name.move_to([x + name.width / 2, y_center, 0])
        return avatar, name

    def _recap_header(self):
        """Year, title, name, avatar, closing line in their recap places, and the region left for the grid."""
        lay, u = self.layout, self.u
        safe = lay.safe
        has_row = bool(self.p.name) or self.photo is not None
        avatar = name = title = closing = None

        if not lay.is_landscape and not lay.is_portrait or (lay.is_portrait and lay.aspect > 0.7):
            # 1:1 and 4:5: the year on the left, name and title beside it, so the grid gets the height
            year = self._year((10.5 if lay.is_square else 12.5) * u, safe.width * 0.5)
            x0 = safe.left + year.width + 5 * u
            rw = safe.right - x0
            if rw >= safe.width * 0.4:
                title = self._title(width=rw, size=40, max_lines=2, align="left")
                name_probe = self._name(26, rw)
                name_h = max(5.5 * u, name_probe.height if name_probe is not None else 0) if has_row else 0.0
                block_h = name_h + (1.5 * u if has_row and title is not None else 0) + (title.height if title else 0)
                year.move_to([safe.left + year.width / 2, safe.top - max(year.height, block_h) / 2, 0])
                by = year.get_center()[1] + block_h / 2
                if has_row:
                    avatar, name = self._name_row(x0, by - name_h / 2, name_h, safe.right, 26)
                    by -= name_h + 1.5 * u
                if title is not None:
                    title.move_to([x0 + title.width / 2, by - title.height / 2, 0])
                header_bottom = min(year.get_bottom()[1], title.get_bottom()[1] if title is not None else by)
                closing = self._closing(width=safe.width, size=36, max_lines=2, align="left")
                if closing is not None:
                    closing.move_to([safe.left + closing.width / 2, safe.bottom + closing.height / 2, 0])
                bottom = closing.get_top()[1] + 4 * u if closing is not None else safe.bottom
                return year, title, name, avatar, closing, Region(safe.left, safe.right, header_bottom - 5 * u, bottom)

        land = lay.is_landscape
        col = Region(safe.left, safe.left + safe.width * 0.34, safe.top, safe.bottom) if land else safe
        width = col.width
        row_h = (8 if lay.is_portrait else 7) * u
        name_probe = self._name(30, width)
        if name_probe is not None:
            row_h = max(row_h, name_probe.height)
        y = col.top
        if has_row:
            avatar, name = self._name_row(col.left, y - row_h / 2, row_h, col.right, 30)
            y -= row_h + 3 * u
        year = self._year((13 if lay.is_portrait else 14) * u, width * (1.0 if land else 0.6))
        year.move_to([col.left + year.width / 2, y - year.height / 2, 0])
        y -= year.height + 3.5 * u
        if self.p.title:
            title = self._title(width=width, size=48 if not land else 46, max_lines=3 if land else 2, align="left")
            title.move_to([col.left + title.width / 2, y - title.height / 2, 0])
            y -= title.height
        if self.p.closing:
            closing = self._closing(width=width, size=42 if lay.is_portrait else 38, max_lines=3 if land else 2,
                                    align="left")
            closing.move_to([col.left + closing.width / 2, col.bottom + closing.height / 2, 0])
        if land:
            grid = Region(col.right + 6 * u, safe.right, safe.top, safe.bottom)
        else:
            bottom = (closing.get_top()[1] + 5 * u) if closing is not None else safe.bottom
            grid = Region(safe.left, safe.right, y - 6 * u, bottom)
        return year, title, name, avatar, closing, grid

    def _label_h(self, text: str, width: float, size: float) -> float:
        """Height fit_text will give *text* (at most 2 lines) at *size* in *width* (an upper bound)."""
        if not text:
            return 0.0
        if not hasattr(self, "_ref_lines"):
            self._ref_lines = (label("bdgjy", size=48, font=self.font).height,
                               label("ÁgjÉ", size=48, font=self.font).height * 1.12)
        one, step = self._ref_lines
        lines = min(2, len(wrap(text, size=size, width=width, font=fonts.resolve(self.font))))
        return (one + (lines - 1) * step) * size / 48

    def _grid_option(self, region: Region, cols: int, kind: str, label_size: float, badges: bool, per_h: float):
        u, n = self.u, len(self.specs)
        gap = 3 * u
        rows = math.ceil(n / cols)
        cw = (region.width - gap * (cols - 1)) / cols
        ch = (region.height - gap * (rows - 1)) / rows
        if cw <= 0 or ch <= 0:
            return None
        lbl_gap = 1.4 * u
        if kind == "tile":
            ch = min(ch, cw * 1.05)
            pad = max(3 * u, min(min(cw, ch) * 0.1, 5 * u))
            d = min(ch * 0.22, (cw - 2 * pad) * 0.25, 10 * u) if badges else 0.0
            text_w = cw - 2 * pad
            above = (d + 2 * u) if d else 0.0
        else:
            ch = min(ch, cw * 0.42)
            pad = max(2.5 * u, min(ch * 0.14, 5 * u))
            d = min(ch - 2 * pad, 16 * u, cw * 0.22) if badges else 0.0
            text_w = cw - 2 * pad - ((d + 3.5 * u) if d else 0.0)
            above = 0.0
        if text_w < 20 * u:
            return None
        lh = max(self._label_h(s.label, text_w, label_size) for s in self.specs)
        avail = ch - 2 * pad - above - ((lh + lbl_gap) if lh else 0.0)
        dh = min(avail / (1 + DESC), ch * (0.3 if kind == "tile" else 0.36), text_w / per_h)
        return {"cols": cols, "rows": rows, "kind": kind, "cw": cw, "ch": ch, "pad": pad, "d": d, "text_w": text_w,
                "label_size": label_size, "lh": lh, "lbl_gap": lbl_gap, "dh": dh, "gap": gap,
                "empty": cols * rows - n, "badges": badges}

    def _choose_grid(self, region: Region, per_h: float) -> dict:
        """The card grid where the numbers come out largest with everything fitting.

        Badges carry each stat's color, so they stay unless the numbers would get too small with them."""
        n = len(self.specs)
        any_icon = any(s.icon for s in self.specs)
        probes = [StatNumber(s, size=24, font=self.font, weight=self.dw, color=self.theme.text,
                             unit_color=self.theme.text) for s in self.specs]
        min_width = max(probe.width for probe in probes)
        min_height = max(probe.digit_height() for probe in probes)
        best = {}
        for badges in ((True, False) if any_icon else (False,)):
            top, top_score = None, -1e9
            for kind, sizes in (("tile", (28, 24)), ("row", (30, 26, 24))):
                for label_size in sizes:
                    for cols in range(1, min(n, 4) + 1):
                        opt = self._grid_option(region, cols, kind, label_size, badges, per_h)
                        if opt is None:
                            continue
                        if opt["dh"] < min_height or opt["text_w"] < min_width:
                            continue
                        if any(len(wrap(s.label, size=label_size, width=opt["text_w"],
                                        font=fonts.resolve(self.font))) > 2 for s in self.specs):
                            continue
                        score = opt["dh"] - 0.03 * opt["empty"] - 0.006 * (30 - label_size)
                        if score > top_score:
                            top, top_score = opt, score
            best[badges] = top
        with_b, without = best.get(True), best.get(False)
        if with_b is not None and (without is None or with_b["dh"] >= max(0.3, 0.6 * without["dh"])):
            return with_b
        return without

    def _card_pages(self, region, start):
        """Dense full-length numbers get several readable recap pages."""
        all_specs = self.specs
        pages = []
        try:
            remaining = list(all_specs)
            while remaining:
                for count in range(len(remaining), 0, -1):
                    self.specs = remaining[:count]
                    per_h = max(number_width_per_size(s, self.font, self.dw) for s in self.specs) * size_for_height(
                        1.0, font=self.font, weight=self.dw)
                    if self._choose_grid(region, per_h) is not None:
                        break
                cards, numbers = self._cards(region, start)
                pages.append((cards, numbers))
                remaining = remaining[count:]
        finally:
            self.specs = all_specs
        return pages

    def _cards(self, region: Region, start):
        """Card groups and their numbers, laid out in *region*."""
        theme, u = self.theme, self.u
        n = len(self.specs)
        per_h = max(number_width_per_size(s, self.font, self.dw) for s in self.specs) * size_for_height(
            1.0, font=self.font, weight=self.dw)
        g = self._choose_grid(region, per_h)
        cols, rows, kind, cw, ch, pad, d = g["cols"], g["rows"], g["kind"], g["cw"], g["ch"], g["pad"], g["d"]
        gap, lbl_gap, lh = g["gap"], g["lbl_gap"], g["lh"]
        size = max(24.0, size_for_height(max(g["dh"], 0.1), font=self.font, weight=self.dw))
        grid_h = rows * ch + (rows - 1) * gap
        top = region.top - max(0.0, (region.height - grid_h) / 2)

        cards, numbers = [], []
        for idx, spec in enumerate(self.specs):
            r, c = divmod(idx, cols)
            in_row = min(cols, n - r * cols)
            row_w = in_row * cw + (in_row - 1) * gap
            x0 = region.center[0] - row_w / 2 + c * (cw + gap)
            y0 = top - r * (ch + gap)
            cell_c = np.array([x0 + cw / 2, y0 - ch / 2, 0])
            color = theme.accent(spec.index)
            bg = shapes.card(cw, ch, color=theme.surface, radius=min(theme.radius * 1.2, ch * 0.2),
                             stroke=theme.line, stroke_width=2.5).move_to(cell_c)
            parts = [bg]
            num = StatNumber(spec, size=size, font=self.font, weight=self.dw, color=theme.text, unit_color=color,
                             align="left", start=start)
            if num.width > g["text_w"]:
                num = StatNumber(spec, size=max(24, size * g["text_w"] / num.width * 0.98), font=self.font,
                                 weight=self.dw, color=theme.text, unit_color=color, align="left", start=start)
            ndh = num.digit_height()
            bdg = badge(spec.icon, d, fill=color, icon_color=theme.on_accent) if d else None
            lb = fit_text(spec.label, width=g["text_w"], size=g["label_size"], min_size=24, max_lines=2,
                          font=self.font, color=theme.muted, align="left") if spec.label else None
            left = x0 + pad
            if kind == "row":
                if d:
                    if bdg is not None:
                        bdg.move_to([left + d / 2, cell_c[1], 0])
                    left += d + 3.5 * u
                block = ndh * (1 + DESC) + ((lbl_gap + lh) if lh else 0)
                base = cell_c[1] + block / 2 - ndh
            else:
                if bdg is not None:
                    bdg.move_to([left + d / 2, y0 - pad - d / 2, 0])
                base = y0 - ch + pad + ((lh + lbl_gap) if lh else 0) + DESC * ndh
            num.place(left, base)
            if lb is not None:
                lb.move_to([left + lb.width / 2, base - DESC * ndh - lbl_gap - lb.height / 2, 0])
            if bdg is not None:
                parts.append(bdg)
            parts.append(num)
            if lb is not None:
                parts.append(lb)
            cards.append(VGroup(*parts))
            numbers.append(num)
        return cards, numbers

    def _recap(self):
        m, u = self.motion, self.u
        plan = self.plan
        year_t, title_t, name_t, avatar_t, closing, grid = self._recap_header()
        pages = self._card_pages(grid, start=None if self.moments else 0)
        cards, numbers = pages[0]

        anims = [self._move_onto(self.year_mob, year_t)]
        move_t = plan["recap_in"] if self.moments else plan["move"]
        if self.name_mob is not None and name_t is not None:
            anims.append(self._move_onto(self.name_mob, name_t))
        elif name_t is not None:
            anims.append(m.appear(name_t, "fade", run_time=move_t))
            self.name_mob = name_t
        if self.moments:
            anims.append(FadeOut(self.tracks, run_time=move_t * 0.6))
            anims += [FadeOut(f, run_time=move_t * 0.6) for f in self.fills]
            if title_t is not None:
                anims.append(m.appear(title_t, "rise", run_time=move_t))
            if avatar_t is not None:
                anims.append(FadeIn(avatar_t, scale=0.7, run_time=move_t, rate_func=ease_out))
            anims.append(LaggedStart(*[m.appear(cd, "rise", run_time=move_t) for cd in cards],
                                     lag_ratio=plan["stagger"] / max(move_t, 0.01)))
            self.play(*anims)
        else:
            if self.avatar_mob is not None and avatar_t is not None:
                anims.append(self._move_onto(self.avatar_mob, avatar_t))
            if self.title_mob is not None:
                anims.append(FadeOut(self.title_mob, shift=UP * 3 * u, run_time=move_t * 0.6))
            if title_t is not None:
                anims.append(m.appear(title_t, "rise", run_time=move_t, delay=move_t * 0.3))
            anims.append(FadeOut(self.bar_mob, run_time=move_t * 0.5))
            self.play(*anims, run_time=move_t)
            self.play(m.appear(cards[0], "rise", run_time=plan["card_in"]))
            for i, card in enumerate(cards):
                count = plan["count"][i]
                _, counting = numbers[i].counting(0, self.specs[i].value, count, count_rate)
                group = [counting]
                if i + 1 < len(cards):
                    group.append(m.appear(cards[i + 1], "rise", run_time=min(plan["card_in"], count)))
                self.play(*group)
                numbers[i].stop()
                self.cue("tick")

        if closing is not None:
            self.play(m.appear(closing, "rise", run_time=plan["closing_in"]))
        for next_cards, next_numbers in pages[1:]:
            self.wait(max(2.0, plan["final_min"]))
            self.play(*[FadeOut(card) for card in cards], run_time=m.exit)
            # Each stat has already counted in moments mode. Grid mode continues
            # counting on the next page rather than showing overlapping cards.
            self.play(m.appear_each(next_cards, "rise"))
            for num in next_numbers:
                if not self.moments:
                    _, counting = num.counting(0, num.spec.value, plan["count"][num.spec.index], count_rate)
                    self.play(counting)
                    num.stop()
                    self.cue("tick")
            cards, numbers = next_cards, next_numbers
        self.poster()
        self.target_length = max(self.target_length, self.elapsed + plan["final_min"]
                                 + (m.exit if self.s.ending == "fade" else 0))
