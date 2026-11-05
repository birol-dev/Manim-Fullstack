from manim import (
    BOLD, DOWN, LEFT, RIGHT, UP, Arrow, Create, FadeIn, Line,
    RoundedRectangle, Scene, Text, VGroup, VMobject,
)

TITLE = "Follow the index"  # studio: Headline
ACCENT = "#8BE2B4"  # studio: Lookup color


class IndexLookup(Scene):
    """Follow one key from the index to its row in a simplified table."""

    def construct(self):
        background, panel, border = "#111719", "#182124", "#364547"
        ink, muted, amber, mint = "#F3EEE1", "#A7B6B1", "#EFC475", ACCENT
        self.camera.background_color = background

        def text(value, size, color=ink, *, mono=False, bold=False):
            return Text(value, font="monospace" if mono else "sans-serif", font_size=size,
                        weight=BOLD if bold else "NORMAL", color=color)

        def left_text(value, x, y, size, color=ink, **style):
            return text(value, size, color, **style).move_to([x, y, 0], aligned_edge=LEFT)

        def card(width, height, x, y, *, fill=panel):
            return RoundedRectangle(width=width, height=height, corner_radius=.12,
                                    fill_color=fill, fill_opacity=1, stroke_color=border,
                                    stroke_width=1.5).move_to([x, y, 0])

        def node(label, x, y, width):
            box = card(width, .64, x, y, fill=background)
            return VGroup(box, text(label, 20, mono=True).move_to(box))

        # Establish the same query, index, and table for the whole shot.
        title = text(TITLE or "Follow the index", 48, bold=True)
        if title.width > 7.6:
            title.scale_to_fit_width(7.6)
        title.move_to([-6.42, 2.83, 0], aligned_edge=LEFT)
        header = VGroup(
            left_text("DATABASE NOTES    /    01", -6.42, 3.45, 17, amber, mono=True),
            title,
            Line([-6.42, 2.30, 0], [6.42, 2.30, 0], color=border, stroke_width=1.5),
            text("WHERE id = 42", 23, mint, mono=True).move_to([4.72, 2.86, 0]),
        )
        index = card(5.95, 4.85, -3.43, -.38)
        table = card(6.53, 4.85, 3.15, -.38)
        labels = VGroup(left_text("01   SORTED INDEX", -6.08, 1.62, 17, amber, mono=True),
                        left_text("02   TABLE ROWS", .30, 1.62, 17, amber, mono=True))
        root = node("30  |  60", -3.43, .82, 2.0)
        leaves = [node(label, x, -1.02, 1.53) for label, x in
                  zip(("10  22", "35  42", "62  78"), (-5.24, -3.43, -1.62))]
        edges = [Line(root.get_bottom(), leaf.get_top(), color=border, stroke_width=2) for leaf in leaves]
        rows = VGroup()
        for i, (key, name) in enumerate(((62, "Relay"), (10, "Paper"), (42, "Atlas"), (35, "Raster"))):
            y = .90 - i * .63
            slab = card(5.64, .52, 3.22, y, fill=background)
            rows.add(VGroup(slab, left_text(str(key), .73, y, 20, muted, mono=True),
                            left_text(name, 1.95, y, 24)))

        self.add(header, index, table, labels, rows)
        self.play(FadeIn(root, shift=DOWN * .10), run_time=.55)
        self.play(*(Create(edge) for edge in edges), *(FadeIn(leaf) for leaf in leaves), run_time=.75)
        self.wait(.40)

        # Resolve the comparison and keep the rejected paths visible at lower contrast.
        comparison = text("30 ≤ 42 < 60", 17, mint, mono=True).move_to([-2.18, -.02, 0])
        self.play(root[0].animate.set_stroke(mint, width=2),
                  edges[1].animate.set_stroke(mint, width=3),
                  leaves[1][0].animate.set_stroke(mint, width=2).set_fill("#20342D"),
                  VGroup(leaves[0], leaves[2], edges[0], edges[2]).animate.set_opacity(.42),
                  FadeIn(comparison, shift=RIGHT * .12), run_time=.85)
        self.wait(.45)

        # Route around the other leaves to the exact row the leaf points at.
        start = leaves[1].get_bottom()
        target = rows[2][0].get_left()
        route = VMobject(stroke_color=mint, stroke_width=3).set_points_as_corners(
            [start, [start[0], -1.84, 0], [.13, -1.84, 0], [.13, target[1], 0]],
        )
        tip = Arrow([.13, target[1], 0], target, buff=0, color=mint, stroke_width=3,
                    max_tip_length_to_length_ratio=.40)
        self.play(Create(route), run_time=.75)
        self.play(Create(tip), rows[2][0].animate.set_stroke(mint, width=2).set_fill("#20342D"),
                  rows[2][1].animate.set_color(mint), run_time=.50)
        result = left_text("MATCH  /  ONE ROW FETCHED", -6.42, -3.20, 20, mint, mono=True)
        self.play(FadeIn(result, shift=UP * .10), run_time=.4)
        self.wait(1.8)
