from manim import *
import numpy as np

class HardcoreShowcase(ThreeDScene):
    def construct(self):
        # 1. INITIAL CAMERA CONFIGURATION
        self.set_camera_orientation(phi=65 * DEGREES, theta=-45 * DEGREES, zoom=0.8)
        
        # 2. FIXED UI LAYER (2D overlay on top of 3D canvas)
        title = Text("MANIM CE: CHAOS ENGINE & TOPOLOGY", font_size=24, color=BLUE_A)
        title.to_edge(UP).shift(LEFT * 0.5)
        
        div_label = Text("Trajectory Divergence (Δ):", font_size=16, color=GRAY_A)
        div_label.to_corner(UL).shift(DOWN * 1.2)
        
        div_val = DecimalNumber(0.0, num_decimal_places=6, color=YELLOW, font_size=18)
        div_val.next_to(div_label, RIGHT)
        
        # Lock UI elements to the screen space
        self.add_fixed_in_frame_mobjects(title, div_label, div_val)
        
        # 3. 3D MATHEMATICAL SPACE SETUP
        axes = ThreeDAxes(
            x_range=[-6, 6, 2], y_range=[-6, 6, 2], z_range=[-6, 6, 2],
            x_length=8, y_length=8, z_length=6
        )
        self.play(FadeIn(axes), run_time=1.5)
        
        # 4. PHASE 1: COMPONENT MORPHING (Parametric Surface Grid)
        # Generates a dynamic 3D wave fabric
        surface = Surface(
            lambda u, v: np.array([
                u,
                v,
                0.6 * np.sin(u) * np.cos(v)
            ]),
            u_range=[-4, 4],
            v_range=[-4, 4],
            resolution=(25, 25)
        )
        surface.set_style(fill_opacity=0.4, stroke_width=0.3)
        surface.set_color_by_gradient(PURE_BLUE, PURE_GREEN, PURE_RED)
        
        self.play(Create(surface), run_time=3.5, rate_func=linear)
        self.wait(0.5)
        
        # Morph the surface into a zero-plane state before fading out
        flattened_surface = Surface(
            lambda u, v: np.array([u, v, 0]),
            u_range=[-4, 4],
            v_range=[-4, 4],
            resolution=(5, 5)
        )
        self.play(Transform(surface, flattened_surface), run_time=1.5)
        self.play(FadeOut(surface))
        
        # 5. PHASE 2: CHAOTIC LORENZ ATTRACTOR (Numerical Integration via Updaters)
        # Parameters for the Lorenz system
        sigma, rho, beta = 10.0, 28.0, 8.0 / 3.0
        scale_factor = 0.12
        z_offset = 25
        
        # Explicit states for two trajectories starting with a tiny 10^-3 discrepancy
        state1 = np.array([1.0, 1.0, 20.0])
        state2 = np.array([1.0, 1.0, 20.001]) 
        
        # Instantiating 3D targets
        dot1 = Dot3D(point=(state1 - np.array([0, 0, z_offset])) * scale_factor, color=RED, radius=0.05)
        dot2 = Dot3D(point=(state2 - np.array([0, 0, z_offset])) * scale_factor, color=MAGENTA, radius=0.05)
        
        # High-performance history tracers
        path1 = TracedPath(dot1.get_center, stroke_color=RED, stroke_width=1.5, stroke_opacity=0.8)
        path2 = TracedPath(dot2.get_center, stroke_color=MAGENTA, stroke_width=1.5, stroke_opacity=0.8)
        
        self.add(dot1, dot2, path1, path2)
        
        # Micro-state tracking containers
        curr_s1 = state1.copy()
        curr_s2 = state2.copy()
        
        # Frame-by-frame differential equation solvers
        def update_dot1(mob, dt):
            nonlocal curr_s1
            dt = min(dt, 0.03) # Prevent tracking breaks during frame drops
            dx = sigma * (curr_s1[1] - curr_s1[0]) * dt
            dy = (curr_s1[0] * (rho - curr_s1[2]) - curr_s1[1]) * dt
            dz = (curr_s1[0] * curr_s1[1] - beta * curr_s1[2]) * dt
            curr_s1 += np.array([dx, dy, dz])
            mob.move_to((curr_s1 - np.array([0, 0, z_offset])) * scale_factor)
            
        def update_dot2(mob, dt):
            nonlocal curr_s2
            dt = min(dt, 0.03)
            dx = sigma * (curr_s2[1] - curr_s2[0]) * dt
            dy = (curr_s2[0] * (rho - curr_s2[2]) - curr_s2[1]) * dt
            dz = (curr_s2[0] * curr_s2[1] - beta * curr_s2[2]) * dt
            curr_s2 += np.array([dx, dy, dz])
            mob.move_to((curr_s2 - np.array([0, 0, z_offset])) * scale_factor)
        
        # UI Updater calculating Euclidean distance divergence in real-time
        def update_metrics(mob):
            distance = np.linalg.norm(curr_s1 - curr_s2)
            mob.set_value(distance)
            
        # Bind mathematical logic to runtime execution loops
        dot1.add_updater(update_dot1)
        dot2.add_updater(update_dot2)
        div_val.add_updater(update_metrics)
        
        # 6. PHASE 3: COMPLEX CAMERA ORBITATION
        # Rotate camera vectors while physics engine executes trajectories simultaneously
        self.move_camera(theta=45 * DEGREES, phi=50 * DEGREES, zoom=1.1, run_time=5, rate_func=linear)
        self.move_camera(theta=135 * DEGREES, phi=75 * DEGREES, zoom=0.9, run_time=5, rate_func=linear)
        self.move_camera(theta=225 * DEGREES, phi=35 * DEGREES, zoom=1.0, run_time=5, rate_func=linear)
        
        # Clean shutdown of tracking routines to freeze final state frame
        dot1.remove_updater(update_dot1)
        dot2.remove_updater(update_dot2)
        div_val.remove_updater(update_metrics)
        
        self.wait(2)