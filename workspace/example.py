from manim import *



class VectorWarpScene(Scene):

    def construct(self):

        # 1. Title Sequence

        title = Tex(r"Mathematical Fluid Flows").scale(1.2).to_edge(UP)

        self.play(Write(title))

        self.wait(0.5)



        # 2. Define a non-linear vector field function (Vortex/Saddle mix)

        def flow_func(pos):

            x, y = pos[0], pos[1]

            return np.array([

                np.sin(y), 

                np.cos(x) - 0.5 * y, 

                0

            ])



        # 3. Add an aesthetic background grid

        grid = NumberPlane(

            background_line_style={

                "stroke_color": GRAY_D,

                "stroke_width": 1,

                "stroke_opacity": 0.4

            }

        )

        self.play(FadeIn(grid, run_time=1.5))



        # 4. Create high-tech moving StreamLines

        stream_lines = StreamLines(

            flow_func,

            x_range=[-7, 7],

            y_range=[-4, 4],

            stroke_width=2,

            max_anchors_per_line=40,

            color=TEAL_A

        )

        

        # 5. Morph Title into the Vector Formula

        formula = MathTex(

            r"\vec{F}(x,y) = \begin{bmatrix} \sin(y) \\ \cos(x) - \frac{1}{2}y \end{bmatrix}"

        ).to_edge(UP).scale(0.9)

        

        self.play(

            ReplacementTransform(title, formula),

            FadeIn(stream_lines)

        )

        

        # Continuous background fluid motion animation

        stream_lines.start_animation(warm_up=True, flow_speed=1.2)

        

        # 6. Morphing geometric focal point

        circle = Circle(radius=1.5, color=PURPLE_A).set_stroke(width=4)

        square = Square(side_length=2.5, color=ORANGE).rotate(PI / 4)

        

        self.play(Create(circle), run_time=2)

        self.wait(1)

        self.play(Transform(circle, square), run_time=2)

        self.wait(3)

        

        # Smooth Outro Out

        self.play(

            FadeOut(circle),

            FadeOut(formula),

            FadeOut(grid),

            FadeOut(stream_lines),

            run_time=1.5

        )