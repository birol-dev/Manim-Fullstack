"""Celebration card: a hero (photo or icon) with a ring, a greeting, a name, an optional
count-up number, a message and a signature, with confetti. Built on the kit; the confetti,
twinkles and live shapes come from the local ``fx`` helpers.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import numpy as np
from manim import (
    DOWN,
    LEFT,
    UP,
    Circle,
    Create,
    DashedVMobject,
    FadeIn,
    LaggedStart,
    Rectangle,
    Star,
    Succession,
    ValueTracker,
    VGroup,
    Wait,
    rate_functions,
    there_and_back,
)

from studio.kit import Counter, StudioScene, ease_out, fit_text, fonts, measure, media, overshoot, shapes, size_for_height
from studio.kit.layout import Region

from . import fx
from .schema import META, OCCASIONS, Params

# Motion flavor per occasion: where the confetti comes from, how the name arrives, which
# number is the star of the card.
FLAVORS = {
    "birthday": {"confetti": "cannons", "letters": "bounce", "number_primary": False},
    "anniversary": {"confetti": "burst", "letters": "rise", "number_primary": True},
    "milestone": {"confetti": "burst", "letters": "bounce", "number_primary": True},
    "thanks": {"confetti": "rain", "letters": "rise", "number_primary": False},
    "welcome": {"confetti": "cannons", "letters": "bounce", "number_primary": False},
}
FALLBACK_ICONS = ("sparkles", "star")
HERO_BLOCK = 1.24  # the hero (with halo and orbit) is this many diameters tall
SCALES = (1.0, 0.92, 0.85, 0.78, 0.72, 0.66, 0.6, 0.55, 0.5, 0.45, 0.4, 0.35)
TEXT_Z = 10
ICON_Z = 5
CONFETTI_Z = -1


class Template(StudioScene):
    Params = Params
    META = META

    # ------------------------------------------------------------------ setup
    def build(self):
        self.flavor = FLAVORS[self.p.occasion]
        self._palette()
        if self.bg is not None:
            self.bg.set_z_index(-20)
        self.clock = fx.Clock()
        self.add(self.clock)
        parts = self._compose()
        self._intro(parts)

    def _palette(self):
        p, th = self.p, self.theme
        accents = list(th.accents)
        if p.accent:
            accents[0] = p.accent
        self.accents = accents
        self.accent = accents[0]
        self.on_accent = fx.on_color(self.accent, "#FFFFFF", "#111111") if p.accent else th.on_accent
        # Color for big type: the accent when it reads on the background, else another accent, else the text color.
        self.ink = fx.readable(accents, th.bg, th.text, 2.7)
        self.mark = self.accent if self.ink != self.accent else accents[1]

    # ------------------------------------------------------------------ layout
    def _fit(self, text, *, width, size, min_size, max_lines, one_line=None, weight="NORMAL", **kw):
        """``fit_text`` plus two things the kit does not do: prefer one line when it fits at
        *one_line* x the size (instead of wrapping a short phrase into a stub), and shrink a
        single long word that is wider than *width* (the kit only counts lines)."""
        size = max(size, min_size, 24)
        family = fonts.resolve(self.theme.font)
        plain = text.replace("*", "")
        if one_line is not None and not any(c == chr(10) for c in plain):
            natural = measure(plain, size=size, font=family, weight=weight)
            fitted = size * min(1.0, width / max(natural, 1e-6)) * 0.99
            if fitted >= size * one_line:
                size, max_lines, min_size = fitted, 1, min(min_size, fitted)
        group = fit_text(text, width=width, size=size, min_size=min_size, max_lines=max_lines, weight=weight, **kw)
        if any("…" in line.original_text for line in group.lines) and "…" not in text:
            max_lines = max(max_lines, len(text.split()))
            group = fit_text(text, width=width, size=min_size, min_size=min_size, max_lines=max_lines,
                             weight=weight, **kw)
        for _ in range(6):
            if group.width <= width * 1.001 or group.font_size <= 24.01:
                break
            smaller = max(24.0, group.font_size * width / group.width * 0.985)
            group = fit_text(text, width=width, size=smaller, min_size=smaller, max_lines=max_lines, weight=weight,
                             **kw)
        if group.width > width:
            group.scale(width / group.width)
        # Set the whole family: entrances animate individual lines and glyphs.
        return group.set_z_index(TEXT_Z)

    def _texts(self, k, width, align):
        """The text mobjects at scale *k*, each centered at the origin."""
        p, th, lay = self.p, self.theme, self.layout
        land = lay.is_landscape
        primary = self.flavor["number_primary"]
        t = SimpleNamespace(headline=None, name=None, counter=None, label=None, message=None, signoff=None)
        common = {"font": th.font, "align": align, "emphasis_color": self.ink}
        body = {**common, "emphasis_color": th.text}

        headline = p.headline or OCCASIONS[p.occasion]["headline"]
        t.headline = self._fit(th.display(headline), width=width, size=(58 if land else 64) * k, min_size=30,
                               max_lines=2, one_line=0.8, weight=th.display_weight, color=th.text, **common)
        if p.name:
            name = self._fit(th.display(p.name), width=width, size=(104 if land else 124) * k, min_size=40,
                             max_lines=2, one_line=0.45, weight=th.display_weight, color=self.ink, **common)
            wave = fx.squiggle(min(max(name.width * 0.6, 1.6), 4.6), self.mark, stroke=max(5.0, 7.5 * k))
            wave.next_to(name, DOWN, buff=0.16 * min(k, 1))
            wave.set_z_index(TEXT_Z)
            if align == "left":
                wave.align_to(name, LEFT)
            else:
                wave.move_to([name.get_center()[0], wave.get_center()[1], 0])
            t.name = name
            t.wave = wave
            t.name_block = VGroup(name, wave).move_to([0, 0, 0])
        else:
            t.name_block = None
        if p.number is not None:
            digit_h = (1.6 if land else 2.0) * k if primary else (1.0 if land else 1.1) * k
            t.counter = self._counter(digit_h, width, align)
            if p.number_label:
                t.label = self._fit(p.number_label, width=width, size=38 * k, min_size=24, max_lines=2,
                                    weight="NORMAL", color=th.text, **body)
        if p.message:
            t.message = self._fit(p.message, width=width * 0.96, size=38 * k, min_size=26, max_lines=5,
                                  color=th.text, line_spacing=1.24, **body)
        if p.from_line:
            t.signoff = self._fit(p.from_line, width=width, size=34 * k, min_size=24, max_lines=2, weight="BOLD",
                                  color=th.text, **body)
        return t

    def _counter(self, digit_h, width, align):
        p, th = self.p, self.theme
        fmt = {"locale": self.s.locale, "compact": p.compact}
        anchor = "left" if align == "left" else "center"

        def make(size):
            return Counter(p.number, size=size, font=th.font, weight=th.display_weight, color=self.ink,
                           anchor=anchor, fmt=fmt).set_z_index(TEXT_Z)

        size = size_for_height(digit_h, font=th.font, weight=th.display_weight)
        counter = make(size)
        widest = 0.0
        for fraction in (1, 0.999, 0.99, 0.9, 0.5, 0.2, 0.1, 0.01):
            widest = max(widest, counter.set_value(p.number * fraction).width)
        if widest > width:
            counter = make(size * width / widest * 0.98)
        counter.set_value(p.number)
        return counter

    def _rows(self, t, k):
        g = min(k, 1.0)
        rows = []

        def add(key, mob, gap):
            if mob is not None:
                rows.append(SimpleNamespace(key=key, mob=mob, gap=gap * g))

        add("headline", t.headline, 0.46)
        # Row gaps normally scale with k; this one follows the fitted name itself.
        name_gap = 0.18 * t.name.height if t.name is not None else 0
        add("name", t.name_block, name_gap / g)
        add("counter", t.counter, 0.5)
        add("label", t.label, 0.16)
        add("message", t.message, 0.5)
        add("signoff", t.signoff, 0.5)
        return rows

    @staticmethod
    def _stack_height(rows):
        return sum(r.mob.height for r in rows) + sum(r.gap for r in rows[1:])

    def _compose(self):
        """Pick the largest scale at which everything fits, then place hero and text."""
        lay = self.layout
        region = lay.safe
        land = lay.is_landscape
        align = "left" if land else "center"
        has_photo = bool(self.asset(self.p.photo))
        d_min = 1.5 if has_photo else 1.35
        chosen = None
        for index, k in enumerate(SCALES):
            last = index == len(SCALES) - 1
            if land:
                hero_box, text_box = region.split_cols([0.4, 0.6], gap=lay.unit * 4)
                texts = self._texts(k, text_box.width, align)
                rows = self._rows(texts, k)
                stack_h = self._stack_height(rows)
                diameter = min(hero_box.width * 0.74, region.height * 0.82)
                ok = stack_h <= text_box.height
                chosen = (k, texts, rows, stack_h, diameter, hero_box, text_box)
            else:
                texts = self._texts(k, region.width, align)
                rows = self._rows(texts, k)
                stack_h = self._stack_height(rows)
                hero_gap = rows[0].gap
                room = (region.height - stack_h - hero_gap) / HERO_BLOCK
                d_max = min(region.width * 0.54, region.height * 0.31)
                diameter = min(d_max, room)
                ok = diameter >= max(d_min, 0.72 * d_max)
                chosen = (k, texts, rows, stack_h, max(diameter, 1.0), region, region)
            if ok or last:
                break
        k, texts, rows, stack_h, diameter, hero_box, text_box = chosen

        # place
        if land:
            top = text_box.center[1] + stack_h / 2
            hero_center = hero_box.center.copy()
            x_left = text_box.left
            y = top
        else:
            hero_gap = rows[0].gap
            total = HERO_BLOCK * diameter + hero_gap + stack_h
            top = region.center[1] + total / 2
            hero_center = np.array([region.center[0], top - HERO_BLOCK / 2 * diameter, 0.0])
            y = top - HERO_BLOCK * diameter - hero_gap
            x_left = None
        for i, row in enumerate(rows):
            if i > 0:
                y -= row.gap
            mob = row.mob
            center_y = y - mob.height / 2
            if land:
                mob.move_to([x_left + mob.width / 2, center_y, 0])
            else:
                mob.move_to([region.center[0], center_y, 0])
            y -= mob.height
        return SimpleNamespace(k=k, texts=texts, rows=rows, hero_center=hero_center, D=diameter, land=land,
                               hero_box=hero_box, text_box=text_box)

    # ------------------------------------------------------------------ pieces
    def _icon(self, size, color):
        """The icon mobject (a star when the bundled icon is missing)."""
        p = self.p
        names = [p.icon, OCCASIONS[p.occasion]["icon"], *FALLBACK_ICONS]
        for name in names:
            if not name:
                continue
            mob = media.icon(name, size=size, color=color, stroke_width=size * 100 / 12 * 1.1)
            if mob.has_points() or len(mob.submobjects):
                return mob
        star = Star(n=5, outer_radius=size / 2, inner_radius=size / 4.4)
        return star.set_fill(color, opacity=1).set_stroke(width=0)

    def _hero(self, D, center):
        th = self.theme
        accent = self.accent
        center = np.array(center, dtype=float)
        h = SimpleNamespace(center=center, D=D, halo=None, ring=None, core=[], icon=None, badge=None, orbit=None)
        h.halo = fx.glow(center, D * 0.56, accent, steps=10, total=0.2)
        h.halo.set_z_index(-4)
        h.ring = Circle(radius=D / 2).set_stroke(accent, width=max(D * 1.7, 4)).set_fill(opacity=0).move_to(center)
        h.ring.set_z_index(-3)
        photo_path = self.asset(self.p.photo)
        if photo_path:
            photo_d = D * 0.84
            border = Circle(radius=photo_d / 2 + D * 0.024).set_fill(th.surface, opacity=1).set_stroke(width=0)
            border.move_to(center).set_z_index(-2)
            photo = media.image(photo_path, height=photo_d, shape="circle").move_to(center)
            photo.set_z_index(-1)
            h.core = [border, photo]
            angle = math.radians(-42)
            badge_center = center + np.array([math.cos(angle), math.sin(angle), 0.0]) * (D / 2)
            disc = Circle(radius=D * 0.14).set_fill(accent, opacity=1).set_stroke(th.surface, width=D * 1.7)
            glyph = self._icon(D * 0.15, self.on_accent).move_to([0, 0, 0])
            h.badge = VGroup(disc, glyph).move_to(badge_center)
            h.badge.set_z_index(ICON_Z)
        else:
            disc = Circle(radius=D * 0.4).set_fill(accent, opacity=1).set_stroke(width=0).move_to(center)
            disc.set_z_index(-2)
            h.core = [disc]
            h.icon = self._icon(D * 0.4, self.on_accent).move_to(center)
            h.icon.set_z_index(ICON_Z)
        orbit_r = D * 0.62
        dashes = DashedVMobject(Circle(radius=orbit_r), num_dashes=40, dashed_ratio=0.4)
        dashes.set_stroke(self.accents[1], width=3, opacity=0.65)
        dots = VGroup(*[
            Circle(radius=D * 0.034).set_fill(color, opacity=1).set_stroke(width=0).move_to(
                [orbit_r * math.cos(a), orbit_r * math.sin(a), 0])
            for a, color in ((0.5, self.accents[1]), (2.65, self.accents[2]), (4.6, self.accents[4 % len(self.accents)]))
        ])
        h.orbit = VGroup(dashes, dots).move_to(center)
        h.orbit.set_z_index(-3)
        c = center.copy()
        h.orbit.add_updater(lambda mob, dt: mob.rotate(0.32 * dt, about_point=c))
        return h

    def _backdrop(self, hero):
        lay, th = self.layout, self.theme
        fw, fh, short = lay.frame_width, lay.frame_height, lay.short
        group = VGroup()
        tint_a, tint_b = fx.vivid(self.accents[1:] + [self.accents[0]], th.bg, 2)
        blob_a = fx.glow([fw / 2, fh / 2, 0], short * 0.78, tint_a, total=0.26)
        blob_b = fx.glow([-fw / 2, -fh / 2, 0], short * 0.72, tint_b, total=0.22)
        group.add(blob_a, blob_b)
        for radius, opacity in ((hero.D * 0.92, 0.16), (hero.D * 1.3, 0.1)):
            ring = Circle(radius=radius).set_fill(opacity=0).set_stroke(self.accent, width=2.5, opacity=opacity)
            ring.move_to(hero.center)
            self.keep_particles_clear(ring, self._particle_foreground)
            group.add(ring)
        group.set_z_index(-8)
        return group

    def _sparkles(self, hero, t_birth, step):
        box = self._decoration_box
        D, c = hero.D, hero.center
        spots = [(-0.98, 0.12, 0.085, 1), (0.95, -0.05, 0.07, 2), (0.78, 0.66, 0.05, 4), (-0.74, -0.58, 0.055, 3),
                 (-0.52, 0.8, 0.04, 0)]
        placed = []
        for i, (dx, dy, rad, ci) in enumerate(spots):
            radius = max(D * rad, 0.14)
            # Reserve the maximum entrance overshoot, not just the settled star.
            extent = radius * 1.2 + 0.10
            desired = c + np.array([dx * D, dy * D, 0])
            candidates = [desired] + [c + np.array([math.cos(a), math.sin(a), 0]) * D * distance
                                      for distance in (0.72, 0.86, 1.02)
                                      for a in np.linspace(0, math.tau, 32, endpoint=False)]
            candidates = [np.array([np.clip(pos[0], box.left + extent, box.right - extent),
                                     np.clip(pos[1], box.bottom + extent, box.top - extent), 0])
                          for pos in candidates]
            candidates.sort(key=lambda pos: np.linalg.norm(pos - desired))

            def available(pos):
                for target in self._particle_foreground:
                    low, high = target.get_corner(DOWN + LEFT)[:2], target.get_corner(UP - LEFT)[:2]
                    if isinstance(target, Circle):
                        delta = np.maximum(np.abs(pos[:2] - target.get_center()[:2]) - extent, 0)
                        if np.sum((delta / np.maximum((high - low) / 2, 1e-6)) ** 2) <= 1:
                            return False
                    elif np.all(pos[:2] + extent >= low) and np.all(pos[:2] - extent <= high):
                        return False
                return all(np.linalg.norm(pos - other[0]) > extent + other[1] * 1.2 + 0.1 for other in placed)

            pos = next((pos for pos in candidates if available(pos)), candidates[0])
            placed.append((pos, radius, self.accents[ci % len(self.accents)],
                           t_birth + i * step, i * 1.7))

        def factory(t):
            out = []
            for pos, r, color, birth, phase in placed:
                age = t - birth
                if age < 0:
                    continue
                grow = fx.ease_out_back(age / 0.55)
                twinkle = 0.82 + 0.18 * math.sin(2.4 * t + phase)
                out.append(fx.sparkle(pos, r * grow * twinkle, color, angle=0.25 * math.sin(1.1 * t + phase)))
            return out

        live = fx.Live(self.clock, factory)
        live.set_z_index(3)
        return self.keep_particles_clear(live, self._particle_foreground)

    def _ripples(self, hero, t0, until):
        D, c = hero.D, hero.center
        events = [(t0, 0.85, 0.5, 1.25)]
        t = t0 + 2.9
        while t < until:
            events.append((t, 0.5, 0.28, 1.4))
            t += 2.9

        def factory(now):
            out = []
            for start, grow, opacity, dur in events:
                age = now - start
                if 0 <= age <= dur:
                    x = age / dur
                    ring = Circle(radius=D / 2 * (1 + grow * fx.ease_out(x)))
                    ring.set_fill(opacity=0).set_stroke(self.accent, width=4.5 * (1 - 0.6 * x), opacity=opacity * (1 - x))
                    out.append(ring.move_to(c))
            return out

        live = fx.Live(self.clock, factory)
        live.set_z_index(-6)
        return self.keep_particles_clear(live, self._particle_foreground)

    # ------------------------------------------------------------------ animation
    @staticmethod
    def _after(anim, delay):
        return Succession(Wait(delay), anim) if delay > 0.001 else anim

    def _letters(self, group, T, bounce):
        glyphs = [g for line in group.lines for g in line.submobjects]
        n = max(len(glyphs), 1)
        run = T(0.55)
        lag = min(T(0.05), T(0.5) / n)
        anims = [
            FadeIn(g, shift=UP * (0.5 if bounce else 0.22), scale=0.5 if bounce else 0.88, run_time=run,
                   rate_func=overshoot if bounce else ease_out)
            for g in glyphs
        ]
        return LaggedStart(*anims, lag_ratio=lag / run)

    def _lines(self, group, T, delay=0.0, lag=0.1, shift=0.3):
        anims = [
            self._after(FadeIn(line, shift=UP * shift, scale=0.94, run_time=T(0.55), rate_func=ease_out),
                        delay + i * T(lag))
            for i, line in enumerate(group.lines)
        ]
        return anims

    def _party(self, hero, start, seed, mode=None):
        lay = self.layout
        mode = mode or self.flavor["confetti"]
        count = {"cannons": 56, "burst": 54, "rain": 48}[mode]
        if self.mode == "poster" or self.is_peek:
            count = int(count * 0.55)  # a thumbnail should keep the text readable
        party = fx.Party(self.clock, start, colors=self.accents, frame_w=lay.frame_width, frame_h=lay.frame_height,
                         mode=mode, origin=tuple(hero.center[:2]), count=count, seed=seed, size=0.27)
        party.set_z_index(CONFETTI_Z)  # over the hero disc, under all foreground families
        return self.keep_particles_clear(party, self._particle_foreground)

    def _intro(self, parts):
        m, th, lay = self.motion, self.theme, self.layout
        t = parts.texts
        hero = self._hero(parts.D, parts.hero_center)
        # Clear whole lines, including spaces/letter holes and antialiased edges.
        # Keep references to animated geometry as well as the settled layout.
        self._particle_foreground = [line for group in
                                     (t.headline, t.name, t.label, t.message, t.signoff) if group is not None
                                     for line in group.lines]
        self._particle_foreground += [mob for mob in (t.counter, hero.icon, hero.badge,
                                                       getattr(t, "wave", None)) if mob is not None]
        # The hero's circular disc/border encloses the icon/photo. Using its
        # curved outline keeps surrounding rings intact, including at corners.
        self._particle_foreground += hero.core[:1]
        top = max(row.mob.get_top()[1] for row in parts.rows)
        bottom = min(row.mob.get_bottom()[1] for row in parts.rows)
        text_block = Rectangle(width=parts.text_box.width, height=top - bottom).move_to(
            [parts.text_box.center[0], (top + bottom) / 2, 0])
        self._decoration_box = (parts.hero_box if parts.land else
                                Region(lay.left, lay.right, lay.top, top + 0.20))
        if hasattr(t, "wave"):
            self.keep_particles_clear(t.wave, self._particle_foreground, padding=0.02)
        self._particle_foreground.append(text_block)
        for decoration in (hero.halo, hero.ring, hero.orbit):
            self.keep_particles_clear(decoration, self._particle_foreground)
        has_message = t.message is not None or t.signoff is not None

        # Time scale: fit the whole entrance into ~72% of the requested length.
        base = 1.3 + (1.3 if t.name_block is not None else 0) + (2.0 if t.counter is not None else 0) \
            + (1.2 if has_message else 0)
        ts = min(max(0.72 * self.target_length / (base * m.k), 0.55), 1.2)

        def T(x):
            return x * m.k * ts

        if self.s.background.kind == "theme":
            frame = shapes.full_frame(lay.frame_width, lay.frame_height, th.bg, th.bg2)
            frame.set_z_index(-19)
            self.add(frame)
        backdrop = self._backdrop(hero)
        t0 = self.clock.t
        ripples = self._ripples(hero, t0 + T(0.35), t0 + self.target_length)
        sparkles = self._sparkles(hero, t0 + T(0.7), T(0.12))
        self.add(ripples, sparkles, hero.orbit)
        hero.orbit.set_opacity(0)

        # 1. backdrop, hero, headline
        anims = [FadeIn(backdrop, run_time=T(0.9)), FadeIn(hero.halo, scale=0.4, run_time=T(0.8), rate_func=ease_out),
                 Create(hero.ring, run_time=T(0.95), rate_func=ease_out)]
        anims += [FadeIn(c, scale=0.35, run_time=T(0.75), rate_func=overshoot) for c in hero.core]
        if hero.icon is not None:
            anims.append(self._after(FadeIn(hero.icon, scale=0.4, run_time=T(0.6), rate_func=overshoot), T(0.28)))
        if hero.badge is not None:
            anims.append(self._after(FadeIn(hero.badge, scale=0.3, run_time=T(0.55), rate_func=overshoot), T(0.55)))
        anims.append(self._after(hero.orbit.animate(run_time=T(0.8)).set_opacity(1), T(0.3)))
        anims += self._lines(t.headline, T, delay=T(0.45), lag=0.16, shift=0.35)
        self.play(*anims)

        # 2. name
        party = None
        parties = []

        def peek_clock(name_duration=0.0):
            if not self.is_peek or party is None:
                return
            # Let the decoration progress forward to the thumbnail's selected
            # phase over the remaining entrance. Never rewind a live effect.
            closing = [T(0.5)] if t.counter is not None else [0.0]
            if t.message is not None:
                closing.append(T(0.55 + 0.1 * (len(t.message.lines) - 1)))
            if t.signoff is not None:
                delay = T(0.35 + 0.1 * len(t.message.lines)) if t.message is not None else 0.0
                closing.append(delay + T(0.55))
            duration = name_duration + (T(2.0) if t.counter is not None else 0.0) + max(closing)
            start, end, at = self.clock.t, party.start + 1.15, self.elapsed
            self.clock.clear_updaters()
            self.clock.add_updater(lambda clock, dt: setattr(
                clock, "t", start + (end - start) * min(1, (self.elapsed - at) / max(duration, 1e-6))))

        if t.name_block is not None:
            if self.p.confetti:
                party = self._party(hero, self.clock.t + T(0.3), seed=11)
                parties.append(party)
                self.add(party)
            anims = [self._letters(t.name, T, self.flavor["letters"] == "bounce"),
                     self._after(Create(t.wave, run_time=T(0.7), rate_func=ease_out), T(0.5))]
            peek_clock(max(a.run_time for a in anims))
            self.play(*anims)
        elif self.p.confetti:
            party = self._party(hero, self.clock.t, seed=11)
            parties.append(party)
            self.add(party)
            peek_clock()

        # 3. number
        counter = t.counter
        if counter is not None:
            target = self.p.number
            counter.set_value(0)
            self.play(FadeIn(counter, scale=0.6, run_time=T(0.5), rate_func=overshoot))
            tracker = ValueTracker(0)
            counter.track(tracker)
            anims = [tracker.animate(run_time=T(1.5), rate_func=rate_functions.ease_out_cubic).set_value(target)]
            if t.label is not None:
                anims.append(self._after(FadeIn(t.label, shift=UP * 0.25, run_time=T(0.6), rate_func=ease_out),
                                         T(0.4)))
            self.play(*anims)
            counter.clear_updaters()
            counter.set_value(target)

        # 4. message, signature, a last pulse on the number
        if has_message or counter is not None:
            anims = []
            if counter is not None:
                anims.append(counter.animate(run_time=T(0.5), rate_func=there_and_back).scale(1.08))
            delay = 0.0
            if t.message is not None:
                anims += self._lines(t.message, T, delay=0.0, lag=0.1, shift=0.25)
                delay = T(0.35 + 0.1 * len(t.message.lines))
            if t.signoff is not None:
                anims.append(self._after(FadeIn(t.signoff, shift=UP * 0.25, run_time=T(0.55), rate_func=ease_out),
                                         delay))
            self.play(*anims)

        # later bursts keep a long video alive
        if self.p.confetti and party is not None:
            nxt = party.start + 6.8
            seed = 12
            while nxt < self.target_length - 2.5 and len(parties) < 4:
                later = self._party(hero, nxt, seed=seed)
                self.add(later)
                parties.append(later)
                nxt += 6.8
                seed += 1
        if (self.mode == "poster" or self.is_peek) and party is not None:
            if self.is_peek:
                self.clock.clear_updaters()
            self.clock.t = party.start + 1.15
        self.poster()
