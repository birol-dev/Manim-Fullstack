"""Announcement: kicker, headline, a huge element, details with icons, call to action, QR.

Three layouts share one motion language:

* ``bold``   centered type; the big text slams onto a full-bleed color band.
* ``split``  a photo (or a color panel carrying the big text) beside / above the text.
* ``poster`` a ticket card dealt onto the screen; the big text and QR sit on the stub.

Beats: (teaser) -> kicker -> headline word by word -> big reveal -> details stagger ->
call to action + QR -> hold with the call to action breathing.
"""

import math

from manim import (
    DOWN,
    LEFT,
    RIGHT,
    UP,
    AnimationGroup,
    Circle,
    FadeIn,
    FadeOut,
    LaggedStart,
    Rectangle,
    UpdateFromAlphaFunc,
    VGroup,
)

from studio.kit import StudioScene, shapes
from studio.kit.layout import Region

from . import blocks as B
from .schema import META, Params

fit_text = B.fit_text

DEG = math.pi / 180


class Template(StudioScene):
    Params = Params
    META = META
    logo_region = "top-right"

    # -- entry -----------------------------------------------------------------
    def build(self):
        p, lay = self.p, self.layout
        bg = self.s.background
        self.pal = B.Palette(self.theme, p.accent, bg.color if bg.kind in ("solid", "gradient") and bg.color else None)
        self.u = lay.unit
        self.fw, self.fh = lay.frame_width, lay.frame_height
        self.decorate = bg.kind != "transparent"
        self.photo = self.asset(p.image)
        self.logo_path = self.asset(p.logo)
        self.details = [d for d in p.details if d.text][:4]

        layout = {"bold": self._bold, "split": self._split, "poster": self._poster}[p.layout]
        teaser = self._teaser() if p.teaser else None
        beats, hold = layout()
        self._run(teaser, [b for b in beats if b is not None], [h for h in hold if h is not None])

    # -- timeline --------------------------------------------------------------
    def _reading(self) -> float:
        p = self.p
        # The big text reads at a glance; ads are skimmed a little faster than subtitles.
        chars = len(p.kicker) + len(p.headline) + len(p.call_to_action) + sum(len(d.text) for d in self.details)
        return 1.0 + chars / 18

    def _run(self, teaser, beats, hold):
        m = self.motion
        natural = sum(b.run_time for b in beats)
        teaser_total = (teaser["in"].run_time + teaser["hold"] + teaser["out"].run_time) if teaser else 0.0
        if self.s.length is None:
            # Long content gets more time to read (up to 14 s) unless a length was asked for.
            wanted = teaser_total + natural + max(3.0, self._reading() - natural)
            self.target_length = round(min(14.0, max(self.META.default_length, wanted)) * 2) / 2
        end = self.target_length - (m.exit if self.s.ending == "fade" else 0)
        room = end - 2.0  # at least 2 s of hold with everything on screen
        f = 1.0
        if teaser_total + natural > room:
            f = max(0.45, room / max(teaser_total + natural, 1e-6))

        if teaser:
            self.play(teaser["in"], run_time=teaser["in"].run_time * f)
            self.wait(max(0.3, teaser["hold"] * f))
            self.remove(*teaser["pieces"])
            self.add(teaser["group"])
            self.play(teaser["out"], run_time=teaser["out"].run_time * f)
        self.cue("whoosh")
        for beat in beats:
            under = getattr(beat, "under", None)
            if under:  # decoration goes right above the background, under everything else
                self.add(*under)
                self.bring_to_back(*under)
                if self.bg is not None:
                    self.bring_to_back(self.bg)
            self.play(beat, run_time=beat.run_time * f)
        self.poster()
        left = self.remaining()
        if left > 0.05:
            if hold:
                self.play(*[h(left) for h in hold], run_time=left)
            else:
                self.wait(left)

    def _teaser(self):
        p, pal, lay, m, u = self.p, self.pal, self.layout, self.motion, self.u
        S = lay.safe
        words = fit_text(self.theme.display(p.teaser), width=S.width * (0.86 if lay.is_portrait else 0.7),
                         height=S.height * 0.5, size=76 if lay.is_portrait else 72, min_size=36, max_lines=3,
                         font=pal.font, weight=pal.display_weight, color=pal.text, emphasis_color=pal.accent_text,
                         line_spacing=1.0)
        words.move_to(S.center + UP * u * 3)
        dots = VGroup(*[Circle(radius=u * 1.2).set_fill(pal.accent, 1).set_stroke(width=0) for _ in range(3)])
        dots.arrange(RIGHT, buff=u * 2.4).next_to(words, DOWN, buff=u * 7)
        rise = B.rise_words(words, unit=u, run_time=m.t(0.7), lag=m.t(0.09))
        t_in = AnimationGroup(rise, LaggedStart(*[B.pop(d, run_time=m.t(0.4), scale=0.2) for d in dots],
                                                lag_ratio=0.35))
        t_out = AnimationGroup(
            FadeOut(words, scale=1.18, run_time=m.t(0.45), rate_func=B.rate_functions.ease_in_cubic),
            FadeOut(dots, shift=DOWN * u * 4, run_time=m.t(0.35)),
        )
        return {"group": VGroup(words, dots), "pieces": rise.pieces, "in": t_in, "out": t_out,
                "hold": max(1.4, m.reading_time(p.teaser, minimum=0.8))}

    # -- shared pieces -----------------------------------------------------------
    def _logo(self, height, max_width):
        if not self.logo_path:
            return None
        try:
            return B.logo(self.logo_path, height=height, max_width=max_width)
        except Exception:  # an unreadable upload must not break the render
            return None

    def _kicker_in(self, kick, anchor="center"):
        m, u = self.motion, self.u
        if kick.radius:  # pill / rounded card
            bg, color, h, r = kick.bg, self.pal.accent, kick.bg.height, kick.radius
            grow = B.open_shape(bg, lambda w: shapes.card(w, h, color=color, radius=min(r, w / 2)),
                                run_time=m.t(0.45), anchor=anchor)
        else:
            grow = B.grow_width(kick.bg, run_time=m.t(0.4), edge=LEFT)
        words = B.rise_words(kick.words, unit=u, run_time=m.t(0.45), lag=m.t(0.05), distance=0.6)
        return LaggedStart(grow, words, lag_ratio=0.35)

    def _details_in(self, det):
        m, u = self.motion, self.u
        anims = []
        for cell in det.cells:
            parts = []
            if cell.bg is not None:
                parts.append(FadeIn(cell.bg, scale=0.88, run_time=m.t(0.45), rate_func=B.BACK))
            parts.append(B.pop(cell.row.mark, run_time=m.t(0.45), scale=0.3))
            parts.append(FadeIn(cell.row.words, shift=RIGHT * u * 3, run_time=m.t(0.5), rate_func=B.QUART))
            anims.append(LaggedStart(*parts, lag_ratio=0.18))
        return LaggedStart(*anims, lag_ratio=m.t(0.13) / anims[0].run_time)

    def _button_in(self, btn, anchor="center"):
        m, u = self.motion, self.u
        bg, h, r, color = btn.bg, btn.bg.height, btn.radius, btn.fill
        grow = B.open_shape(bg, lambda w: shapes.card(w, h, color=color, radius=min(r, w / 2)),
                            run_time=m.t(0.5), anchor=anchor)
        words = FadeIn(btn.words, shift=UP * u * 2, run_time=m.t(0.4), rate_func=B.QUART)
        return LaggedStart(grow, words, lag_ratio=0.4)

    def _qr_in(self, qr):
        m = self.motion
        return LaggedStart(B.pop(qr.card, run_time=m.t(0.5), scale=0.5),
                           FadeIn(qr.modules, run_time=m.t(0.4)), lag_ratio=0.4)

    def _qr(self, size):
        if not self.p.qr_text:
            return None
        return B.qr_card(self.p.qr_text, size=size, radius=max(self.pal.radius * 0.8, self.u * 1.2))

    @staticmethod
    def _footer_group(qr=None, cta=None, button=None):
        parts = [x for x in (qr, cta, button) if x is not None]
        if not parts:
            return None
        group = VGroup(*parts)
        group.qr, group.cta, group.button = qr, cta, button
        group.cut = button.cut if button is not None else False
        return group

    def _footer(self, width, *, qr_size, cta_size, button_fill, button_color):
        """The call to action as a button; with a QR code, the call to action is written beside it."""
        p, pal, u = self.p, self.pal, self.u
        qr = self._qr(qr_size)
        if qr is not None:
            if not p.call_to_action:
                return self._footer_group(qr=qr)
            gap = u * 4
            cta = fit_text(p.call_to_action, width=width - qr.width - gap, height=qr.height, size=cta_size,
                           min_size=24, max_lines=3, font=pal.font, weight="BOLD", color=pal.text, align="left",
                           line_spacing=1.08)
            B.shrink_to(cta, width - qr.width - gap)
            cta.next_to(qr, RIGHT, buff=gap)
            group = self._footer_group(qr=qr, cta=cta)
            group.cut = B.is_cut(cta, p.call_to_action)
            return group
        if not p.call_to_action:
            return None
        btn = B.button(p.call_to_action, pal, max_width=width, size=cta_size, fill=button_fill, color=button_color)
        return self._footer_group(button=btn)

    def _footer_in(self, footer, anchor="center"):
        m, u = self.motion, self.u
        anims = []
        if footer.qr is not None:
            anims.append(self._qr_in(footer.qr))
        if footer.cta is not None:
            anims.append(B.rise_words(footer.cta, unit=u, run_time=m.t(0.5), lag=m.t(0.04), distance=0.6))
        if footer.button is not None:
            anims.append(self._button_in(footer.button, anchor=anchor))
        return LaggedStart(*anims, lag_ratio=0.3)

    def _breathe(self, target):
        """Hold motion: the call to action (button, or the QR code) pulses gently."""
        if target is None:
            return None
        target.set_z_index(10)
        return lambda run_time: B.breathe(target, run_time=run_time, period=1.8, amount=0.035)

    @staticmethod
    def _stack(items, gaps, region, *, align, max_extra, valign="center"):
        """Place mobjects top to bottom in *region*; spare height widens the gaps (up to *max_extra* each),
        the rest centers the stack."""
        items = [(mob, gap) for mob, gap in zip(items, gaps) if mob is not None]
        if not items:
            return
        total = sum(mob.height for mob, _ in items) + sum(g for _, g in items[1:])
        if total > region.height:
            # Dense tickets and square cards give up spacing before shrinking ink.
            ink = sum(mob.height for mob, _ in items)
            gaps = sum(g for _, g in items[1:])
            gap_scale = max(0.0, min(1.0, (region.height - ink) / gaps)) if gaps else 0.0
            items = [(mob, gap * gap_scale) for mob, gap in items]
            if ink > region.height:
                for mob, _ in items:
                    mob.scale(region.height / ink)
            total = sum(mob.height for mob, _ in items) + sum(g for _, g in items[1:])
        spare = max(0.0, region.height - total)
        extra = min(spare / (len(items) - 1), max_extra) if len(items) > 1 else 0.0
        rest = spare - extra * (len(items) - 1)
        y = region.top - (rest / 2 if valign == "center" else 0)
        for i, (mob, gap) in enumerate(items):
            if i:
                y -= gap + extra
            if align == "left":
                mob.move_to([region.left + mob.width / 2, y - mob.height / 2, 0])
            else:
                mob.move_to([region.center[0], y - mob.height / 2, 0])
            y -= mob.height

    def _intro(self, logo, kick, head, anchor):
        m, u = self.motion, self.u
        out = []
        if logo is not None:
            out.append(FadeIn(logo, shift=DOWN * u * 3, run_time=m.t(0.5), rate_func=B.QUART))
        if kick is not None:
            out.append(self._kicker_in(kick, anchor=anchor))
        if head is not None:
            out.append(B.rise_words(head, unit=u, run_time=m.t(0.6), lag=m.t(0.08)))
        return out

    # -- choosing a fit -----------------------------------------------------------
    @staticmethod
    def _pick(candidates):
        """The first candidate whose flexible space covers its need; else the one closest to it.
        Candidates are dicts with ``flex`` and ``need`` (or None when rejected, e.g. text was cut)."""
        best = None
        for cand in candidates:
            if cand is None:
                continue
            if cand["flex"] >= cand["need"]:
                return cand
            if best is None or cand["flex"] - cand["need"] > best["flex"] - best["need"]:
                best = cand
        return best

    def _head_min(self, width, max_lines, align, emphasis=None, min_size=34):
        """Height of the headline at its smallest size (it is never cut, the big text gives way)."""
        if not self.p.headline:
            return 0.0
        mob = B.headline(self.p.headline, self.pal, width=width, height=None, size=min_size, min_size=min_size,
                         max_lines=max_lines, align=align, emphasis=emphasis)
        return mob.height

    # -- bold --------------------------------------------------------------------
    def _bold(self):
        p, pal, lay, m, u = self.p, self.pal, self.layout, self.motion, self.u
        S = lay.safe
        W = S.width
        portrait, land = lay.is_portrait, lay.is_landscape
        n = len(self.details)
        tall = S.height / S.width
        has_big = bool(p.big_text)
        tilt = 0 if self.s.energy == "calm" else -2.5 * DEG
        band_w = self.fw * 1.12
        head_lines = 2 if land else 3
        head_max = 88 if portrait else (76 if land else 72)
        head_min = self._head_min(W, head_lines, "center")

        levels = [  # font sizes, QR size and base gap (units), roomy to dense
            dict(detail=32 if portrait else 30, kicker=30 if portrait else 28, cta=34 if portrait else 32,
                 qr=24 if portrait else 20, gap=4.5),
            dict(detail=28, kicker=26, cta=30, qr=18, gap=3.4),
            dict(detail=25, kicker=24, cta=27, qr=16, gap=2.5),
        ]
        if land:
            plan = [(0, n, True), (1, n, True), (1, 2, True), (2, n, True), (2, 2, True), (2, 2, False)]
        elif tall > 1.15:
            plan = [(0, 1, True), (1, 1, True), (2, 1, True), (2, 1, False), (2, 2, True)]
        else:
            plan = [(0, 1, True), (1, 1, True), (2, 1, True), (2, 1, False), (1, 2, True), (2, 2, True)]

        def candidate(level, cols, chips):
            lv = levels[level]
            cols = max(1, min(cols, n)) if n else 1
            det = B.details_block(self.details, pal, width=W, size=lv["detail"], columns=cols, chips=chips,
                                  align="center") if n else None
            if det is not None and det.cut:
                return None
            kick = B.kicker(p.kicker, pal, max_width=W, size=lv["kicker"]) if p.kicker else None
            footer = self._footer(W * (0.9 if not land else 0.7), qr_size=u * lv["qr"], cta_size=lv["cta"],
                                  button_fill=pal.ink, button_color=pal.on_ink)
            if (kick is not None and kick.cut) or (footer is not None and footer.cut):
                return None
            logo = self._logo(u * (9 if portrait else 7) * (1 - 0.15 * level), W * 0.4)
            fixed = [x for x in (logo, kick, det, footer) if x is not None]
            count = len(fixed) + (1 if p.headline else 0) + (1 if has_big else 0)
            gap = u * lv["gap"]
            flex = S.height - sum(x.height for x in fixed) - gap * (count - 1)
            if has_big:
                flex -= band_w * abs(math.sin(tilt))  # the tilted band needs a little more room
            need = head_min + (u * 20 if has_big else 0)
            return dict(logo=logo, kick=kick, det=det, footer=footer, gap=gap, flex=flex, need=need)

        c = self._pick(candidate(*step) for step in plan)
        logo, kick, det, footer, gap, flex = c["logo"], c["kick"], c["det"], c["footer"], c["gap"], c["flex"]

        head = None
        if p.headline:
            budget = max(head_min, flex * (0.42 if has_big else 1.0))
            head = B.headline(p.headline, pal, width=W, height=budget, size=head_max, min_size=34,
                              max_lines=head_lines)
        band = big = band_group = None
        if has_big:
            room = flex - (head.height if head is not None else 0)
            big = B.big_type(p.big_text, pal, width=W * 0.92, height=max(room / 1.5, u * 7), color=pal.on_accent,
                             max_cap=S.height * (0.2 if portrait else 0.3))
            pad = max(big.cap * 0.32, u * 3)
            band = Rectangle(width=band_w, height=big.height + 2 * pad).set_fill(pal.accent, 1).set_stroke(width=0)
            band_group = VGroup(band, big)
            band_group.rotate(tilt)
            B.shrink_to(big, W)

        deco = None
        if self.decorate:
            r1, r2 = lay.short * 0.42, lay.short * 0.26
            c1 = Circle(radius=r1).set_fill(pal.bg2, 1).set_stroke(width=0)
            c2 = Circle(radius=r2).set_fill(pal.bg2, 1).set_stroke(width=0)
            c1.move_to([self.fw / 2 - r1 * 0.35, self.fh / 2 - r1 * 0.3, 0])
            c2.move_to([-self.fw / 2 + r2 * 0.2, -self.fh / 2 + r2 * 0.55, 0])
            deco = VGroup(c1, c2)

        small = gap * 0.7
        self._stack([logo, kick, head, band_group, det, footer],
                    [0, small, small, gap, gap, gap], S, align="center", max_extra=gap * 1.4)

        beats = []
        intro = []
        if deco is not None:
            intro.append(LaggedStart(*[FadeIn(x, scale=0.7, run_time=m.t(0.8), rate_func=B.QUART) for x in deco],
                                     lag_ratio=0.15))
        intro += self._intro(logo, kick, None, "center")
        if intro:
            beats.append(self._under(LaggedStart(*intro, lag_ratio=0.2), deco))
        if head is not None:
            beats.append(B.rise_words(head, unit=u, run_time=m.t(0.6), lag=m.t(0.08)))
        if band_group is not None:
            beats.append(LaggedStart(
                B.grow_width(band, run_time=m.t(0.45), edge=LEFT),
                B.slam_chars(big, run_time=m.t(0.4), lag=m.t(0.06), scale=1.8),
                lag_ratio=0.45,
            ))
        if det is not None:
            beats.append(self._details_in(det))
        if footer is not None:
            beats.append(self._footer_in(footer))
        target = None if footer is None else (footer.button or footer.qr)
        return beats, [self._breathe(target)]

    # -- split -------------------------------------------------------------------
    def _split_regions(self, share):
        lay, u = self.layout, self.u
        S, fw, fh = lay.safe, self.fw, self.fh
        margin = u * 6
        if lay.is_landscape:
            panel = Region(-fw / 2, -fw / 2 + fw * share, fh / 2, -fh / 2)
            T = Region(panel.right + margin, S.right, S.top, S.bottom)
        else:
            panel = Region(-fw / 2, fw / 2, fh / 2, fh / 2 - fh * share)
            T = Region(S.left, S.right, panel.bottom - margin, S.bottom)
        P = Region(max(panel.left, S.left), min(panel.right, S.right), min(panel.top, S.top),
                   max(panel.bottom, S.bottom))
        P = Region(P.left, P.right - margin, P.top, P.bottom) if lay.is_landscape else \
            Region(P.left, P.right, P.top, P.bottom + margin * 0.6)
        return panel, T, P

    def _split(self):
        p, pal, lay, m, u = self.p, self.pal, self.layout, self.motion, self.u
        portrait, land = lay.is_portrait, lay.is_landscape
        n = len(self.details)
        margin = u * 6
        if land:
            shares = [0.46, 0.40]
        elif portrait:
            shares = [0.42, 0.36]
        else:
            shares = [0.40, 0.33, 0.28] if lay.aspect < 0.9 else [0.36, 0.30, 0.26]
        levels = [dict(detail=30, kicker=28, cta=30, qr=21 if portrait else 19, gap=4.0),
                  dict(detail=27, kicker=26, cta=28, qr=18, gap=3.2),
                  dict(detail=24, kicker=24, cta=26, qr=16, gap=2.4)]
        head_max = 76 if portrait else (66 if land else 58)

        def candidate(share, lv):
            panel, T, P = self._split_regions(share)
            qr_side, region = None, T
            if T.width / max(T.height, 1e-6) > 1.45 and p.qr_text:
                qs = min(T.height * 0.62, T.width * 0.3)
                qr_side = self._qr(qs)
                if qr_side is not None:
                    region = Region(T.left, T.right - qs - margin * 0.8, T.top, T.bottom)
                    qr_side.move_to([T.right - qs / 2, T.bottom + qs / 2, 0])
            W = region.width
            kick = B.kicker(p.kicker, pal, max_width=W, size=lv["kicker"], style="bar") if p.kicker else None
            det = B.details_block(self.details, pal, width=W, size=lv["detail"], columns=1, chips=False,
                                  align="left") if n else None
            if qr_side is None:
                footer = self._footer(W, qr_size=u * lv["qr"], cta_size=lv["cta"], button_fill=pal.accent,
                                      button_color=pal.on_accent)
            else:
                btn = B.button(p.call_to_action, pal, max_width=W, size=lv["cta"], fill=pal.accent,
                               color=pal.on_accent) if p.call_to_action else None
                footer = self._footer_group(button=btn)
                if footer is not None:
                    footer.cut = btn.cut
            if any(x is not None and x.cut for x in (kick, det, footer)):
                return None
            logo = self._logo(u * 7, W * 0.5)
            fixed = [x for x in (logo, kick, det, footer) if x is not None]
            count = len(fixed) + (1 if p.headline else 0)
            gap = u * lv["gap"]
            flex = region.height - sum(x.height for x in fixed) - gap * (count - 1)
            need = max(self._head_min(W, 3, "left", min_size=32), u * 4)
            return dict(panel=panel, P=P, region=region, qr_side=qr_side, logo=logo, kick=kick, det=det,
                        footer=footer, gap=gap, flex=flex, need=need)

        c = self._pick(candidate(share, lv) for share in shares for lv in levels)
        panel, P, region, qr_side = c["panel"], c["P"], c["region"], c["qr_side"]
        logo, kick, det, footer, gap, flex = c["logo"], c["kick"], c["det"], c["footer"], c["gap"], c["flex"]
        W = region.width
        head = B.headline(p.headline, pal, width=W, height=max(flex, c["need"]), size=head_max, min_size=32,
                          max_lines=3, align="left") if p.headline else None
        self._stack([logo, kick, head, det, footer], [0, gap * 0.8, gap * 0.6, gap, gap * 1.1], region,
                    align="left", max_extra=gap * 1.2)

        # -- the panel: photo (with the big text on a sticker) or a color field carrying the big text
        photo = sticker = panel_big = rings = None
        if self.photo:
            try:
                photo = B.photo_cover(self.photo, width=panel.width, height=panel.height)
                photo.move_to(panel.center)
            except Exception:  # an unreadable upload falls back to the color panel
                photo = None
        fill = Rectangle(width=panel.width, height=panel.height).set_fill(pal.accent, 1).set_stroke(width=0)
        fill.move_to(panel.center)
        if photo is not None:
            fill.set_z_index(1)  # the color block covers the photo, then opens
            if p.big_text:
                d = max(min(P.width, P.height) * (0.42 if land else 0.5), u * 22)
                d = min(d, P.width, P.height)
                sticker = B.sticker(p.big_text, pal, diameter=d, fill=pal.accent, color=pal.on_accent)
                sticker.rotate(-8 * DEG)
                sticker.move_to([P.right - d / 2, P.bottom + d / 2, 0])
                sticker.set_z_index(5)
        else:
            if self.decorate:
                rr = max(panel.width, panel.height) * 0.8
                raw = B.rings(rr, count=6, color=pal.on_accent, opacity=0.12, thickness=u * 0.9)
                raw.move_to([panel.right - panel.width * 0.12, panel.bottom + panel.height * 0.18, 0])
                rings = B.clip_to(raw, fill.copy(), pal.on_accent, 0.12)
            if p.big_text:
                inner = Region(P.left + u * 2, P.right - u * 2, P.top - u * 2, P.bottom + u * 2)
                panel_big = B.big_type(p.big_text, pal, width=inner.width, height=inner.height * 0.62,
                                       color=pal.on_accent)
                panel_big.move_to(inner.center)

        # -- beats
        beats = []
        edge = LEFT if land else UP
        if photo is not None:
            beats.append(B.grow_width(fill, run_time=m.t(0.5), edge=edge))
            beats.append(AnimationGroup(FadeIn(photo, scale=1.06, run_time=m.t(0.8), rate_func=B.QUART),
                                        self._collapse(fill, edge=-edge, run_time=m.t(0.6))))
        else:
            reveal = [B.grow_width(fill, run_time=m.t(0.55), edge=edge)]
            if rings is not None:
                reveal.append(FadeIn(rings, scale=0.9, run_time=m.t(0.9), rate_func=B.QUART))
            beats.append(self._under(LaggedStart(*reveal, lag_ratio=0.3), [fill, rings]))
        intro = self._intro(logo, kick, head, "left")
        if intro:
            beats.append(LaggedStart(*intro, lag_ratio=0.3))
        if panel_big is not None:
            beats.append(B.slam_chars(panel_big, run_time=m.t(0.4), lag=m.t(0.06), scale=1.8))
        if sticker is not None:
            beats.append(self._spin_in(sticker, run_time=m.t(0.6)))
        if det is not None:
            beats.append(self._details_in(det))
        last = []
        if footer is not None:
            last.append(self._footer_in(footer, anchor="left"))
        if qr_side is not None:
            last.append(self._qr_in(qr_side))
        if last:
            beats.append(LaggedStart(*last, lag_ratio=0.3))
        target = (footer.button or footer.qr) if footer is not None else qr_side
        return beats, [self._breathe(target)]

    @staticmethod
    def _under(beat, mobs):
        """Mark *mobs* to be layered right above the background when *beat* plays."""
        beat.under = [x for x in (mobs or []) if x is not None]
        return beat

    @staticmethod
    def _collapse(block, *, edge, run_time):
        """The reverse of grow_width: the block shrinks toward *edge* and leaves."""
        target = block.copy()
        dim = 1 if abs(edge[1]) > 0 else 0

        def update(mob, alpha):
            k = max(1 - B.QUART(alpha), 0.002)
            mob.become(target.copy().stretch(k, dim, about_edge=edge))

        return UpdateFromAlphaFunc(block, update, run_time=run_time, remover=True)

    def _spin_in(self, mob, *, run_time):
        target = mob.copy()
        center = mob.get_center()

        def update(m, alpha):
            a = B.BACK(alpha)
            m.become(target.copy())
            m.scale(max(0.3 + 0.7 * a, 0.01), about_point=center)
            m.rotate((1 - a) * 40 * DEG, about_point=center)
            if alpha < 0.25:
                m.fade(1 - alpha * 4)

        return UpdateFromAlphaFunc(mob, update, run_time=run_time)

    # -- poster (ticket) ----------------------------------------------------------
    def _poster(self):
        p, pal, lay, m, u = self.p, self.pal, self.layout, self.motion, self.u
        S, fw, fh = lay.safe, self.fw, self.fh
        portrait, land = lay.is_portrait, lay.is_landscape
        n = len(self.details)
        vertical = not land
        C = S
        pad = u * (3 if lay.is_square else 6)
        notch = u * 4.5
        head_max = 80 if portrait else (66 if land else 58)
        levels = [dict(detail=30, kicker=26, gap=4.0), dict(detail=27, kicker=24, gap=3.2),
                  dict(detail=24, kicker=24, gap=2.4)]
        # The stub's share of the card: vertical tickets size it to what the main part needs.
        stub_min = 0.24 if portrait else 0.32
        stub_max = 0.30 if portrait else 0.40

        def main_region(split):
            if vertical:
                perf_y = C.top - C.height * split
                return Region(C.left + pad, C.right - pad, C.top - pad, perf_y + pad * 0.8)
            perf_x = C.left + C.width * split
            return Region(C.left + pad, perf_x - pad * 0.8, C.top - pad, C.bottom + pad)

        def candidate(lv, cols):
            M = main_region(1 - (stub_max if vertical else 0.34))
            W = M.width
            kick = B.kicker(p.kicker, pal, max_width=W, size=lv["kicker"]) if p.kicker else None
            det = B.details_block(self.details, pal, width=W, size=lv["detail"], columns=min(cols, max(n, 1)),
                                  chips=False, align="left") if n else None
            if any(x is not None and x.cut for x in (kick, det)):
                return None
            logo = self._logo(u * 7, W * 0.45)
            fixed = [x for x in (logo, kick, det) if x is not None]
            count = len(fixed) + (1 if p.headline else 0)
            gap = u * lv["gap"]
            head_min = self._head_min(W, 3, "left", emphasis=pal.accent_on_surface, min_size=32)
            content = sum(x.height for x in fixed) + gap * (count - 1) + head_min
            if vertical:
                main_h = content + pad * 1.8
                stub = 1 - main_h / C.height
                split = 1 - min(stub_max, stub)
                flex = stub - stub_min  # spare share of the card
                need = 0.0
            else:
                split = 0.66
                flex = main_region(split).height - (content - head_min)
                need = head_min
            return dict(lv=lv, cols=cols, kick=kick, det=det, logo=logo, gap=gap, split=split, flex=flex,
                        need=need)

        plan = [(lv, 1) for lv in levels] + ([(levels[2], 2)] if n > 2 else [])
        c = self._pick(candidate(lv, cols) for lv, cols in plan)
        split, gap = c["split"], c["gap"]
        logo, kick, det = c["logo"], c["kick"], c["det"]
        if vertical:
            split = max(split, 1 - stub_max)
            split = min(split, 1 - stub_min * 0.85)
        M = main_region(split)

        card = B.ticket(C.width, C.height, split=split, vertical=vertical, notch=notch,
                        radius=max(pal.radius * 1.6, u * 1.5), color=pal.surface, stroke=pal.line)
        card.move_to(C.center)
        shadow = card.copy().set_fill(pal.text, 0.10).set_stroke(width=0).shift(RIGHT * u * 1.2 + DOWN * u * 1.8)
        if vertical:
            perf_y = C.top - C.height * split
            perf = B.perforation([C.left + notch * 1.5, perf_y, 0], [C.right - notch * 1.5, perf_y, 0],
                                 color=pal.line, dash=u * 2.2)
            ST = Region(C.left + pad, C.right - pad, perf_y - pad * 0.8, C.bottom + pad)
        else:
            perf_x = C.left + C.width * split
            perf = B.perforation([perf_x, C.top - notch * 1.5, 0], [perf_x, C.bottom + notch * 1.5, 0],
                                 color=pal.line, dash=u * 2.2)
            ST = Region(perf_x + pad * 0.8, C.right - pad, C.top - pad, C.bottom + pad)

        # -- the main part: logo, kicker, headline, details
        W = M.width
        fixed_h = sum(x.height for x in (logo, kick, det) if x is not None)
        count = sum(1 for x in (logo, kick, det) if x is not None) + (1 if p.headline else 0)
        flex = M.height - fixed_h - gap * (count - 1)
        head = B.headline(p.headline, pal, width=W, height=max(flex, u * 6), size=head_max, min_size=32,
                          max_lines=3, align="left", emphasis=pal.accent_on_surface) if p.headline else None
        self._stack([logo, kick, head, det], [0, gap * 0.8, gap * 0.6, gap * 1.2], M, align="left",
                    max_extra=gap * 1.3)

        # -- the stub: big text, call to action, QR (the call to action is never cut; the big text gives way)
        qr = big = cta = None
        if vertical:
            qr = self._qr(min(ST.height, ST.width * 0.38))
            left = Region(ST.left, ST.right - (qr.width + pad * 0.8 if qr is not None else 0), ST.top, ST.bottom)
            if p.call_to_action:
                cta = fit_text(p.call_to_action, width=left.width, size=30 if p.big_text else 40, min_size=24,
                               max_lines=3, font=pal.font, weight="BOLD", color=pal.text,
                               align="left" if qr is not None else "center", line_spacing=1.08)
                B.shrink_to(cta, left.width)
            if p.big_text:
                room = left.height - (cta.height + u * 3 if cta is not None else 0)
                big = B.big_type(p.big_text, pal, width=left.width, height=max(room, u * 6),
                                 color=pal.accent_on_surface, align="left" if qr is not None else "center",
                                 allow_two=False)
            if qr is not None:
                qr.move_to([ST.right - qr.width / 2, ST.center[1], 0])
            self._stack([big, cta], [0, u * 3], left if qr is not None else ST,
                        align="left" if qr is not None else "center", max_extra=u * 2)
        else:
            if p.call_to_action:
                cta = fit_text(p.call_to_action, width=ST.width, size=30, min_size=24, max_lines=3, font=pal.font,
                               weight="BOLD", color=pal.text, line_spacing=1.08)
                B.shrink_to(cta, ST.width)
            cta_h = cta.height if cta is not None else 0
            qr = self._qr(min(ST.width * 0.78, (ST.height - cta_h) * 0.55))
            if p.big_text:
                used = (qr.height if qr is not None else 0) + cta_h
                big = B.big_type(p.big_text, pal, width=ST.width, height=max(ST.height - used - u * 9, u * 7),
                                 color=pal.accent_on_surface, max_cap=ST.height * 0.22)
            self._stack([big, qr, cta], [0, u * 4.5, u * 4.5], ST, align="center", max_extra=u * 4)

        deco = None
        if self.decorate:
            deco = B.dot_grid(fw * 1.05, fh * 1.05, step=u * 6, radius=u * 0.55, color=pal.line, opacity=0.9)

        # -- beats
        beats = []
        deal = []
        if deco is not None:
            deal.append(FadeIn(deco, run_time=m.t(0.6)))
        ticket = VGroup(shadow, card)
        deal.append(self._deal_in(ticket, run_time=m.t(0.8)))
        deal.append(B.grow_width(perf, run_time=m.t(0.45), edge=LEFT if vertical else UP))
        beats.append(self._under(LaggedStart(*deal, lag_ratio=0.3), [deco, ticket, perf]))
        intro = self._intro(logo, kick, head, "left")
        if intro:
            beats.append(LaggedStart(*intro, lag_ratio=0.3))
        if det is not None:
            beats.append(self._details_in(det))
        stub = []
        if big is not None:
            stub.append(B.slam_chars(big, run_time=m.t(0.4), lag=m.t(0.06), scale=1.8))
        if qr is not None:
            stub.append(self._qr_in(qr))
        if cta is not None:
            stub.append(B.rise_words(cta, unit=u, run_time=m.t(0.5), lag=m.t(0.04), distance=0.6))
        if stub:
            beats.append(LaggedStart(*stub, lag_ratio=0.3))
        return beats, [self._breathe(qr)]


    def _deal_in(self, ticket, *, run_time):
        """The card slides up from below with a small turn, like a ticket being handed over."""
        u = self.u
        target = ticket.copy()
        center = ticket.get_center()

        def update(m, alpha):
            m.become(target.copy())
            if alpha >= 1:
                return
            settle = B.rate_functions.ease_out_back(alpha)
            m.rotate((1 - B.QUART(alpha)) * -6 * DEG, about_point=center)
            m.shift(DOWN * (1 - settle) * u * 30)
            fade = min(1.0, alpha * 3)
            m[0].set_fill(opacity=0.10 * fade)
            m[1].set_fill(opacity=fade).set_stroke(opacity=fade)

        return UpdateFromAlphaFunc(ticket, update, run_time=run_time)
