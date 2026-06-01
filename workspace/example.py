from manim import *

class SquareToCircle(Scene):
    def construct(self):
        # Create shapes
        circle = Circle(color=PINK)
        square = Square(color=BLUE)
        square.flip(RIGHT)
        square.rotate(PI / 8)

        # Show shapes
        self.play(Create(square))
        self.play(Transform(square, circle))
        self.play(FadeOut(square))

class WriteFormula(Scene):
    def construct(self):
        # Create standard Text elements. 
        # (Using Text instead of MathTex because LaTeX isn't installed locally)
        title = Text("Manim Video Editor", font_size=40, color=YELLOW)
        subtitle = Text("Render math and animations cleanly", font_size=28, color=WHITE)
        
        # Position them
        title.shift(UP * 0.8)
        subtitle.next_to(title, DOWN)

        # Draw them
        self.play(Write(title))
        self.play(FadeIn(subtitle, shift=UP))
        self.wait(1.5)
        self.play(FadeOut(title), FadeOut(subtitle))
