"""An accurate goal snapshot, with the true percentage even above 100%."""
from manim import PI, TAU, Arc, Circle, ValueTracker, VGroup

from studio.kit import Counter, Region, StudioScene, ease_out, fit_text, shapes
from studio.numfmt import format_number

from .schema import META, Params


class Template(StudioScene):
    Params = Params
    META = META

    def words(self, source, box, size=34, color=None):
        words = fit_text(source, width=box.width, height=box.height, size=size, min_size=24,
            max_lines=2, font=self.theme.font, color=color or self.theme.text,
            emphasis_color=self.theme.accent(0))
        return box.fit(words)

    def build(self):
        self.reserve_logo_band()
        p, theme, lay, motion = self.p, self.theme, self.layout, self.motion
        heading, main, values, note = lay.safe.split_rows([.16, .61, .12, .11], gap=lay.unit * 2)
        fixed = VGroup()
        accent, progress = theme.accent(0), ValueTracker(0)
        percent = p.current / p.target * 100
        if p.title:
            fixed.add(self.words(theme.display(p.title), heading, 50))
        suffix = (" " if p.suffix and p.suffix[0].isalnum() else "") + p.suffix
        fmt = {"locale": self.s.locale, "decimals": p.decimals, "prefix": p.prefix}
        value_line = (f"{format_number(p.current, **fmt)} / {format_number(p.target, suffix=suffix, **fmt)}"
                      if suffix else f"{format_number(p.current, **fmt)} of {format_number(p.target, **fmt)}")
        fixed.add(self.words(value_line, values, 40))
        if p.note:
            fixed.add(self.words(p.note, note, 28, theme.muted))
        if p.style == "ring":
            radius = min(main.width, main.height) * .45
            stroke = max(10, radius * 10)
            fixed.add(Circle(radius=radius).set_stroke(theme.line, width=stroke).move_to(main.center))
            def make_meter():
                ratio = min(1, max(0, progress.get_value() / 100))
                return Arc(radius=radius, start_angle=PI / 2, angle=-TAU * max(.00001, ratio),
                    arc_center=main.center).set_stroke(accent, width=stroke, opacity=1 if ratio > 0 else 0)
            digits_box = Region(main.center[0] - radius * .80, main.center[0] + radius * .80,
                                main.center[1] + radius * .38, main.center[1] - radius * .18)
            caption_box = Region(main.center[0] - radius * .70, main.center[0] + radius * .70,
                                 main.center[1] - radius * .30, main.center[1] - radius * .58)
        else:
            width, height = main.width * .90, lay.unit * 5
            left = main.point(.05, .68)
            count, gap = 20, lay.unit
            segment_width = (width - gap * (count - 1)) / count
            if p.style == "segments":
                for index in range(count):
                    fixed.add(shapes.card(segment_width, height, color=theme.line, radius=.04)
                        .move_to([left[0] + segment_width / 2 + index * (segment_width + gap), left[1], 0]))
            else:
                fixed.add(shapes.pill(width, height, color=theme.line).move_to([left[0] + width / 2, left[1], 0]))
            def make_meter():
                ratio = min(1, max(0, progress.get_value() / 100))
                if p.style == "segments":
                    group = VGroup()
                    for index in range(count):
                        portion = max(0, min(1, ratio * count - index))
                        filled = max(.001, segment_width * portion)
                        group.add(shapes.card(filled, height, color=accent, radius=.04)
                            .move_to([left[0] + index * (segment_width + gap) + filled / 2, left[1], 0])
                            .set_opacity(1 if portion > 0 else 0))
                    return group
                filled = max(.001, width * ratio)
                return shapes.pill(filled, height, color=accent).move_to(
                    [left[0] + filled / 2, left[1], 0]).set_opacity(1 if ratio > 0 else 0)
            digits_box = Region(main.left, main.right, main.top - main.height * .12, main.top - main.height * .43)
            caption_box = Region(main.left, main.right, main.top - main.height * .46, main.top - main.height * .56)
            fixed.add(self.words("0%", Region(main.left, main.left + 1, left[1] - height, left[1] - height - .35),
                                 24, theme.muted))
            fixed.add(self.words("100%", Region(main.right - 1, main.right, left[1] - height, left[1] - height - .35),
                                 24, theme.muted))
        counter = Counter(percent, size=150, font=theme.font, weight=theme.display_weight,
                          color=accent, fmt={"locale": self.s.locale, "suffix": "%", "compact": percent > 9999},
                          sample_values=(0,))
        digits_box.fit(counter)
        counter.set_value(0)
        fixed.add(self.words("of target", caption_box, 28, theme.muted))
        meter = make_meter()
        meter.add_updater(lambda mob: mob.become(make_meter()))
        self.play(motion.appear(fixed, "rise"), motion.appear(counter, "fade"))
        self.add(meter)
        counter.track(progress)
        counter.add_updater(lambda mob: mob.set_x(digits_box.center[0]))
        self.play(progress.animate.set_value(percent), run_time=min(2.4, max(.8, self.remaining() * .5)), rate_func=ease_out)
        counter.clear_updaters()
        meter.clear_updaters()
        self.poster()
