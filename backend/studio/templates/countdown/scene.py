import math

from manim import LEFT, PI, TAU, Arc, Circle, FadeIn, FadeOut, ValueTracker, VGroup, there_and_back

from studio.kit import Counter, StudioScene, fit_text, shapes, size_for_height

from .schema import META, Params


def clock(value: float) -> str:
    """Whole seconds left, rounded up, as m:ss (so the display reaches 0:00 exactly at the end)."""
    total = max(0, math.ceil(value - 1e-6))
    return f"{total // 60}:{total % 60:02d}"


class Template(StudioScene):
    Params = Params
    META = META

    def build(self):
        p, theme, lay, m = self.p, self.theme, self.layout, self.motion
        accent = p.accent or theme.accent(0)
        warn = theme.accent(3)
        seconds = float(p.seconds)
        warn_at = 10.0 if (p.warn_last and seconds > 12) else 0.0

        has_title = bool(p.title)
        has_note = bool(p.subtitle)
        title_weight = (0.22 if lay.is_portrait else 0.17) if has_title else 0.001
        rows = lay.safe.split_rows([title_weight, 0.7, 0.12 if has_note else 0.001], gap=lay.unit * 2)
        title_box, main_box, note_box = rows

        title = fit_text(theme.display(p.title), width=title_box.width, height=title_box.height,
                         size=72 if lay.is_portrait else 56, min_size=32, max_lines=2, font=theme.font, weight=theme.display_weight,
                         color=theme.text) if has_title else None
        note = fit_text(p.subtitle, width=note_box.width, height=note_box.height, size=34, max_lines=1,
                        font=theme.font, color=theme.muted) if has_note else None
        if title is not None:
            title_box.fit(title, align="center")
        if note is not None:
            note_box.fit(note, align="center")
        self._confetti_foreground = [mob for mob in (title, note) if mob is not None]

        left = ValueTracker(seconds)
        intro = []
        if title is not None:
            intro.append(m.appear(title, "drop"))

        if p.style == "big" and seconds <= 20:
            self._big_numbers(main_box, title, note, seconds, accent)
            return

        if p.style == "ring":
            radius = min(main_box.width, main_box.height) / 2 * 0.92
            stroke = max(radius * 9, 6)
            track = Circle(radius=radius).set_stroke(theme.line, width=stroke).move_to(main_box.center)

            def make_arc():
                frac = max(left.get_value(), 0) / seconds
                arc = Arc(radius=radius, start_angle=PI / 2, angle=-TAU * max(frac, 1e-4),
                          arc_center=main_box.center)
                return arc.set_stroke(accent if left.get_value() > warn_at or not warn_at else warn, width=stroke)

            arc = make_arc()
            arc.add_updater(lambda a: a.become(make_arc()))
            digit_h = radius * 0.42
            meter = VGroup(track, arc)
            center = main_box.center
        else:  # bar, or "big" with more than 20 s (big digits above a thin bar)
            bar_w = main_box.width * 0.92
            bar_h = lay.unit * (5 if p.style == "bar" else 2.4)
            bar_y = main_box.bottom + main_box.height * 0.28
            track = shapes.pill(bar_w, bar_h, color=theme.line).move_to([main_box.center[0], bar_y, 0])

            def make_fill():
                frac = max(left.get_value(), 0) / seconds
                w = max(bar_w * frac, bar_h)
                fill = shapes.pill(w, bar_h, color=accent if left.get_value() > warn_at or not warn_at else warn)
                return fill.move_to(track.get_left(), aligned_edge=LEFT)

            arc = make_fill()
            arc.add_updater(lambda f: f.become(make_fill()))
            # m:ss is about four digit-heights wide, so narrow frames are limited by width
            digit_h = min(main_box.height * (0.34 if p.style == "bar" else 0.48), main_box.width * 0.22)
            meter = VGroup(track, arc)
            center = [main_box.center[0], (bar_y + bar_h / 2 + main_box.top) / 2, 0]

        size = size_for_height(digit_h, font=theme.font, weight="BOLD")
        sample = (seconds, 3599)
        digits = Counter(seconds, size=size, font=theme.font, weight="BOLD", color=theme.text, formatter=clock,
                         sample_values=sample).move_to(center)
        warn_digits = Counter(min(seconds, warn_at), size=size, font=theme.font, weight="BOLD", color=warn,
                              formatter=clock, sample_values=sample).move_to(center) if warn_at else None

        self.add(track)
        intro += [m.appear(track, "fade"), FadeIn(arc, run_time=m.enter), m.appear(digits, "pop")]
        if note is not None:
            intro.append(m.appear(note, "rise"))
        self.play(*intro)
        digits.track(left)

        if self.mode == "poster":
            left.set_value(seconds * 0.62)
            self.poster()

        self.play(left.animate(rate_func=lambda t: t).set_value(warn_at), run_time=seconds - warn_at)
        if warn_at:
            digits.clear_updaters()
            warn_digits.track(left)
            self.remove(digits)
            self.add(warn_digits)
            for n in range(int(warn_at), 0, -1):
                self.play(left.animate(rate_func=lambda t: t).set_value(n - 1),
                          warn_digits.animate(rate_func=there_and_back).scale(1.06), run_time=1)
            digits = warn_digits

        arc.clear_updaters()
        digits.clear_updaters()
        self._finish_card(main_box, accent, [meter, digits])

    def _finish_card(self, box, accent, outgoing):
        p, theme, m = self.p, self.theme, self.motion
        message = fit_text(theme.display(p.finish_text), width=box.width * 0.9, height=box.height * 0.5, size=200,
                           max_lines=2, font=theme.font, weight=theme.display_weight, color=accent)
        message.move_to(box.center)
        self.play(*[FadeOut(o, run_time=m.exit) for o in outgoing])
        anims = [m.appear(message, "pop", run_time=m.t(0.7))]
        if p.confetti:
            confetti = shapes.Confetti(self.layout.frame_width, self.layout.frame_height, theme.accents)
            # The same clearance rule applies to the finish card and its labels.
            self.keep_particles_clear(confetti, [*self._confetti_foreground, message])
            self.add(confetti)
            anims.append(confetti.fall(run_time=3))
        self.play(*anims)
        self.target_length = self.elapsed + 2.5

    def _big_numbers(self, box, title, note, seconds, accent):
        theme, m = self.theme, self.motion
        intro = [m.appear(o, "drop") for o in (title, note) if o is not None]
        if intro:
            self.play(*intro)
        height = min(box.height * 0.8, box.width * 0.62)
        size = size_for_height(height, font=theme.font, weight=theme.display_weight)
        count = int(math.ceil(seconds))
        current = None
        for n in range(count, 0, -1):
            number = Counter(n, size=size, font=theme.font, weight=theme.display_weight,
                             color=accent if n > 3 else theme.accent(3), formatter=lambda v: str(int(v)),
                             sample_values=(n,)).move_to(box.center)
            anims = [FadeIn(number, scale=1.5, run_time=0.35, rate_func=lambda t: 1 - (1 - t) ** 3)]
            if current is not None:
                anims.append(FadeOut(current, scale=0.7, run_time=0.25))
            self.play(*anims)
            if n == max(count - 2, 1) and self.mode == "poster":
                self.poster()
            self.wait(max(0.0, 1 - 0.35))
            current = number
        self._finish_card(box, accent, [current])
