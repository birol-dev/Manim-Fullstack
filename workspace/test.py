from manim import *

class NewScene(Scene):
    def construct(self):
        text = Text("New Project", font_size=36)
        self.play(Write(text))
        self.wait(1)
        self.play(FadeOut(text))
