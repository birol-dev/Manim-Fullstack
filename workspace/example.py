from manim import *

class SquareToCircle(Scene):
    def construct(self):
         circle = Circle()
 square =     Square ()
        # Show shapes
        self.play(Create(square))
        self.play(Transform(square, circle))
        self.play(FadeOut(square))

