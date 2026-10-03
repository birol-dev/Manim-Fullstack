export interface SceneTemplate {
  id: string;
  title: string;
  description: string;
  category: string;
  filename: string;
  /** Requires a LaTeX install (MathTex / Tex). */
  needsLatex?: boolean;
  code: string;
}

export const SCENE_TEMPLATES: SceneTemplate[] = [
  {
    id: "square-to-circle",
    title: "Square to Circle",
    description: "The classic first scene: draw a square and morph it into a circle.",
    category: "Basics",
    filename: "square_to_circle.py",
    code: `from manim import *


class SquareToCircle(Scene):
    def construct(self):
        square = Square(side_length=3, color=BLUE).rotate(PI / 4)
        circle = Circle(radius=1.5, color=PINK).set_fill(PINK, opacity=0.35)

        self.play(Create(square))
        self.play(Transform(square, circle))
        self.wait(0.5)
        self.play(FadeOut(square))
`,
  },
  {
    id: "kinetic-title",
    title: "Kinetic Title",
    description: "Write a title, slide in a subtitle, and pulse a ring behind them.",
    category: "Text",
    filename: "kinetic_title.py",
    code: `from manim import *


class KineticTitle(Scene):
    def construct(self):
        ring = Circle(radius=2.6, color=BLUE_E, stroke_width=6)
        title = Text("MANIM COMPOSER", font_size=56, weight=BOLD)
        subtitle = Text("math animation, written in Python", font_size=28, color=GRAY_B)
        subtitle.next_to(title, DOWN, buff=0.4)

        self.play(Create(ring), run_time=1.2)
        self.play(Write(title))
        self.play(FadeIn(subtitle, shift=UP * 0.4))
        self.play(ring.animate.scale(1.25).set_stroke(opacity=0), run_time=1.5)
        self.wait(0.5)
        self.play(FadeOut(title, shift=LEFT), FadeOut(subtitle, shift=RIGHT))
`,
  },
  {
    id: "function-plot",
    title: "Function Plot",
    description: "Plot sine and cosine on axes with labels that don't need LaTeX.",
    category: "Graphs",
    filename: "function_plot.py",
    code: `from manim import *


class FunctionPlot(Scene):
    def construct(self):
        axes = Axes(
            x_range=[-PI, 2 * PI, PI / 2],
            y_range=[-1.5, 1.5, 0.5],
            x_length=11,
            y_length=5,
            tips=False,
        )
        sine = axes.plot(np.sin, color=BLUE)
        cosine = axes.plot(np.cos, color=YELLOW)
        sine_label = Text("sin x", font_size=28, color=BLUE).next_to(axes.c2p(2 * PI, 0), UR, buff=0.15)
        cosine_label = Text("cos x", font_size=28, color=YELLOW).next_to(axes.c2p(2 * PI, 1), UR, buff=0.15)

        self.play(Create(axes))
        self.play(Create(sine), Write(sine_label), run_time=2)
        self.play(Create(cosine), Write(cosine_label), run_time=2)
        self.wait(1)
`,
  },
  {
    id: "value-tracker",
    title: "Updaters",
    description: "Drive a rotating hand and a growing arc from one ValueTracker.",
    category: "Motion",
    filename: "updaters.py",
    code: `from manim import *


class AngleTracker(Scene):
    def construct(self):
        angle = ValueTracker(0)
        center = ORIGIN
        base = Line(center, RIGHT * 2.5, color=GREY)
        hand = always_redraw(
            lambda: Line(center, RIGHT * 2.5, color=BLUE).rotate(angle.get_value(), about_point=center)
        )
        arc = always_redraw(
            lambda: Arc(radius=0.8, angle=angle.get_value(), color=YELLOW, arc_center=center)
        )

        self.play(Create(base), Create(hand))
        self.add(arc)
        self.play(angle.animate.set_value(PI * 0.75), run_time=2, rate_func=smooth)
        self.play(angle.animate.set_value(PI / 6), run_time=1.5)
        self.wait(0.5)
`,
  },
  {
    id: "3d-orbit",
    title: "3D Orbit",
    description: "Set up a ThreeDScene and orbit the camera around a solid.",
    category: "3D",
    filename: "orbit_3d.py",
    code: `from manim import *


class Orbit3D(ThreeDScene):
    def construct(self):
        axes = ThreeDAxes(x_length=6, y_length=6, z_length=4)
        prism = Prism(dimensions=[1.5, 1.5, 2.5], fill_color=PURPLE, fill_opacity=0.7, stroke_width=1)

        self.set_camera_orientation(phi=70 * DEGREES, theta=30 * DEGREES)
        self.play(Create(axes))
        self.play(GrowFromCenter(prism))
        self.begin_ambient_camera_rotation(rate=0.4)
        self.wait(3)
        self.stop_ambient_camera_rotation()
`,
  },
  {
    id: "equation",
    title: "Equation Morph",
    description: "Typeset an equation with MathTex and transform it step by step.",
    category: "LaTeX",
    filename: "equation.py",
    needsLatex: true,
    code: `from manim import *


class EquationMorph(Scene):
    def construct(self):
        first = MathTex(r"e^{i\\pi} + 1 = 0", font_size=72)
        second = MathTex(r"e^{i\\theta} = \\cos\\theta + i\\sin\\theta", font_size=60)

        self.play(Write(first))
        self.wait(0.5)
        self.play(TransformMatchingTex(first, second))
        self.wait(1)
`,
  },
];

export const LATEX_TEMPLATES = [
  { name: "Euler's identity", code: "e^{i\\pi} + 1 = 0" },
  { name: "Quadratic formula", code: "x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}" },
  { name: "Gaussian integral", code: "\\int_{-\\infty}^{\\infty} e^{-x^2}\\,dx = \\sqrt{\\pi}" },
  { name: "Sum of integers", code: "\\sum_{i=1}^{n} i = \\frac{n(n+1)}{2}" },
  { name: "Schrödinger equation", code: "i\\hbar\\frac{\\partial}{\\partial t}\\Psi = \\hat{H}\\Psi" },
  { name: "Gauss's law", code: "\\nabla \\cdot \\mathbf{E} = \\frac{\\rho}{\\varepsilon_0}" },
  { name: "2×2 matrix", code: "\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}" },
  { name: "Derivative", code: "f'(x) = \\lim_{h \\to 0} \\frac{f(x+h) - f(x)}{h}" },
];

/** Starter code for a new, empty script. */
export function newSceneCode(className: string): string {
  return `from manim import *


class ${className}(Scene):
    def construct(self):
        title = Text("${className}", font_size=48)
        self.play(Write(title))
        self.wait(1)
        self.play(FadeOut(title))
`;
}
