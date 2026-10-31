"""The quiz layout planner: sizes and positions for every aspect, computed from the content.

Order top to bottom: label pill, question, answers, and a bottom zone that holds the timer
ring while people think and the explanation after the reveal. Text sizes and spacing shrink
together until the stack fits; leftover height goes to taller answer cards and breathing
room around the question. It measures text with the kit's ``wrap`` (no Manim objects are
built), mirroring what ``fit_text`` will do with the same width and size.
"""

from __future__ import annotations

from dataclasses import dataclass

from .helpers import EXPLANATION_SPACING, slot_diameter, fit_size, line_height, lines_at


@dataclass
class Plan:
    ring: float                # timer ring diameter
    pill_h: float              # label pill height (0 without a label)
    head_y: float              # label center y
    bottom_h: float            # height of the bottom zone: the timer, later the explanation
    bottom_y: float            # its center y
    badge_d: float             # diameter of the check badge inside the explanation panel
    e_gap: float
    q_size: float
    q_width: float
    q_lines: int
    q_center_y: float
    opt_size: float
    cols: int
    rows: int
    card_w: float
    card_h: float
    gap: float
    slot_d: float
    pad_l: float
    pad_r: float
    text_w: float
    opt_lines: int
    opt_top: float
    e_size: float
    e_lines: int
    e_w: float
    e_text_w: float
    e_h: float
    letter_size: float
    overflow: float            # > 0: the content does not fit even at the smallest sizes


