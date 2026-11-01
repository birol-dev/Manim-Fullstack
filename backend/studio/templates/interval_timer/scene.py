"""Real-time named phases. Text changes only at a phase boundary, never every frame."""
import math

from manim import PI, TAU, Arc, Circle, FadeOut, ValueTracker, VGroup, linear

from studio.kit import Counter, StudioScene, fit_text, shapes

from .schema import META, Params, schedule


def clock(value):
    seconds = max(0, math.ceil(value - 1e-6))
    return f"{seconds // 60}:{seconds % 60:02d}"


class Template(StudioScene):
    Params = Params
    META = META

    def words(self, source, box, size=36, color=None):
        words = fit_text(source, width=box.width, height=box.height, size=size, min_size=24,
            max_lines=2, font=self.theme.font, color=color or self.theme.text)
        return box.fit(words)

    def build(self):
        self.reserve_logo_band()
        p, theme, lay, motion = self.p, self.theme, self.layout, self.motion
        phases = schedule(p)
        total = sum(seconds for _, seconds, _, _ in phases)
        title_box, phase_box, main, rounds_box, progress_box = lay.safe.split_rows(
            [.13, .12, .56, .09, .10], gap=lay.unit * 2)
        title = self.words(theme.display(p.title), title_box, 48) if p.title else VGroup()
        radius = min(main.width, main.height) * .43
        stroke = max(9, radius * 9)
        ring = Circle(radius=radius).set_stroke(theme.line, width=stroke).move_to(main.center)
        track_width, track_height = progress_box.width * .90, lay.unit * 2
        track_left = progress_box.point(.05, .30)
        track = shapes.pill(track_width, track_height, color=theme.line).move_to(
            [track_left[0] + track_width / 2, track_left[1], 0])
        self.play(motion.appear(title, "drop"), motion.appear(ring, "fade"), motion.appear(track, "fade"))
        completed, current = 0, None
        for phase_number, (name, seconds, color_index, round_number) in enumerate(phases):
            accent = theme.accent(color_index)
            left = ValueTracker(seconds)
            phase_name = self.words(name or f"Step {color_index + 1}", phase_box, 42, accent)
            round_name = self.words(f"Round {round_number} / {p.rounds}", rounds_box, 30, theme.muted)
            digits = Counter(seconds, size=150, font=theme.font, color=theme.text,
                             formatter=clock, sample_values=(0, 3599)).move_to(main.center)
            digits.scale(min(1, radius * 1.55 / max(digits.width, .01), radius * .55 / max(digits.height, .01)))
            digits.move_to(main.center).track(left)
            digits.add_updater(lambda mob: mob.set_x(main.center[0]))
            def make_arc(left=left, seconds=seconds, accent=accent):
                fraction = max(0, left.get_value()) / seconds
                return Arc(radius=radius, start_angle=PI / 2, angle=-TAU * max(.00001, fraction),
                    arc_center=main.center).set_stroke(accent, width=stroke, opacity=1 if fraction > 0 else 0)
            arc = make_arc()
            arc.add_updater(lambda mob, make=make_arc: mob.become(make()))
            def make_progress(left=left, seconds=seconds, completed=completed):
                fraction = (completed + seconds - left.get_value()) / total
                width = max(.001, track_width * fraction)
                return shapes.pill(width, track_height, color=theme.accent(0)).move_to(
                    [track_left[0] + width / 2, track_left[1], 0]).set_opacity(1 if fraction > 0 else 0)
            progress = make_progress()
            progress.add_updater(lambda mob, make=make_progress: mob.become(make()))
            if current is not None:
                self.remove(current)
            current = VGroup(phase_name, round_name, digits, arc, progress)
            self.add(current)
            if phase_number == 0:
                if self.mode == "poster":
                    left.set_value(seconds * .62)
                    self.poster()
                if self.is_peek:
                    span = min(seconds * .38, 4.5)
                    left.set_value(seconds * .62 + span)
                    self.update_mobjects(0)
                    self.play(left.animate.set_value(seconds * .62), run_time=span, rate_func=linear)
                    self.poster()
            if phase_number == len(phases) - 1:
                for number in range(min(3, int(seconds)), 0, -1):
                    self.cue("tick_final", offset=seconds - number)
            self.play(left.animate.set_value(0), run_time=seconds, rate_func=linear)
            current.clear_updaters(recursive=True)
            completed += seconds
        self.cue("finish")
        self.play(FadeOut(current), FadeOut(ring), FadeOut(track), run_time=.3)
        message = self.words(p.finish_text or "Finished", main, 76, theme.accent(0))
        self.play(motion.appear(message, "rise"))
        self.target_length = self.elapsed + 2
