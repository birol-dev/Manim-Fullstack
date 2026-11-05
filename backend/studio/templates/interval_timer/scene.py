"""Real-time named phases. Text changes only at a phase boundary, never every frame."""
import math

from manim import LEFT, PI, TAU, Arc, Circle, FadeOut, Line, ValueTracker, VGroup, linear

from studio.kit import Counter, StudioScene, fit_text, shapes, size_for_height
from studio.kit.layout import Region

from .schema import META, Params, schedule


def clock(value):
    seconds = max(0, math.ceil(value - 1e-6))
    return f"{seconds // 60}:{seconds % 60:02d}"


class Template(StudioScene):
    Params = Params
    META = META
    logo_region = "bottom-right"

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
        console = p.style == "console"
        show_session_track = not console or len(phases) > 1
        readout = main
        radius = min(main.width, main.height) * .43
        stroke = max(9, radius * 9)
        phase_meter = None
        if console:
            u = lay.unit
            display = Region(lay.safe.left, lay.safe.right, phase_box.top, rounds_box.bottom)
            width = min(display.width * .92, display.height * 1.7)
            height = min(display.height, width * .95)
            cx, cy, _ = display.center
            face = shapes.card(width, height, color=theme.surface, radius=2.2 * u,
                               stroke=theme.line, stroke_width=2).move_to(display.center)
            interior = Region(cx - width / 2 + 4 * u, cx + width / 2 - 4 * u,
                              cy + height / 2 - 3 * u, cy - height / 2 + 3 * u)
            phase_box, readout, rounds_box = interior.split_rows([.20, .62, .18 if p.rounds > 1 else .08], gap=1.1 * u)
            meter_width, meter_height = interior.width, 1.2 * u
            meter_start = [interior.left, readout.bottom - u, 0]
            phase_meter = (meter_width, meter_height, meter_start)
            meter = shapes.pill(meter_width, meter_height, color=theme.bg).move_to(meter_start, aligned_edge=LEFT)
            header_rule = Line([interior.left, phase_box.bottom, 0], [interior.right, phase_box.bottom, 0])
            header_rule.set_stroke(theme.line, width=1.3)
            frame = VGroup(face, header_rule, meter)
            track_width = width
            track_left = [cx - width / 2, progress_box.center[1], 0]
        else:
            frame = Circle(radius=radius).set_stroke(theme.line, width=stroke).move_to(main.center)
            track_width = progress_box.width * .90
            track_left = progress_box.point(.05, .30)
        track_height = lay.unit * (1.25 if console else 2)
        track = VGroup()
        if show_session_track:
            track = shapes.pill(track_width, track_height, color=theme.line).move_to(
                [track_left[0] + track_width / 2, track_left[1], 0])
        self.play(motion.appear(title, "drop"), motion.appear(frame, "rise" if console else "fade"), motion.appear(track, "fade"))
        completed, current = 0, None
        for phase_number, (name, seconds, color_index, round_number) in enumerate(phases):
            accent = theme.accent(color_index)
            left = ValueTracker(seconds)
            phase_name = self.words(name or f"Step {color_index + 1}", phase_box, 42, accent)
            round_name = (VGroup() if console and p.rounds == 1 else
                          self.words(f"Round {round_number} / {p.rounds}", rounds_box, 30, theme.muted))
            digit_width, digit_height = (readout.width * .88, readout.height * .68) if console else (radius * 1.55, radius * .55)
            font = "JetBrains Mono" if console and not self.s.brand.font else theme.font
            size = size_for_height(digit_height, font=font) if console else 150
            digits = Counter(seconds, size=size, font=font, color=theme.text,
                             formatter=clock, sample_values=(0, 3599)).move_to(readout.center)
            digits.scale(min(1, digit_width / max(digits.width, .01), digit_height / max(digits.height, .01)))
            digits.move_to(readout.center).track(left)
            digits.add_updater(lambda mob: mob.set_x(readout.center[0]))
            def make_arc(left=left, seconds=seconds, accent=accent):
                fraction = max(0, left.get_value()) / seconds
                if phase_meter is not None:
                    width, height, start = phase_meter
                    return shapes.pill(max(.001, width * fraction), height, color=accent).move_to(
                        start, aligned_edge=LEFT).set_opacity(1 if fraction > 0 else 0)
                return Arc(radius=radius, start_angle=PI / 2, angle=-TAU * max(.00001, fraction),
                    arc_center=main.center).set_stroke(accent, width=stroke, opacity=1 if fraction > 0 else 0)
            arc = make_arc()
            arc.add_updater(lambda mob, make=make_arc: mob.become(make()))
            def make_progress(left=left, seconds=seconds, completed=completed):
                fraction = (completed + seconds - left.get_value()) / total
                width = max(.001, track_width * fraction)
                return shapes.pill(width, track_height, color=theme.accent(1 if console else 0)).move_to(
                    [track_left[0] + width / 2, track_left[1], 0]).set_opacity(1 if fraction > 0 else 0)
            progress = make_progress() if show_session_track else VGroup()
            if show_session_track:
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
        self.play(FadeOut(current), FadeOut(frame), FadeOut(track), run_time=.3)
        message = self.words(p.finish_text or "Finished", main, 76, theme.accent(0))
        self.play(motion.appear(message, "rise"))
        self.target_length = self.elapsed + 2
