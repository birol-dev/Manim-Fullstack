"""Measured number cards; only cached glyphs change during the count-up."""
from math import ceil

from manim import Line, VGroup

from studio.kit import Counter, Region, StudioScene, ease_out, fit_text, shapes

from .schema import META, Params


class Template(StudioScene):
    Params = Params
    META = META

    def words(self, source, box, *, size=34, color=None):
        words = fit_text(source, width=box.width, height=box.height, size=size, min_size=24,
            max_lines=2, font=self.theme.font, color=color or self.theme.text,
            emphasis_color=self.theme.accent(0))
        return box.fit(words)

    def build(self):
        self.reserve_logo_band()
        p, lay, theme, motion = self.p, self.layout, self.theme, self.motion
        heading, content, footer = lay.safe.split_rows([.16, .76, .08], gap=lay.unit * 2.5)
        fixed = VGroup()
        if p.title:
            fixed.add(self.words(theme.display(p.title), heading, size=50))
        if p.source:
            fixed.add(self.words(p.source, footer, size=25, color=theme.muted))
        count = len(p.figures)
        columns = (count if count <= 3 else 2) if lay.is_landscape else (2 if count == 4 else 1)
        rows = content.split_rows([1] * ceil(count / columns), gap=lay.unit * 3)
        boxes = [box for row in rows for box in row.split_cols([1] * columns, gap=lay.unit * 3)]
        counters, anchors = [], []
        for index, (figure, box) in enumerate(zip(p.figures, boxes)):
            accent = theme.accent(index)
            fixed.add(shapes.card(box.width, box.height, color=theme.surface, radius=.24).move_to(box.center))
            fixed.add(Line(box.point(.08, .04), box.point(.24, .04)).set_stroke(accent, width=5))
            fixed.add(self.words(figure.label or "Number", box_region(box, .08, .08, .92, .24),
                                 size=40 if count == 1 else 30, color=theme.muted))
            value_box = box_region(box, .07, .31, .93, .71 if figure.note else .84)
            counter = Counter(figure.value, size=210 if count == 1 else 104,
                font=theme.font, weight=theme.display_weight, color=accent,
                fmt={"locale": self.s.locale, "prefix": figure.prefix, "suffix": figure.suffix,
                     "decimals": figure.decimals, "compact": figure.compact}, sample_values=(figure.start,))
            if figure.suffix and figure.suffix[0].isalnum():
                counter.fmt["suffix"] = " " + figure.suffix
                counter.set_value(figure.value)
            width, height = counter.width, counter.height
            # Compact figures can be wider mid-count (18.6K) than at either end
            # (18K, 25K). Reserve that space before starting the animation.
            for fraction in (0, .37, .73, 1):
                counter.set_value(figure.start + (figure.value - figure.start) * fraction)
                width, height = max(width, counter.width), max(height, counter.height)
            counter.set_value(figure.start)
            counter.scale(min(1, value_box.width / max(width, .01),
                              value_box.height / max(height, .01))).move_to(value_box.center)
            if figure.note:
                fixed.add(self.words(figure.note, box_region(box, .08, .79, .92, .95), size=28, color=theme.muted))
            counters.append(counter)
            anchors.append(float(value_box.center[0]))
        self.play(motion.appear(fixed, "rise"), *[motion.appear(counter, "fade") for counter in counters])
        animations = [counter.counting(figure.start, figure.value)[1] for counter, figure in zip(counters, p.figures)]
        for counter, anchor in zip(counters, anchors):
            counter.add_updater(lambda mob, x=anchor: mob.set_x(x))
        self.play(*animations, run_time=min(2.6, max(.8, self.remaining() * .5)), rate_func=ease_out)
        for counter in counters:
            counter.clear_updaters()
        self.poster()


def box_region(box, x0, y0, x1, y1):
    a, b = box.point(x0, y0), box.point(x1, y1)
    return Region(a[0], b[0], a[1], b[1])
