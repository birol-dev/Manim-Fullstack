"""One animation that runs a whole post's choreography.

A quote has dozens of small things coming in at their own moment (words, stars, a
name). Playing one Manim animation per word is slow and clumsy to schedule, so this
is a single ``Animation`` over the whole post: every ``Piece`` has a start time, a
duration and an effect, plus an optional emphasis pulse (a slight pop that also
turns the word to the accent color). Nothing is rebuilt per frame: pieces only
shift, scale and change opacity or color, and a piece that is finished is never
touched again.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
from manim import DOWN, LEFT, Animation, Group, ImageMobject, Mobject, ManimColor, VMobject, interpolate_color, linear

from studio.kit import ease_in_out, ease_out, overshoot


@dataclass
class Pulse:
    """A short emphasis: scale up a little and back, turning from *c_from* to *c_to*."""

    start: float
    dur: float
    amount: float
    c_from: str
    c_to: str


@dataclass
class Piece:
    """One thing that enters.

    effect: ``rise`` (fade + move up into place), ``fade``, ``slide`` (fade + move in from the left),
    ``pop`` (fade + scale from 60% with a little overshoot), ``dim`` (fade from *dim* up to full, used by
    the highlight sweep; the piece stays untouched before its start) or ``none`` (pulse only).
    """

    mob: Mobject
    start: float
    dur: float = 0.5
    effect: str = "rise"
    dist: float = 0.0  # travel for rise / slide, in frame units
    dim: float = 0.0   # opacity before a ``dim`` piece starts
    to: float = 1.0    # opacity the piece ends at
    pulse: Optional[Pulse] = None
    host: Optional[Mobject] = None  # what sits in the scene when this is a part of something bigger (a word in a line)

    @property
    def end(self) -> float:
        pulse_end = self.pulse.start + self.pulse.dur if self.pulse else 0.0
        return max(self.start + self.dur if self.effect != "none" else 0.0, pulse_end)

    def spans(self) -> list:
        """The time windows in which this piece changes something."""
        out = []
        if self.effect != "none":
            out.append((self.start, self.start + max(self.dur, 1e-3)))
        if self.pulse is not None:
            out.append((self.pulse.start, self.pulse.start + max(self.pulse.dur, 1e-3)))
        return out


def _snapshot(mob: Mobject):
    """The opacities a mobject was built with, so an entrance scales them instead of overwriting them
    (an empty star is 16% opaque, a photo ring has no fill, spaces between words are invisible)."""
    if isinstance(mob, ImageMobject):
        return ("image", mob.pixel_array.copy())
    return ("shapes", [(sm, float(sm.get_fill_opacity()), float(sm.get_stroke_opacity()))
                       for sm in mob.get_family() if isinstance(sm, VMobject)])


def _opacity(mob: Mobject, a: float, base) -> None:
    kind, data = base
    if kind == "image":  # keep the photo's own alpha shape (circle crop) and just scale it
        out = data.copy()
        out[..., 3] = (data[..., 3] * a).astype(data.dtype)
        mob.pixel_array = out
        return
    for sm, fill, stroke in data:
        sm.set_fill(opacity=fill * a, family=False)
        sm.set_stroke(opacity=stroke * a, family=False)


class Choreography:
    """The state of a whole post's entrance, played in time windows.

    Manim redraws every glyph of every animated mobject on every frame, which is slow for a paragraph. So
    each window animates only the things entering during it; whatever has finished sits in the scene as a
    still, and whatever has not started yet is not in the scene at all. ``play(a, b)`` plays the window
    [a, b]; consecutive windows play the whole thing, and the storyboard shows one frame per window."""

    def __init__(self, scene, pieces: list, content=()):
        self.scene = scene
        self.pieces = list(pieces)
        n = len(self.pieces)
        self.end = max((p.end for p in self.pieces), default=0.1)
        self._base = [_snapshot(p.mob) for p in self.pieces]  # as built, before any entrance touches them
        self._phase = [None] * n          # last applied entry progress
        self._color_phase = [None] * n    # last applied pulse progress
        self._offset = [np.zeros(3) for _ in range(n)]
        self._entry_scale = [1.0] * n     # the entry effect's own scale (pop)
        self._scale = [1.0] * n           # scale currently applied (entry x pulse)
        self._final = [False] * n
        # the things that sit in the scene, in order, with the time windows in which they change
        self.hosts, self._spans, seen = [], [], {}
        for piece in self.pieces:
            host = piece.host if piece.host is not None else piece.mob
            if id(host) not in seen:
                seen[id(host)] = len(self.hosts)
                self.hosts.append(host)
                self._spans.append([])
            self._spans[seen[id(host)]] += piece.spans()
        self._group = None
        self._still: set = set()  # ids of hosts already added to the scene as stills
        # anything in the layout that no piece animates is simply there from the start
        covered = {id(sm) for host in self.hosts for sm in host.get_family()}
        for item in content:
            for sm in item.get_family():
                if not sm.submobjects and id(sm) not in covered:
                    scene.add(sm)

    def play(self, start: float, end: float) -> None:
        scene = self.scene
        if self._group is not None:
            scene.remove(self._group)
        active = []
        for i, host in enumerate(self.hosts):
            spans = self._spans[i]
            if any(s < end and e > start for s, e in spans):
                active.append(host)
            elif spans and min(s for s, _ in spans) < start and id(host) not in self._still:
                scene.add(host)
                self._still.add(id(host))
        for host in active:  # moving again (or for the first time)
            if id(host) in self._still:
                scene.remove(host)
                self._still.discard(id(host))
        self._group = Group(*active)
        scene.add(self._group)
        scene.play(Segment(self, self._group, start, end))

    # -- the per-frame work ---------------------------------------------------
    def apply(self, t: float) -> None:
        for i, piece in enumerate(self.pieces):
            if self._final[i]:
                continue
            if piece.effect != "none":
                self._entry(i, piece, t)
            if piece.pulse is not None:
                self._pulse_color(i, piece, t)
            self._apply_scale(i, piece, t)
            self._final[i] = t >= piece.end

    def _entry(self, i: int, piece: Piece, t: float) -> None:
        if piece.effect == "dim" and t < piece.start:
            return  # untouched until its turn
        raw = (t - piece.start) / piece.dur if piece.dur > 0 else 1.0
        p = min(max(raw, 0.0), 1.0)
        if self._phase[i] == p:
            return
        self._phase[i] = p
        e = ease_out(p)
        kind = piece.effect
        offset, factor = 0.0, 1.0
        if kind == "dim":
            opacity = piece.dim + (piece.to - piece.dim) * e
        elif kind == "pop":
            opacity, factor = piece.to * min(1.0, p * 2.2), 0.6 + 0.4 * overshoot(p)
        elif kind == "fade":
            opacity = piece.to * e
        else:  # rise, slide
            opacity, offset = piece.to * min(1.0, p * 1.6), piece.dist * (1 - e)
        _opacity(piece.mob, opacity, self._base[i])
        shift = (LEFT if kind == "slide" else DOWN) * offset
        piece.mob.shift(shift - self._offset[i])
        self._offset[i] = shift
        self._entry_scale[i] = factor

    def _pulse_factor(self, piece: Piece, t: float) -> float:
        pulse = piece.pulse
        if pulse is None or t <= pulse.start or pulse.dur <= 0:
            return 1.0
        q = min((t - pulse.start) / pulse.dur, 1.0)
        return 1.0 + pulse.amount * math.sin(math.pi * ease_in_out(q))

    def _apply_scale(self, i: int, piece: Piece, t: float) -> None:
        factor = self._entry_scale[i] * self._pulse_factor(piece, t)
        if abs(factor - self._scale[i]) > 1e-4:
            piece.mob.scale(factor / self._scale[i])
            self._scale[i] = factor

    def _pulse_color(self, i: int, piece: Piece, t: float) -> None:
        pulse = piece.pulse
        q = 0.0 if pulse.dur <= 0 else min(max((t - pulse.start) / pulse.dur, 0.0), 1.0)
        if self._color_phase[i] == q:
            return
        self._color_phase[i] = q
        # glyphs are filled shapes; this changes color only (opacity belongs to the entry effect)
        piece.mob.set_color(interpolate_color(ManimColor(pulse.c_from), ManimColor(pulse.c_to), ease_in_out(q)))


class Segment(Animation):
    """One time window of a Choreography, as a Manim animation of the things that move in it."""

    def __init__(self, choreo: Choreography, group: Mobject, start: float, end: float):
        self.choreo, self.t_start, self.t_end = choreo, start, end
        super().__init__(group, rate_func=linear, run_time=max(end - start, 0.02))

    def create_starting_mobject(self):
        return Mobject()  # nothing to diff against; skips a deep copy of every glyph

    def interpolate_mobject(self, alpha: float) -> None:
        self.choreo.apply(self.t_start + alpha * (self.t_end - self.t_start))