def plan_layout(lay, R, theme, *, question: str, options: list, explanation: str, has_label: bool) -> Plan:
    unit = lay.unit
    font = theme.font
    qw, ow, ew = theme.display_weight, "SEMIBOLD", "NORMAL"
    n = len(options)
    tall = lay.aspect < 0.7  # 9:16

    if lay.is_landscape:
        q_max, o_max, e_max, ring = 76.0, 46.0, 32.0, 1.2
    elif lay.is_square:
        q_max, o_max, e_max, ring = 78.0, 42.0, 32.0, 1.1
    else:
        q_max, o_max, e_max, ring = (80.0, 46.0, 34.0, 1.4) if tall else (72.0, 40.0, 32.0, 1.2)
    q_min, o_min, e_min = 24.0, 24.0, 24.0
    e_lines_max = 2 if lay.is_landscape else 4

    e_width = R.width
    badge_d = unit * 8.4
    e_gap = unit * 3.2

    # Answer layouts in order of preference: (columns, max lines per answer).
    if lay.is_landscape:
        grids = {2: [2], 3: [3], 4: [2]}[n]
    elif lay.is_square or lay.aspect >= 0.7:  # 1:1 and 4:5
        grids = [2]
    else:
        grids = []
    variants = [(c, 2) for c in grids] + [(1, 3)] + [(c, lines) for lines in (3, 4) for c in grids]

    def at(k: float, variant: tuple, *, dense: bool = False) -> dict:
        cols, max_lines = variant
        # A dense plan is the last resort for maximum-length text: less padding, tighter
        # spacing and a smaller size floor. A plan that already fits is never replaced.
        s = max(0.30 if dense else 0.4, k)  # spacing scale: tightens together with the text
        low = 18.0 if dense else 24.0
        qs, os_, es = max(low, q_max * k), max(low, o_max * k), max(low, e_max * k)
        d = dict(k=k, qs=qs, es=es)
        d["ring"] = ring * max(0.60 if dense else 0.85, s)
        d["pill_h"] = unit * 6.6 if has_label else 0.0
        d["g_head"] = unit * 4.0 * s if has_label else 0.0
        d["g_opts"], d["g_exp"], gap = unit * 4.5 * s, unit * 3.0 * s, unit * 2.8 * max(0.7, s)
        tight = max(0.5, s)
        squeeze = 0.55 if dense else 1.0
        pad_l, pad_r, slot_gap = unit * 3.2 * tight * squeeze, unit * 3.4 * tight * squeeze, unit * 3.2 * tight * squeeze
        pad_v = unit * 3.0 * s * squeeze
        d["pad_l"], d["pad_r"], d["gap"] = pad_l, pad_r, gap

        # question
        q_width = R.width * (1.0 if dense else 0.96)
        d["q_width"] = q_width
        d["q_lines"] = lines_at(question, q_width, qs, font, qw)
        d["q_h"] = d["q_lines"] * line_height(qs, font, qw, 1.0)

        # answers
        letter = max(20.0 if dense else 24.0, min(40.0, os_ * 0.85))
        slot = slot_diameter(letter, font)
        card_w = (R.width - (cols - 1) * gap) / cols
        text_w = card_w - pad_l - slot - slot_gap - pad_r
        uniform = min(fit_size(o, text_w, os_, low, max_lines, font, ow)[0] for o in options)
        lines = max(lines_at(o, text_w, uniform, font, ow) for o in options)
        cut = lines > max_lines  # even the smallest size needs more lines than allowed: it would be trimmed
        lines = min(lines, max_lines)
        rows = -(-n // cols)
        card_h = max(slot + unit * 4.6 * s, lines * line_height(uniform, font, ow, 1.0) + 2 * pad_v,
                     unit * 12.0 * max(0.8, s))
        d["opts"] = dict(cols=cols, rows=rows, card_w=card_w, card_h=card_h, text_w=text_w, size=uniform,
                         lines=lines, height=rows * card_h + (rows - 1) * gap)
        d["eligible"] = (not cut) and uniform >= os_ * 0.85  # text stays close to the target size, untrimmed
        d["slot"], d["letter"] = slot, letter

        # explanation
        d["e_text_w"] = e_width - 2 * unit * 3.6 - badge_d - e_gap
        if explanation:
            size, lines = fit_size(explanation, d["e_text_w"], es, low, e_lines_max, font, ew)
            d["e_size"], d["e_lines"] = size, lines
            d["e_h"] = max(lines * line_height(size, font, ew, EXPLANATION_SPACING) + 2 * unit * 2.4 * s,
                           badge_d + unit * 3.0 * s)
        else:
            d["e_size"], d["e_lines"], d["e_h"] = es, 0, 0.0
        d["bottom_h"] = max(d["ring"], d["e_h"])
        d["total"] = (d["pill_h"] + d["g_head"] + d["q_h"] + d["g_opts"] + d["opts"]["height"] + d["g_exp"]
                      + d["bottom_h"])
        d["floor"] = d["qs"] <= low and d["opts"]["size"] <= low and d["es"] <= low
        return d

    # Largest text first; at each size the first (preferred) answer layout that fits wins.
    k, d = 1.0, None
    while d is None:
        tried = []
        for variant in variants:
            t = at(k, variant)
            tried.append(t)
            if t["eligible"] and t["total"] <= R.height:
                d = t
                break
        if d is None and (tried[0]["floor"] or k < 0.2):
            pool = [t for t in tried if t["eligible"]] or tried  # nothing fits: take the least overflow
            d = min(pool, key=lambda t: t["total"])
        k *= 0.94

    if d["total"] > R.height or not d["eligible"]:
        # Maximum-length content: try the same layouts with less padding and a smaller
        # size floor. This never replaces a plan that already fits, so normal content
        # renders exactly as before.
        best, k = None, 1.0
        while k >= 0.15:
            candidates = [at(k, variant, dense=True) for variant in variants]
            fitting = [t for t in candidates if t["eligible"] and t["total"] <= R.height]
            if fitting:
                best = fitting[0]
                break
            pool = [t for t in candidates if t["eligible"]] or candidates
            candidate = min(pool, key=lambda t: t["total"])
            if best is None or candidate["total"] < best["total"]:
                best = candidate
            k *= 0.86
        if best is not None and (best["total"] < d["total"] or (best["eligible"] and not d["eligible"])):
            d = best

    opts = d["opts"]
    free = max(0.0, R.height - d["total"])
    cap = opts["card_h"] * (0.9 if opts["rows"] == 1 else (0.7 if tall else 0.45))
    grow = min(cap, free * 0.5 / opts["rows"])
    free -= grow * opts["rows"]
    card_h = opts["card_h"] + grow

    head_y = R.top - d["pill_h"] / 2
    y = R.top - d["pill_h"] - d["g_head"]
    q_zone = d["q_h"] + free
    q_center = y - q_zone / 2
    y -= q_zone + d["g_opts"]

    return Plan(
        ring=d["ring"], pill_h=d["pill_h"], head_y=head_y, bottom_h=d["bottom_h"],
        bottom_y=R.bottom + d["bottom_h"] / 2, badge_d=badge_d, e_gap=e_gap,
        q_size=d["qs"], q_width=d["q_width"], q_lines=d["q_lines"], q_center_y=q_center,
        opt_size=opts["size"], cols=opts["cols"], rows=opts["rows"], card_w=opts["card_w"], card_h=card_h,
        gap=d["gap"], slot_d=d["slot"], pad_l=d["pad_l"], pad_r=d["pad_r"], text_w=opts["text_w"],
        opt_lines=opts["lines"], opt_top=y, e_size=d["e_size"], e_lines=d["e_lines"], e_w=e_width,
        e_text_w=d["e_text_w"], e_h=d["e_h"], letter_size=d["letter"], overflow=max(0.0, d["total"] - R.height),
    )
