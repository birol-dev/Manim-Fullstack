class CodeCardTemplate(Scene):
    def construct(self):
        code_str = (
            "def calculate_trajectory(pos, vel):\n"
            "    gravity = -9.81\n"
            "    return pos + vel * dt + 0.5 * gravity * (dt ** 2)"
        )
        snippet = Code(
            code_string=code_str,
            language="python",
            formatter_style="monokai",
            background="window",
            insert_line_no=True,
            font="Monospace",
            scale_factor=0.8
        )
        self.play(FadeIn(snippet, shift=UP * 0.3))