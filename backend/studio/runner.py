"""The one file Manim renders for every template export (static: no generated code).

    COMPOSER_JOB=/path/job.json manim -r 1080,1920 --fps 30 backend/studio/runner.py StudioRender

Reads the job, sizes the frame for the pixel aspect, imports the template's scene and
declares ``StudioRender`` here, because Manim only picks up scene classes defined in the
file it was given.
"""

import importlib
import json
import math
import os
import sys
import threading
import time

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from studio.kit import runtime  # noqa: E402
from studio.compat import observe_encoded_frames, output_config  # noqa: E402
from studio.registry import get_template  # noqa: E402
from manim import tempconfig  # noqa: E402
from manim.renderer.cairo_renderer import CairoRenderer  # noqa: E402

PROGRESS_PREFIX = "@@studio-export "


class TimingRenderer(CairoRenderer):
    """Run the scene's timing without drawing images or encoding a movie.

    Quantize each play/wait just as Cairo does at the export fps. Advancing by
    these frames also makes remaining()/padding use the same clock as the movie.
    Counting plays or using a preview's (15 fps, rounded) duration is insufficient.
    """

    def __init__(self, **kwargs):
        super().__init__(skip_animations=True, **kwargs)
        self.frames = 0

    def update_frame(self, *args, **kwargs):
        pass

    def save_static_frame_data(self, *args, **kwargs):
        pass

    def play(self, scene, *args, **kwargs):
        started = self.time
        super().play(scene, *args, **kwargs)
        dt = 1 / self.camera.frame_rate
        samples = scene.duration / dt
        # Frozen waits repeat floor(duration * fps) frames; animated plays sample
        # arange(0, duration, 1/fps), including a final fractional frame.
        frozen = scene.is_current_animation_frozen_frame()
        frames = int(samples) if frozen else math.ceil(samples)
        self.frames += frames
        # Match Cairo's floating-point clock too: remaining() can otherwise pad
        # one different frame at an exact second boundary.
        self.time = started
        if frozen:
            self.time += frames * dt
        else:
            for _ in range(frames):
                self.time += dt


def measure_scene(template):
    with tempconfig({**output_config(dry_run=True), "progress_bar": "none"}):
        renderer = TimingRenderer()
        scene = template(renderer=renderer)
        scene.render()
        return renderer.frames


class FrameProgress:
    """Count completed frames, including batched frozen waits and async encoders."""

    def __init__(self, writer, total, send):
        self.total, self.send = total, send
        self.frames = 0
        self.last_sent = 0.0
        self._lock = threading.Lock()  # 0.22 can encode several segments concurrently
        self.finish = writer.finish
        # Manim >=0.19 queues frames to a background encoder. Counting queue.put
        # would report a long frozen wait complete while its frames still encode.
        # Observe the actual encoder instead, splitting its batches into frames.
        observe_encoded_frames(writer, self)
        writer.finish = self.finishing
        self.emit("drawing")

    def emit(self, phase):
        self.send({"phase": phase, "rendered_frames": self.frames, "total_frames": self.total})
        self.last_sent = time.monotonic()

    def write(self, frame, *args, **kwargs):
        result = self.write_frame(frame, *args, **kwargs)
        self.completed(int(kwargs.get("num_frames", args[0] if args else 1)))
        return result

    def write_batch(self, frame, num_frames):
        for _ in range(num_frames):
            self.write_frame(frame, 1)
            self.completed(1)

    def completed(self, count):
        with self._lock:
            self.frames += count
            if self.frames >= self.total:
                self.emit("finishing")
            elif time.monotonic() - self.last_sent >= 0.2:
                self.emit("drawing")

    def finishing(self, *args, **kwargs):
        # finish() combines partial movies, encodes GIF/WebM/MOV and muxes sound.
        # 0.22 can reach finish() with segment workers still encoding. Their
        # completed() calls announce finishing after the last encoded frame;
        # announcing it now would freeze the queue's progress below total.
        with self._lock:
            if self.frames >= self.total:
                self.emit("finishing")
        return self.finish(*args, **kwargs)

_job = runtime.current_job()
_spec = get_template(_job["template"])  # refuses ids that aren't installed templates
runtime.apply_frame()
_Template = importlib.import_module(f"studio.templates.{_spec.id}.scene").Template


class StudioRender(_Template):
    def render(self, *args, **kwargs):
        total = measure_scene(_Template)

        def send(event):
            sys.stdout.write(PROGRESS_PREFIX + json.dumps(event) + "\n")
            sys.stdout.flush()

        self._export_progress = FrameProgress(self.renderer.file_writer, total, send)
        return super().render(*args, **kwargs)
