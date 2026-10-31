import math
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
from manim import (
    DOWN,
    UP,
    PI,
    TAU,
    Arc,
    CapStyleType,
    Circle,
    FadeIn,
    FadeOut,
    ValueTracker,
    VGroup,
    linear,
    there_and_back,
)

from studio.kit import Counter, StudioScene, ease_in_out, ease_out, fit_text, label, overshoot, shapes, size_for_height

from . import helpers as H
from .planner import plan_layout
from .schema import META, Params

LETTERS = "ABCD"
OPTION_WEIGHT = "SEMIBOLD"


def seconds_left(value: float) -> str:
    """Whole seconds left, rounded up, so the ring shows 1 until the very end."""
    return str(max(0, math.ceil(value - 1e-6)))


class Template(StudioScene):
    Params = Params
    META = META
    logo_region = "bottom-left"
    logo_reserved_aspects = ("16:9", "9:16", "1:1", "4:5")

    # -- build ----------------------------------------------------------------------
    def build(self):
        if self.s.aspect in self.logo_reserved_aspects:
            self.reserve_logo_band()  # the explanation panel fills the bottom zone otherwise
        p, theme, lay, m = self.p, self.theme, self.layout, self.motion
        bg = (self.s.background.color or theme.bg) if self.s.background.kind in ("solid", "gradient") else theme.bg
        pal = H.palette(theme, bg)
        R = lay.safe
        think = int(p.think_seconds)
        correct = int(p.correct) - 1
        options = [o.text for o in p.options]
        question_text = theme.display(" ".join(p.question.split()))
        explanation = " ".join(p.explanation.split())

        plan = plan_layout(lay, R, theme, question=question_text, options=options, explanation=explanation,
                             has_label=bool(p.label))
        separate_explanation = bool(explanation and plan.overflow > 0)
        if separate_explanation:
            # Long answers need the thinking screen's height. Give the explanation
            # its own reveal screen rather than pushing answers below the frame.
            plan = plan_layout(lay, R, theme, question=question_text, options=options, explanation="",
                               has_label=bool(p.label))
        cx = float(R.center[0])

        self._decorate(pal)

        # label pill on top; the timer ring lives in the bottom zone (the explanation takes it over later)
        pill = None
        if p.label:
            pill = self._pill(theme.display(" ".join(p.label.split())), pal, R)
            pill.move_to([cx, plan.head_y, 0])
        ring_center = np.array([cx, plan.bottom_y, 0.0])

        question = fit_text(question_text, width=plan.q_width, size=plan.q_size, min_size=plan.q_size, max_lines=8,
                            font=theme.font, weight=theme.display_weight, color=theme.text, line_spacing=1.0)
        question.move_to([cx, plan.q_center_y, 0])

        cards = self._cards(options, plan, pal, R)
        panel = None
        if explanation:  # added now, invisible, so that the check badge can travel over it later
            explanation_plan = plan
            if separate_explanation:
                explanation_plan = replace(plan, bottom_y=R.center[1], e_h=R.height * 0.65,
                                           e_lines=8, e_size=32)
            panel = self._explanation(explanation, explanation_plan, pal, cx)
            panel.group.set_opacity(0).shift(DOWN * lay.unit * 3)
            self.add(panel.group)

        # the timer
        left = ValueTracker(think)
        warn_n = 3 if think >= 5 else 0
        ring = self._ring(plan, pal, ring_center, think, left, warn_n)

        # -- 1. label and question
        intro = [m.appear(question, "rise")]
        if pill is not None:
            intro.append(m.appear(pill, "drop"))
        self.play(*intro)

        # -- 2. answers stagger in, the ring pops in
        self.play(
            m.appear_each([c.group for c in cards], "rise", lag=m.stagger * 1.3),
            m.appear(ring.group, "pop", delay=m.t(0.25)),
        )
        ring.start(left)

        # -- 3. thinking time (the poster is taken here, with the timer part-way)
        if self.mode == "poster":
            left.set_value(think * 0.55)
            self.poster()
        if self.is_peek:
            self.play(left.animate(rate_func=linear).set_value(think * 0.55), run_time=think * 0.45)
            self.poster()

        main = think - warn_n
        for n in range(min(3, think), 0, -1):
            self.cue("tick", offset=think - n)
        if main > 0:
            self.play(left.animate(rate_func=linear).set_value(warn_n), run_time=main)
        for n in range(warn_n, 0, -1):
            self.play(left.animate(rate_func=linear).set_value(n - 1),
                      ring.digits.animate(rate_func=there_and_back).scale(1.12), run_time=1)
        ring.stop()

        # -- 4. reveal: the ring turns into a check, the right answer lights up, the others dim
        badge = self._badge(plan, pal).move_to(ring_center)
        self.cue("correct")
        winner = cards[correct]
        anims = [FadeOut(ring.group, scale=0.8, run_time=m.t(0.4)),
                 FadeIn(badge, scale=0.4, rate_func=overshoot, run_time=m.t(0.6))]
        for i, card in enumerate(cards):
            anims += self._reveal(card, pal, correct=(i == correct))
        tick = H.check_mark(plan.slot_d * 0.62, pal.success, width=max(plan.slot_d * 8.5, 5))
        tick.move_to(winner.slot.get_center())
        anims.append(FadeIn(tick, scale=0.4, rate_func=overshoot, run_time=m.t(0.6)))
        self.play(*anims, run_time=m.t(0.6))
        self.remove(tick)
        winner.group.add(tick)
        self.add(winner.group)

        # -- 5. explanation: the badge settles into its panel, with a small pulse on the right answer
        finale = [winner.group.animate(rate_func=there_and_back, run_time=m.t(0.4)).scale(1.025)]
        if panel is not None:
            if separate_explanation:
                self.wait(0.8)
                self.play(*[FadeOut(obj) for obj in [question, *[c.group for c in cards], pill]
                            if obj is not None], run_time=m.exit)
                # Individual card animations can leave glyphs as scene roots.
                # Start the explanation page with just its panel, badge and the brand logo.
                self.remove(*[mob for mob in self.content() if mob is not self.brand_logo])
                self.add(panel.group, badge)
                finale = []
            finale.append(panel.group.animate(rate_func=ease_out, run_time=m.enter).shift(UP * lay.unit * 3)
                          .set_opacity(1))
            finale.append(badge.animate(rate_func=ease_in_out, run_time=m.t(0.7))
                          .scale(plan.badge_d / plan.ring).move_to(panel.badge_at))
        self.play(*finale)

        hold = m.reading_time(explanation, minimum=2.0) if explanation else 3.0
        self.wait(hold)
        self.target_length = self.elapsed + (m.exit if self.s.ending == "fade" else 0.0)

    # -- pieces ---------------------------------------------------------------------
    def _decorate(self, pal):
        """Soft background shapes in two corners; skipped on transparent exports."""
        if self.s.background.kind == "transparent":
            return
        lay, theme = self.layout, self.theme
        w, h, short = lay.frame_width, lay.frame_height, lay.short
        alpha = 0.10 if theme.dark else 0.09
        big = Circle(radius=short * 0.46).set_fill(pal.primary, alpha).set_stroke(width=0)
        big.move_to([-w / 2 + short * 0.04, h / 2 - short * 0.02, 0])
        small = Circle(radius=short * 0.30).set_fill(pal.success, alpha * 0.8).set_stroke(width=0)
        small.move_to([w / 2 - short * 0.02, -h / 2 + short * 0.05, 0])
        self.add(big, small)

    def _pill(self, text, pal, R):
        unit = self.layout.unit
        pad = unit * 3.6
        txt = label(text, size=28, weight="BOLD", color=pal.on_primary, max_width=R.width - 2 * pad)
        pill = shapes.pill(txt.width + 2 * pad, unit * 6.6, color=pal.primary)
        txt.move_to(pill.get_center())
        return VGroup(pill, txt)

    def _ring(self, plan, pal, center, think, left, warn_n):
        """Timer ring: a disc with seconds in the middle and an arc that empties."""
        theme = self.theme
        d = plan.ring
        thick = d * 0.10
        rc = d / 2 - thick / 2
        width = thick * 100
        disc = Circle(radius=rc).set_fill(pal.surface, 1).set_stroke(width=0).move_to(center)
        track = Circle(radius=rc).set_stroke(pal.line, width=width).move_to(center)

        def make_arc():
            value = left.get_value()
            color = pal.warn if (warn_n and value <= warn_n) else pal.primary
            return Arc(radius=rc, start_angle=PI / 2, angle=-TAU * max(value / think, 1e-3), arc_center=center,
                       color=color, stroke_width=width, cap_style=CapStyleType.ROUND)

        arc = make_arc()
        size = size_for_height(d * 0.30, font=theme.font, weight="BOLD")
        digits = Counter(think, size=size, font=theme.font, weight="BOLD", color=pal.text, formatter=seconds_left,
                         sample_values=(think,)).move_to(center)
        group = VGroup(disc, track, arc, digits)

        def start(tracker):
            arc.add_updater(lambda a: a.become(make_arc()))
            digits.track(tracker)

        def stop():
            arc.clear_updaters()
            digits.clear_updaters()

        return SimpleNamespace(group=group, arc=arc, digits=digits, start=start, stop=stop)

    def _badge(self, plan, pal):
        d = plan.ring
        disc = Circle(radius=d / 2).set_fill(pal.success, 1).set_stroke(width=0)
        tick = H.check_mark(d * 0.46, pal.ink, width=d * 7.5)
        return VGroup(disc, tick)

    def _cards(self, options, plan, pal, R):
        cards = []
        n = len(options)
        for i, text in enumerate(options):
            row, col = divmod(i, plan.cols)
            in_row = min(plan.cols, n - row * plan.cols)
            row_w = in_row * plan.card_w + (in_row - 1) * plan.gap
            x0 = R.center[0] - row_w / 2 + plan.card_w / 2
            x = x0 + col * (plan.card_w + plan.gap)
            y = plan.opt_top - plan.card_h / 2 - row * (plan.card_h + plan.gap)
            cards.append(self._card(i, text, plan, pal, np.array([x, y, 0.0])))
        return cards

    def _card(self, index, text, plan, pal, center):
        theme, unit = self.theme, self.layout.unit
        w, h = plan.card_w, plan.card_h
        punchy = theme.display_weight == "HEAVY"  # the pop theme: hard edges, black outlines
        radius = min(theme.radius * 1.15, h / 2)
        depth = unit * (1.8 if punchy else 1.1)
        shadow = shapes.card(w, h, color=pal.line, radius=radius).shift(DOWN * depth)
        face = shapes.card(w, h, color=pal.surface, radius=radius, stroke=pal.line,
                           stroke_width=6 if punchy else 2.5)
        sx = -w / 2 + plan.pad_l + plan.slot_d / 2
        slot = Circle(radius=plan.slot_d / 2).move_to([sx, 0, 0])
        letter = None
        if self.p.show_letters:
            slot.set_fill(pal.primary, 1).set_stroke(width=0)
            letter = label(LETTERS[index], size=plan.letter_size, weight="BOLD", color=pal.on_primary)
            letter.move_to([sx, 0, 0])
        else:  # an empty "radio" ring that fills with the check at the reveal
            slot.set_fill(pal.surface, 1).set_stroke(pal.muted, width=3.5)
        body = fit_text(text, width=plan.text_w, size=plan.opt_size, min_size=plan.opt_size,
                        max_lines=plan.opt_lines, font=theme.font, weight=OPTION_WEIGHT, color=pal.text,
                        align="left", line_spacing=1.0)
        lift = H.baseline_shift(text, plan.opt_size, theme.font, OPTION_WEIGHT) if len(body.lines) == 1 else 0.0
        body.move_to([w / 2 - plan.pad_r - plan.text_w + body.width / 2, lift, 0])
        parts = [shadow, face, slot] + ([letter] if letter is not None else []) + [body]
        group = VGroup(*parts)
        group.shift(center - face.get_center())
        return SimpleNamespace(group=group, shadow=shadow, face=face, slot=slot, letter=letter, body=body,
                               radio=letter is None)

    def _reveal(self, card, pal, correct):
        """Animations for one card at the reveal: the right answer lights up, the others dim."""
        if correct:
            anims = [
                card.face.animate.set_fill(pal.success).set_stroke(pal.success_deep),
                card.shadow.animate.set_fill(pal.success_deep),
                card.slot.animate.set_fill(pal.ink).set_stroke(pal.ink),
                card.body.animate.set_color(pal.ink),
            ]
            if card.letter is not None:
                anims.append(card.letter.animate.set_opacity(0))
            return anims
        dim = pal.dim
        anims = [
            card.face.animate.set_fill(dim(pal.surface)).set_stroke(dim(pal.line)),
            card.shadow.animate.set_fill(dim(pal.line)),
            card.body.animate.set_color(dim(pal.text)),
        ]
        if card.letter is not None:
            anims += [card.slot.animate.set_fill(dim(pal.primary)), card.letter.animate.set_color(dim(pal.on_primary))]
        else:
            anims += [card.slot.animate.set_fill(dim(pal.surface)).set_stroke(dim(pal.muted))]
        return anims

    def _explanation(self, text, plan, pal, cx):
        """Panel with the check badge's resting place on its left and the text beside it."""
        theme = self.theme
        face = shapes.card(plan.e_w, plan.e_h, color=H.mix(pal.surface, pal.success, 0.2),
                           radius=min(theme.radius, plan.e_h / 2), stroke=pal.success, stroke_width=2.5)
        body = fit_text(text, width=plan.e_text_w, size=plan.e_size, min_size=plan.e_size, max_lines=plan.e_lines,
                        font=theme.font, weight="NORMAL", color=pal.text, align="left",
                        line_spacing=H.EXPLANATION_SPACING)
        content_w = plan.badge_d + plan.e_gap + body.width
        start = cx - content_w / 2
        body.move_to([start + plan.badge_d + plan.e_gap + body.width / 2, plan.bottom_y, 0])
        face.move_to([cx, plan.bottom_y, 0])
        return SimpleNamespace(group=VGroup(face, body), badge_at=np.array([start + plan.badge_d / 2, plan.bottom_y, 0.0]))
