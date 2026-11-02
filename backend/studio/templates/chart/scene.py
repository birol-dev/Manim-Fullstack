"""Directly labelled charts, with measured legends only for crowded labels."""
from __future__ import annotations

from math import cos, pi, sin

import numpy as np
from manim import Circle, Create, FadeIn, Line, ManimColor, Rectangle, Sector, VGroup, interpolate_color

from studio.kit import Counter, StudioScene, ease_out, label
from studio.kit.layout import Region

from .parts import MIN_TYPE, ink_on, slice_colors, text, visible_segments
from .schema import META, Params


class Template(StudioScene):
    Params = Params
    META = META
    logo_region = "top-right"
    logo_height = 6

    def _counter(self, value, size=32, **options):
        return Counter(value, size=size, font=self.theme.font, color=self.theme.text,
                       fmt={"locale": self.s.locale, "decimals": self.p.decimals}, **options)

    def _compose(self):
        if not getattr(self, "_logo_reserved", False):
            self.reserve_logo_band()
            self._logo_reserved = True
        S, theme, p, u = self.layout.safe, self.theme, self.p, self.layout.unit
        self.accent = p.accent or theme.accent(0)
        if p.chart_type == "pie":
            self.colors = slice_colors(self.accent, len(p.values), theme.dark)
            # Zero rows keep their key, but must not leave two similar shades
            # touching after their invisible slices are removed.
            visible = iter(slice_colors(self.accent, sum(row.value > 0 for row in p.values), theme.dark))
            self.colors = [next(visible) if row.value > 0 else color
                           for row, color in zip(p.values, self.colors)]
        else:
            tint = str(interpolate_color(ManimColor(self.accent), ManimColor(theme.bg), .28))
            peak = max(row.value for row in p.values)
            self.colors = [self.accent if row.value == peak else tint for row in p.values]
        self.heading = text(theme.display(p.title), width=S.width, height=S.height * .28,
            size=48, font=theme.font, weight=theme.display_weight, color=theme.text,
            emphasis_color=self.accent, align="left")
        self.heading.move_to([S.left + self.heading.width / 2, S.top - self.heading.height / 2, 0])
        content = Region(S.left, S.right, self.heading.get_bottom()[1] - 5 * u, S.bottom)
        self.entries, self.counters, self.pages, self.axis_labels = [], [], [], []
        self.percent_labels = []
        self.legend_side = p.chart_type == "pie" and self.layout.is_landscape
        self.uses_legend = p.chart_type == "pie"
        if not self.uses_legend:
            self.axis_labels = self._direct_labels(content)
            self.uses_legend = not self.axis_labels
        if self.uses_legend:
            self.plot_region = self._legend(content)
        else:
            line_h = max(words.height for words in self.axis_labels)
            rows = 1 + max(getattr(words, "chart_row", 0) for words in self.axis_labels)
            label_h = rows * line_h + (rows - 1) * .14
            self.plot_region = Region(content.left, content.right, content.top,
                                      content.bottom + label_h + 3 * u)
            slot = content.width / len(p.values)
            for i, words in enumerate(self.axis_labels):
                x = np.clip(content.left + (i + .5) * slot,
                            content.left + words.width / 2, content.right - words.width / 2)
                words.move_to([x, content.bottom + label_h - words.height / 2
                               - getattr(words, "chart_row", 0) * (line_h + .14), 0])
        self.axes, self.marks = self._drawing(self.plot_region)
        return self.heading, self.entries, self.axes, self.marks

    def _direct_labels(self, R):
        """Try wrapping at every readable size before using a key."""
        slot = R.width / len(self.p.values)
        # A second baseline lets whole month names stay readable in tall video.
        # Try this before splitting any word, still keeping each label below its point.
        for break_words, stagger in ((False, False), (False, True), (True, False)):
            for size in range(28 if stagger else 32, MIN_TYPE - 1, -2):
                try:
                    words = [text(row.label, width=slot * (2 if stagger else 1) - .14,
                                  height=.5 if stagger else min(1.25, R.height * .24),
                                  size=size, min_size=size, break_words=break_words,
                                  font=self.theme.font, color=self.theme.text) for row in self.p.values]
                except ValueError:
                    continue
                if stagger:
                    for i, word in enumerate(words):
                        word.chart_row = i % 2
                return words
        return []

    def _legend(self, R):
        u, theme = self.layout.unit, self.theme
        inline = self.p.chart_type == "pie" and len(self.p.values) <= 6
        if self.legend_side:
            key = Region(R.right - R.width * .35, R.right, R.top, R.bottom)
            plot = Region(R.left, key.left - 5 * u, R.top, R.bottom)
            cols, max_h = 1, R.height
        else:
            key = R
            plot = None
            cols, max_h = (1 if inline else 2), R.height * .48
        gap = 4 * u
        cw = (key.width - (cols - 1) * gap) / cols
        marker_w = .32 if self.p.chart_type == "pie" else .56
        marker_gap = .20
        entries = []
        for i, row in enumerate(self.p.values):
            number = self._counter(row.value, size=28, anchor="left")
            while number.width > cw - marker_w - marker_gap and number.size > MIN_TYPE:
                number = self._counter(row.value, size=number.size - 2, anchor="left")
            label_w = cw - marker_w - marker_gap - (number.width + .25 if inline else 0)
            words = text(row.label, width=label_w, size=28,
                         height=max_h - .55, font=theme.font, color=theme.text, align="left")
            if inline:
                number.move_to([words.get_left()[0] + label_w + .25 + number.width / 2,
                                words.lines[0].get_center()[1], 0])
            else:
                number.next_to(words, np.array([0, -1, 0]), aligned_edge=np.array([-1, 0, 0]), buff=.12)
            if self.p.chart_type == "pie":
                marker = Rectangle(width=.32, height=.32).set_fill(self.colors[i], 1).set_stroke(width=0)
            else:
                badge = Circle(radius=marker_w / 2).set_fill(self.accent, 1).set_stroke(width=0)
                index = label(str(i + 1), size=MIN_TYPE, font=theme.font, color=ink_on(self.accent))
                badge.scale(max(1, (index.width + .14) / marker_w))
                marker = VGroup(badge, index)
            marker.move_to([words.get_left()[0] - marker_gap - marker.width / 2,
                            words.lines[0].get_center()[1], 0])
            entry = VGroup(words, number, marker)
            entry.words, entry.number, entry.marker = words, number, marker
            entries.append(entry)
        # Crowded keys page at real type sizes while the chart remains visible.
        for page_size in range(len(entries), 0, -1):
            pages = [entries[i:i + page_size] for i in range(0, len(entries), page_size)]
            heights = [[max(e.height for e in page[r:r + cols])
                        for r in range(0, len(page), cols)] for page in pages]
            key_h = max(sum(h) + max(0, len(h) - 1) * .22 for h in heights)
            if key_h <= max_h:
                break
        if self.legend_side:
            key_top = (R.top + R.bottom + key_h) / 2
            self.legend_region = Region(key.left, key.right, key_top, key_top - key_h)
        else:
            key_top = R.bottom + key_h
            self.legend_region = Region(key.left, key.right, key_top, R.bottom)
            plot = Region(R.left, R.right, R.top, key_top + (4 if inline else 8) * u)
        for page, row_heights in zip(pages, heights):
            y = key_top
            for r, row_h in enumerate(row_heights):
                for c, entry in enumerate(page[r * cols:(r + 1) * cols]):
                    entry.shift([key.left + c * (cw + gap) - entry.get_left()[0],
                                 y - entry.get_top()[1], 0])
                y -= row_h + .22
        self.pages, self.entries = pages, entries
        self.counters = [entry.number for entry in entries]
        return plot

    def _drawing(self, R):
        if self.p.chart_type == "pie":
            return self._pie(R)
        return self._cartesian(R)

    def _pie(self, R):
        radius = min(R.width, R.height) * .49
        self.pie_radius, self.pie_center = radius, R.center
        total, angle, marks = sum(row.value for row in self.p.values), pi / 2, []
        for i, row in enumerate(self.p.values):
            share = row.value / total
            if share == 0:
                marks.append(VGroup())
                continue
            sector = Sector(outer_radius=radius, start_angle=angle, angle=-2 * pi * share,
                            fill_opacity=1, fill_color=self.colors[i],
                            stroke_color=self.theme.bg, stroke_width=3)
            sector.move_arc_center_to(R.center)
            mark = VGroup(sector)
            if share >= .08:
                percent = label(f"{share:.0%}", size=32, font=self.theme.font,
                                weight="BOLD", color=ink_on(self.colors[i]))
                mid = angle - pi * share
                distance = 0 if share == 1 else radius * .62
                room = radius if share == 1 else min(distance * sin(min(pi * share, pi / 2)), radius - distance)
                if np.hypot(percent.width, percent.height) / 2 + .10 < room:
                    percent.move_to(R.center + distance * np.array([cos(mid), sin(mid), 0]))
                    percent.slice_index = i
                    self.percent_labels.append(percent)
                    mark.add(percent)
            marks.append(mark)
            angle -= 2 * pi * share
        return VGroup(), marks

    def _cartesian(self, R):
        values, theme = self.p.values, self.theme
        n, axes, marks = len(values), VGroup(), []
        low, high = min(row.value for row in values), max(row.value for row in values)
        if self.p.chart_type == "bars" or low <= 0 <= high or low <= (high - low) * .2:
            low, high = min(0, low), max(0, high)
        else:
            pad = max((high - low) * .08, abs(high) * .03, .01)
            low, high = low - pad, high + pad
        if low == high:
            high = low + 1
        self.y_range = low, high
        slot = R.width / n
        if not self.uses_legend:
            self.counters = []
            for row in values:
                for size in range(32, MIN_TYPE - 1, -2):
                    number = self._counter(row.value, size=size)
                    if number.width <= slot - .14:
                        break
                self.counters.append(number)
        number_h = max((number.height for number in self.counters), default=.35)
        top = R.top - (number_h + .32 if not self.uses_legend else .12)
        bottom = R.bottom + (number_h + .22 if low < 0 and not self.uses_legend else .12)
        y_for = lambda value: bottom + (value - low) / (high - low) * (top - bottom)
        zero = y_for(0) if low <= 0 <= high else bottom
        self.zero_y = zero
        self.baseline = Line([R.left, zero, 0], [R.right, zero, 0]).set_stroke(theme.muted, width=1.5)
        axes.add(self.baseline)
        for fraction in (.25, .5, .75, 1):
            y = bottom + fraction * (top - bottom)
            axes.add(Line([R.left, y, 0], [R.right, y, 0]).set_stroke(theme.line, width=1, opacity=.5))
        previous = None
        self.points, self.value_directions = [], []
        for i, row in enumerate(values):
            x, y = R.left + (i + .5) * slot, y_for(row.value)
            point = np.array([x, y, 0])
            self.points.append(point)
            if self.uses_legend:
                index = label(str(i + 1), size=MIN_TYPE, font=theme.font, color=theme.muted)
                index.move_to([x, R.bottom - .16 - index.height / 2, 0])
                axes.add(index)
            if self.p.chart_type == "bars":
                mark = Rectangle(width=slot * .62, height=max(abs(y - zero), .025))
                mark.set_fill(self.colors[i], 1).set_stroke(width=0).move_to([x, (y + zero) / 2, 0])
                mark.grow_from = np.array([x, zero, 0])
            else:
                dot = Circle(radius=min(.085, slot * .12)).set_fill(self.accent, 1)
                dot.set_stroke(theme.bg, width=1.5).move_to(point)
                mark = VGroup(dot)
                if previous is not None:
                    mark.add_to_back(Line(previous, point).set_stroke(self.accent, width=5))
            marks.append(mark)
            if not self.uses_legend:
                direction = -1 if self.p.chart_type == "bars" and row.value < 0 else 1
                self.value_directions.append(direction)
                number, words = self.counters[i], self.axis_labels[i]
                self._place_value(number, mark, direction)
                entry = VGroup(words, number)
                entry.words, entry.number = words, number
                self.entries.append(entry)
            previous = point
        if not self.uses_legend:
            self.pages = [self.entries]
        self.line_segments = []
        if self.p.chart_type == "line":
            for i, mark in enumerate(marks[1:], start=1):
                mark.remove(mark[0])
                segments = [Line(a, b).set_stroke(self.accent, width=5) for a, b in visible_segments(
                    self.points[i - 1], self.points[i], [] if self.uses_legend else self.counters)]
                self.line_segments.extend(segments)
                mark.add_to_back(VGroup(*segments))
        return axes, marks

    def _place_value(self, number, mark, direction):
        tip = mark.get_top() if direction > 0 else mark.get_bottom()
        if self.p.chart_type == "line":
            tip = mark[-1].get_top()
        number.move_to([tip[0], tip[1] + direction * (.15 + number.height / 2), 0])

    def build(self):
        self._compose()
        m = self.motion
        reads = [m.reading_time(row.label, minimum=.65) for row in self.p.values]
        intro, enter, hold = m.t(.7), m.t(.6), 1.5
        ending = m.exit + .15 if self.s.ending == "fade" else 0
        natural = intro + sum(enter + read for read in reads) + hold + ending
        if self.s.length is None:
            self.target_length = min(META.max_length, max(META.min_length, natural))
        factor = min(1, max(0, self.target_length - ending) / (natural - ending))
        self.play(FadeIn(self.heading), FadeIn(self.axes), run_time=intro * factor)
        visible = []
        page_starts = {id(page[0]): page for page in self.pages}
        for i, (entry, number, mark, row, read) in enumerate(zip(
                self.entries, self.counters, self.marks, self.p.values, reads)):
            if id(entry) in page_starts and visible:
                self.remove(*visible)
                visible = []
            visible.append(entry)
            number.set_value(0)
            self.play(FadeIn(entry), run_time=enter * .35 * factor)
            tracker, counting = number.counting(0, row.value)
            self.add(tracker)
            if self.p.chart_type == "bars":
                full = mark.copy()
                mark.stretch(.001, 1, about_point=mark.grow_from)
                drawing = mark.animate.become(full)
            else:
                drawing = Create(mark)
            if not self.uses_legend:
                direction = self.value_directions[i]
                number.add_updater(lambda mob, mark=mark, direction=direction:
                                   self._place_value(mob, mark, direction))
            self.cue("tick")
            self.play(drawing, counting, run_time=(enter * .65 + read) * factor, rate_func=ease_out)
            number.clear_updaters()
            number.set_value(row.value)
            if not self.uses_legend:
                self._place_value(number, mark, self.value_directions[i])
            self.remove(tracker)
        self.poster()
