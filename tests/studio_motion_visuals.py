"""Real warm-worker render probes. References draw live scene roots from scratch.

No golden PNGs: every reference is the exact same animation state as its movie
frame, without Cairo's cached/flattened moving-object lists. MP4 decoding also
checks the encoded file the browser actually receives.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
from PIL import Image

from studio.worker import _Child


class RecordingChild(_Child):
    def __init__(self, folder, samples=(22, 30, 33, 37, 45)):
        super().__init__(None)
        self.folder = Path(folder)
        self.samples = samples
        self.references = {}
        self.stale = {}

    def template_class(self, template_id):
        cls = super().template_class(template_id)
        probe = self

        class Recorded(cls):
            def setup(self):
                from manim.utils.iterables import list_update

                super().setup()
                add_frame = self.renderer.add_frame
                frame_number = 0

                def record(frame, num_frames=1):
                    nonlocal frame_number
                    wanted = [n for n in probe.samples if frame_number <= n < frame_number + num_frames]
                    if wanted:
                        # A separate camera never uses the old glyph references or
                        # a static-image cache. It draws the current scene tree.
                        camera = type(self.camera)()
                        roots = list_update(self.mobjects, self.foreground_mobjects)
                        camera.capture_mobjects(roots)
                        live = {id(m) for root in roots for m in root.get_family()}
                        displayed = self.camera.get_mobjects_to_display(self.moving_mobjects)
                        for n in wanted:
                            path = probe.folder / f"reference-{n}.png"
                            camera.get_image().convert("RGB").save(path)
                            Image.fromarray(frame).convert("RGB").save(probe.folder / f"raw-{n}.png")
                            probe.references[n] = path
                            probe.stale[n] = len([m for m in displayed if id(m) not in live])
                    add_frame(frame, num_frames)
                    frame_number += num_frames

                self.renderer.add_frame = record

        return Recorded


def decoded_frames(movie, samples, width, height):
    select = "+".join(f"eq(n\\,{n})" for n in samples)
    result = subprocess.run(["ffmpeg", "-v", "error", "-i", str(movie), "-vf", f"select={select}",
                             "-vsync", "0", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                            capture_output=True, check=True, timeout=60)
    frames = np.frombuffer(result.stdout, dtype=np.uint8).reshape(-1, height, width, 3)
    assert len(frames) == len(samples)
    return dict(zip(samples, frames))


def probe_motion(folder, template, params, settings, *, long_side=480, duration=4):
    from studio.formats import ASPECT_RATIOS

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    w, h = ASPECT_RATIOS[settings["aspect"]]
    width, height = [round(long_side * side / max(w, h) / 2) * 2 for side in (w, h)]
    movie = folder / "motion.mp4"
    child = RecordingChild(folder)
    result = child.render({"id": 1, "width": width, "height": height, "media_dir": str(folder / "media"),
                           "job": {"template": template, "params": params, "settings": settings,
                                   "mode": "motion", "max_duration": duration, "output": str(movie)}})
    assert result["ok"], result
    samples = sorted(child.references)
    frames = decoded_frames(movie, samples, width, height)
    metrics = {}
    for n, frame in frames.items():
        Image.fromarray(frame).save(folder / f"decoded-{n}.png")
        reference = np.asarray(Image.open(child.references[n]).convert("RGB"))
        raw = np.asarray(Image.open(folder / f"raw-{n}.png").convert("RGB"))
        raw_difference = np.abs(raw.astype(float) - reference.astype(float))
        difference = np.abs(frame.astype(float) - reference.astype(float))
        metrics[n] = {"mean": float(difference.mean()), "bad_pixels": float((difference.max(axis=2) > 40).mean()),
                      "raw_mean": float(raw_difference.mean()),
                      "raw_bad_pixels": float((raw_difference.max(axis=2) > 40).mean()),
                      "stale_objects": child.stale[n]}
    (folder / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return result, metrics


def benchmark_previews(folder, long_side):
    from studio import registry
    from studio.formats import ASPECT_RATIOS
    from studio.worker import PreviewWorker

    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    worker = PreviewWorker(media_dir=str(folder / "worker-media"))
    results = {}
    try:
        worker.start()  # Compare render time separately from the shared import/font startup.
        for template, preset in [("celebration", "happy-birthday"), ("countdown", "classroom-timer")]:
            spec = registry.get_template(template).public()
            card = next(p for p in spec["presets"] if p["id"] == preset)
            settings = {"aspect": spec["default_aspect"], **card["settings"]}
            w, h = ASPECT_RATIOS[settings["aspect"]]
            width, height = [round(long_side * side / max(w, h) / 2) * 2 for side in (w, h)]
            job = {"template": template, "params": card["params"], "settings": settings,
                   "mode": "motion", "max_duration": 20, "output": str(folder / f"{preset}.mp4")}
            started = time.perf_counter()
            result = worker.render(job, width, height, timeout=120)
            results[preset] = {"seconds": round(time.perf_counter() - started, 3), "render_ms": result["ms"],
                               "duration": result["duration"], "width": width, "height": height}
    finally:
        worker.close()
    (folder / "timings.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results


def compare_real_draft(folder, motion_movie):
    """Full, uncapped Draft export via the real CLI; no async executor/sandbox pipe."""
    from studio import registry
    from studio.exports import RUNNER_PATH

    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    spec = registry.get_template("countdown").public()
    card = next(p for p in spec["presets"] if p["id"] == "classroom-timer")
    job = {"template": "countdown", "params": card["params"],
           "settings": {"aspect": spec["default_aspect"], **card["settings"]}, "mode": "video"}
    job_path = folder / "job.json"
    job_path.write_text(json.dumps(job), encoding="utf-8")
    env = {**os.environ, "COMPOSER_JOB": str(job_path), "PYTHONIOENCODING": "utf-8"}
    started = time.perf_counter()
    with (folder / "render.log").open("w", encoding="utf-8") as log:
        subprocess.run([sys.executable, "-m", "manim", "-qm", "-r", "854,480", "--fps", "15",
                        "--media_dir", str(folder / "media"), "--disable_caching", "--progress_bar", "none",
                        "--verbosity", "ERROR", "-o", "draft", RUNNER_PATH, "StudioRender"],
                       env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=240,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    render_seconds = time.perf_counter() - started
    movie = next((folder / "media").rglob("draft.mp4"))
    samples = [30, 45, 150, 285]
    draft = decoded_frames(movie, samples, 854, 480)
    motion = decoded_frames(motion_movie, samples, 720, 404)
    differences = {}
    for frame in samples:
        images = [Image.fromarray(frames[frame]).resize((480, 270), Image.Resampling.LANCZOS) for frames in (draft, motion)]
        difference = np.abs(np.asarray(images[0]).astype(float) - np.asarray(images[1]).astype(float))
        for kind, img in zip(("draft", "motion"), images):
            img.save(folder / f"{kind}-{frame}.png")
        differences[frame] = {"mean": float(difference.mean()), "bad_pixels": float((difference.max(axis=2) > 40).mean())}
    result = {"draft_render_seconds": round(render_seconds, 3), "draft": str(movie), "comparisons": differences}
    (folder / "comparison.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
