from manim import *


class SquareToCircle(Scene):
    """The classic first Manim scene: a square morphs into a circle."""

    def construct(self):
        square = Square(side_length=3, color=BLUE).rotate(PI / 4)
        circle = Circle(radius=1.5, color=PINK).set_fill(PINK, opacity=0.35)

        self.play(Create(square))
        self.play(Transform(square, circle))
        self.wait(0.5)
        self.play(FadeOut(square))


class TitleCard(Scene):
    """Animated title text. Text() uses Pango, so it works without LaTeX."""

    def construct(self):
        title = Text("Manim Composer", font_size=64, weight=BOLD)
        underline = Underline(title, color=BLUE, buff=0.2)
        subtitle = Text("Write a scene. Press render.", font_size=30, color=GRAY_B)
        subtitle.next_to(underline, DOWN, buff=0.5)

        self.play(Write(title))
        self.play(Create(underline), FadeIn(subtitle, shift=UP * 0.3))
        self.wait(1)
        self.play(FadeOut(VGroup(title, underline, subtitle), shift=DOWN * 0.3))


class SineWave(Scene):
    """Plot a function on axes and trace it with a moving dot."""

    def construct(self):
        axes = Axes(
            x_range=[0, 2 * PI, PI / 2],
            y_range=[-1.5, 1.5, 0.5],
            x_length=10,
            y_length=4,
            tips=False,
        )
        curve = axes.plot(np.sin, color=YELLOW)
        dot = Dot(axes.c2p(0, 0), color=YELLOW)

        self.play(Create(axes))
        self.play(Create(curve), MoveAlongPath(dot, curve), run_time=3, rate_func=linear)
        self.wait(0.5)
