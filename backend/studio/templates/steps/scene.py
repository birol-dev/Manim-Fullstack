"""Steps: a short list revealed one item at a time, with time to read each.

Styles share one motion language:

* ``numbered``  a numbered badge per item.
* ``checklist`` a box per item that ticks right after the item appears.
* ``timeline``  a vertical line with the time beside each dot.

Beats: the kicker and title enter -> one item at a time (it stays on screen while the next
arrives, with a reading pause after each) -> the complete list holds, and the poster is
taken on that full list.
"""

from __future__ import annotations

from math import ceil

from manim import RIGHT, Create, FadeIn, GrowFromCenter, LaggedStart, Line

from studio.kit import StudioScene, ease_out, label, overshoot

from . import parts as P
from .schema import META, Params


class Template(StudioScene):
    Params = Params
    META = META

    # -- entry -----------------------------------------------------------------
    def build(self):
        self._prepare()
        plan = self._plan()
        header, rows = self._compose()
        self._play(header, rows, plan)

    def _prepare(self):
        p, bg = self.p, self.s.background
        color = bg.color if bg.kind in ("solid", "gradient") and bg.color else None
        self.pal = P.Palette(self.theme, p.accent, color)
        self.steps = [s for s in p.steps if s.text.strip()]
        self.u = self.layout.unit
        self.highlight = min(p.highlight, len(self.steps)) if p.highlight > 0 else 0
        self.visible_rows = 0
        self.ticked = 0

    # -- timing ----------------------------------------------------------------
    def _plan(self) -> dict:
        m, n = self.motion, len(self.steps)
        pace = {"calm": 1.15, "punchy": 0.85}.get(self.s.energy, 1.0)
        reads = [m.reading_time(f"{s.text} {s.detail}".strip(), minimum=0.8) * pace for s in self.steps]
        tick = m.t(0.35) if self.p.style == "checklist" else 0.0
        intro = m.t(1.1) if self.p.title.strip() or self.p.kicker.strip() else 0
        enter = m.t(0.55)
        hold = max(2.2, m.t(1.5))
        ending = m.exit + 0.15 if self.s.ending == "fade" else 0
        natural = intro + n * (enter + tick) + sum(reads) + hold + ending
        if self.s.length is None and natural > 0:
            # The content sets the length: more items get more time (within the meta limits).
            wanted = ceil(natural * 2) / 2
            self.target_length = float(min(max(wanted, self.META.min_length), self.META.max_length))
        # Honour even a short explicit duration: scale entrances and pauses
        # together, rather than imposing a minimum pause that overruns the movie.
        factor = min(1.0, max(0, self.target_length - ending) / (natural - ending))
        plan = {"intro": intro * factor, "enter": enter * factor, "tick": tick * factor,
                "reads": [r * factor for r in reads], "natural": natural, "hold": hold * factor}
        self.plan = plan
        return plan

    # -- layout ----------------------------------------------------------------
    def _title_size(self) -> float:
        return 44 if len(self.steps) <= 5 else 28

    def _levels(self) -> list:
        """Actual type sizes: never scale a composed row to fit its slot."""
        start = 42 if self.layout.aspect < 0.7 else 36
        return [(size, max(24, round(size * 0.76)), 4, 3)
                for size in range(start, 23, -2)]

    def _compose(self):
        """Header and placed rows, without animation (also used by the layout tests)."""
        p, pal, lay = self.p, self.pal, self.layout
        S = lay.safe
        header = P.header(p.kicker, p.title, pal, width=S.width, title_size=self._title_size(),
                          title_lines=1 if lay.is_landscape else 2)
        tall = lay.aspect < 0.7
        header_gap = (0.52 if tall else 0.32) if len(self.steps) < 6 else 0.24
        if not len(header):
            header_gap = 0
        inset = 0.12
        available = S.height - 2 * inset - header.height - header_gap
        time_width = max((label(t, size=24, font=pal.font, weight="SEMIBOLD").width
                          for t in (s.time for s in self.steps) if t), default=0.0)
        min_gap = 0.08 if len(self.steps) >= 6 else 0.24
        def build(level, compact=False):
            text_size, detail_size, text_lines, detail_lines = level
            return [P.build_row(p.style, step, i, pal, width=S.width, time_width=time_width,
                                highlighted=(i + 1 == self.highlight), text_size=text_size,
                                detail_size=detail_size, text_lines=text_lines,
                                detail_lines=detail_lines, stacked_time=tall and not compact,
                                show_icon=lay.is_landscape and not compact, compact_detail=compact)
                    for i, step in enumerate(self.steps)]

        def fits(candidate):
            return sum(r.height for r in candidate) + min_gap * (len(candidate) - 1) <= available

        # Height is monotone with type size. Probe the floor before spending
        # Pango work on intermediate sizes, then find the largest fitting size.
        levels = self._levels()
        tested = {0: build(levels[0])}
        rows = tested[0] if fits(tested[0]) else None
        if rows is None:
            last = len(levels) - 1
            tested[last] = build(levels[last])
            if fits(tested[last]):
                lo, hi = 1, last
                while lo < hi:
                    mid = (lo + hi) // 2
                    tested[mid] = build(levels[mid])
                    if fits(tested[mid]):
                        hi = mid
                    else:
                        lo = mid + 1
                rows = tested[lo]
        if rows is None:
            header = P.header(p.kicker, p.title, pal, width=S.width, title_size=24, title_lines=2)
            inset, header_gap, min_gap = 0.08, 0.18, 0.04
            if not len(header):
                header_gap = 0
            available = S.height - 2 * inset - header.height - header_gap
            candidate = build((24, 24, 4, 3), compact=True)
            if fits(candidate):
                rows = candidate
        if rows is None:
            raise ValueError("These steps cannot fit at readable type sizes in this safe area.")

        # Centre the WHOLE composition, header included. Short lists get a calm
        # bounded rhythm; tall lists can spend their extra height between steps.
        gap = min(0.90 if tall else 0.56,
                  (available - sum(r.height for r in rows)) / (len(rows) - 1))
        total = header.height + header_gap + sum(r.height for r in rows) + gap * (len(rows) - 1)
        top = S.center[1] + total / 2
        header.shift([S.left, top, 0])
        y = top - header.height - header_gap
        for row in rows:
            delta = [S.left, y - row.get_top()[1], 0]
            row.shift(delta)
            for extra_mob in (row.tick, row.filled):
                if extra_mob is not None:
                    extra_mob.shift(delta)
            row.dot_center = row.marker.get_center().copy() if row.marker is not None else None
            y -= row.height + gap

        if p.style == "timeline":
            for i in range(1, len(rows)):
                start, end = rows[i - 1].dot_center.copy(), rows[i].dot_center.copy()
                start[1] -= rows[i - 1].marker.height / 2 + 0.025
                end[1] += rows[i].marker.height / 2 + 0.025
                rows[i].segment = Line(start, end).set_stroke(pal.muted, width=2.0, opacity=0.4)
        return header, rows

    # -- motion ----------------------------------------------------------------
    def _header_in(self, header):
        m = self.motion
        anims = []
        if header.bar is not None:
            anims.append(GrowFromCenter(header.bar, rate_func=ease_out))
        if header.words is not None:
            anims.append(m.appear(header.words, "rise"))
        if header.title is not None:
            anims.append(m.appear(header.title, "rise"))
        return LaggedStart(*anims, lag_ratio=0.22)

    def _row_in(self, row):
        anims = []
        if row.card is not None:
            anims.append(FadeIn(row.card, scale=0.97, rate_func=ease_out))
        if row.marker is not None:
            anims.append(FadeIn(row.marker, scale=0.5, rate_func=overshoot))
        if row.text is not None:
            anims.append(FadeIn(row.text, shift=RIGHT * 0.16, rate_func=ease_out))
        if row.detail is not None:
            anims.append(FadeIn(row.detail, shift=RIGHT * 0.12, rate_func=ease_out))
        if row.icon is not None:
            anims.append(FadeIn(row.icon, scale=0.7, rate_func=overshoot))
        if row.time is not None:
            anims.append(FadeIn(row.time))
        return LaggedStart(*anims, lag_ratio=0.12)

    def _play(self, header, rows, plan):
        if len(header):
            self.play(self._header_in(header), run_time=plan["intro"])
        last = len(rows) - 1
        for i, row in enumerate(rows):
            anims = [self._row_in(row)]
            if row.segment is not None:
                anims.insert(0, Create(row.segment, rate_func=ease_out))
            self.play(*anims, run_time=plan["enter"])
            self.visible_rows += 1
            if row.tick_anim is not None:
                self.cue("tick", offset=plan["tick"] * 0.7)
                self.play(row.tick_anim, run_time=plan["tick"])
                self.ticked += 1
            else:
                self.cue("pop")
            if i == last:
                self.poster()  # the full list
            if plan["reads"][i] > 0.01:
                self.wait(plan["reads"][i])
