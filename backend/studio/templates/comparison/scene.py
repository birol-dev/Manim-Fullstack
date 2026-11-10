"""Shared-scale numerical comparisons; each measure has its own honest zero baseline."""
from manim import LEFT, ORIGIN, LaggedStart, Line, ValueTracker, VGroup

from studio.kit import Counter, Region, StudioScene, ease_out, fit_text, shapes
from studio.numfmt import format_number

from .schema import META, Params


def inset(box, x0, y0, x1, y1):
    a, b = box.point(x0, y0), box.point(x1, y1)
    return Region(a[0], b[0], a[1], b[1])


class Template(StudioScene):
    Params = Params
    META = META
    logo_region = "bottom-right"

    def words(self, source, box, size=32, color=None, align="center", max_lines=2):
        words = fit_text(source, width=box.width, height=box.height, size=size, min_size=24,
            max_lines=max_lines, font=self.theme.font, color=color or self.theme.text,
            emphasis_color=self.theme.accent(0), align=align)
        return box.fit(words, align=align)

    def build(self):
        self.reserve_logo_band()
        p, theme, lay, motion = self.p, self.theme, self.layout, self.motion
        ledger = p.layout == "ledger"
        align = "left" if ledger else "center"
        weights = [.14, .10, .56, .20]
        if ledger:
            weights = [.13, .10, .61, .16] if lay.is_landscape else [.13, .10, .57, .20]
        title_box, names, body, footer = lay.safe.split_rows(weights, gap=lay.unit * 2)
        fixed, fills, counters, row_groups = VGroup(), [], [], []
        if p.title:
            fixed.add(self.words(theme.display(p.title), title_box, size=48, align=align))
        colors = [theme.accent(0), theme.accent(1)]
        name_boxes = ([inset(names, .04, 0, .46, 1), inset(names, .54, 0, .96, 1)] if ledger
                      else names.split_cols([1, 1], gap=.6))
        for index, (name, box) in enumerate(zip((p.left_label, p.right_label), name_boxes)):
            if ledger:
                fixed.add(Line(box.point(0, 1), box.point(1, 1)).set_stroke(theme.line, width=1.5),
                          Line(box.point(0, 1), box.point(.20, 1)).set_stroke(colors[index], width=4))
            else:
                fixed.add(shapes.card(box.width, box.height, color=theme.surface, radius=.18).move_to(box.center))
            fixed.add(self.words(name or ("First" if index == 0 else "Second"),
                                 inset(box, 0 if ledger else .06, .10, 1 if ledger else .94, .90),
                                 34, colors[index], align=align))
        progress = ValueTracker(0)
        for metric, row in zip(p.metrics, body.split_rows([1] * len(p.metrics), gap=lay.unit * 2.5)):
            details = VGroup()
            if ledger:
                details.add(Line(row.point(0, 1), row.point(1, 1)).set_stroke(theme.line, width=1.2))
            else:
                details.add(shapes.card(row.width, row.height, color=theme.surface, radius=.18).move_to(row.center))
            preference = {"higher": " · higher is better", "lower": " · lower is better"}.get(metric.better, "")
            label_box = inset(row, .04, .04, .96, .28) if ledger else inset(row, .06, .06, .94, .26)
            details.add(self.words((metric.label or "Measure") + preference, label_box,
                                   28, theme.muted, align=align))
            largest = max(metric.left, metric.right, 1e-9)
            for index, value in enumerate((metric.left, metric.right)):
                x0, x1 = (.04, .46) if index == 0 else (.54, .96)
                value_box = inset(row, x0, .33, x1, .70 if p.show_bars else .90)
                other = metric.right if index == 0 else metric.left
                preferred = (metric.better == "higher" and value > other) or (metric.better == "lower" and value < other)
                counter = Counter(value, size=72, font=theme.font, color=colors[index] if preferred else theme.text,
                    anchor="left" if ledger else "center",
                    fmt={"locale": self.s.locale, "decimals": metric.decimals,
                         "prefix": metric.prefix, "suffix": (" " if metric.suffix and metric.suffix[0].isalnum() else "") + metric.suffix},
                    sample_values=(0,))
                value_box.fit(counter, align=align)
                counter.set_value(0)
                counters.append((counter, value, float(value_box.left if ledger else value_box.center[0])))
                if p.show_bars:
                    width, height = row.width * (x1 - x0), min(lay.unit * 2.5, row.height * .11)
                    left = row.point(x0, .84)
                    track = shapes.pill(width, height, color=theme.line).move_to([left[0] + width / 2, left[1], 0])
                    details.add(track)
                    def make_fill(value=value, largest=largest, width=width, height=height, left=left.copy(), color=colors[index]):
                        actual_width = width * value / largest * max(0, progress.get_value())
                        return shapes.pill(max(.001, actual_width), height, color=color).move_to(
                            [left[0] + max(.001, actual_width) / 2, left[1], 0]).set_opacity(1 if actual_width > 1e-6 else 0)
                    fill = make_fill()
                    fill.add_updater(lambda mob, make=make_fill: mob.become(make()))
                    fills.append(fill)
            row_groups.append(details)
        first = p.metrics[0]
        if first.left:
            delta = format_number((first.right - first.left) / first.left * 100,
                                  locale=self.s.locale, decimals=1, sign=True, suffix="%")
        else:
            delta = format_number(first.right - first.left, locale=self.s.locale, decimals=first.decimals,
                                  sign=True, prefix=first.prefix, suffix=first.suffix)
        takeaway = p.takeaway or f"{first.label}: {delta} change"
        takeaway_box, source_box = footer.split_rows([.48, .52] if ledger else [.6, .4], gap=lay.unit)
        fixed.add(self.words(takeaway, takeaway_box, 30, align=align, max_lines=3 if ledger else 2))
        if p.source:
            fixed.add(self.words(p.source, source_box, 24, theme.muted, align=align, max_lines=4 if ledger else 2))
        if ledger:
            self.play(motion.appear(fixed, "fade"), LaggedStart(*[
                motion.appear(row, "rise") for row in row_groups
            ], lag_ratio=.18), *[motion.appear(counter, "fade") for counter, _, _ in counters])
        else:
            fixed.add(*row_groups)
            self.play(motion.appear(fixed, "rise"), *[motion.appear(counter, "fade") for counter, _, _ in counters])
        self.add(*fills)
        animations = [counter.counting(0, value)[1] for counter, value, _ in counters]
        for counter, _, anchor in counters:
            counter.add_updater(lambda mob, x=anchor: mob.set_x(x, direction=LEFT if ledger else ORIGIN))
        self.play(*animations, progress.animate.set_value(1),
                  run_time=min(2.4, max(.8, self.remaining() * .5)), rate_func=ease_out)
        for counter, _, _ in counters:
            counter.clear_updaters()
        for fill in fills:
            fill.clear_updaters()
        self.poster()
