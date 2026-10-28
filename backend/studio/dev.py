"""Developer tool: render a template's previews (and optionally a video) to look at.

    python backend/studio/dev.py countdown                      # every preset x 16:9, 9:16, 1:1
    python backend/studio/dev.py countdown --aspects 9:16 --preset classroom-timer
    python backend/studio/dev.py countdown --params '{"title": "A much longer title than usual"}'
    python backend/studio/dev.py countdown --video --quality 720p --preset launch-countdown

Posters and storyboards render in this process with Manim loaded once, the same way the
app's preview worker does; ``--video`` exports through runner.py in a subprocess.
Output goes to --out (default: a .studio-dev folder next to the repo's workspace).
"""

import argparse
import importlib
import json
import os
import subprocess
import sys
import time

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from studio.formats import QUALITIES, frame_size, pixel_size  # noqa: E402
from studio.registry import get_template, validate_job  # noqa: E402

DEFAULT_OUT = os.path.join(os.path.dirname(BACKEND), "workspace", ".studio-dev")
RUNNER = os.path.join(BACKEND, "studio", "runner.py")


def render_preview(template, params, settings, mode, out, short=360, assets_dir=None, media_dir=None):
    """Poster or storyboard in this process. Returns seconds taken."""
    from manim import tempconfig

    from studio.kit import runtime

    _, _, s = validate_job(template, params, settings)
    w, h = pixel_size(s.aspect, short)
    fw, fh = frame_size(w, h)
    cls = importlib.import_module(f"studio.templates.{template}.scene").Template
    runtime.set_job({"template": template, "params": params, "settings": settings, "mode": mode,
                     "assets_dir": assets_dir, "output": out})
    cfg = {"pixel_width": w, "pixel_height": h, "frame_width": fw, "frame_height": fh, "save_last_frame": True,
           "write_to_movie": False, "media_dir": media_dir or os.path.join(os.path.dirname(out), "_media"),
           "disable_caching": True, "verbosity": "ERROR", "progress_bar": "none",
           "transparent": s.background.kind == "transparent"}
    started = time.perf_counter()
    try:
        with tempconfig(cfg):
            cls().render()
    finally:
        runtime.set_job(None)
    return time.perf_counter() - started


def render_video(template, params, settings, out_dir, quality="720p", fmt="mp4", assets_dir=None):
    _, _, s = validate_job(template, params, settings)
    q = QUALITIES[quality]
    w, h = pixel_size(s.aspect, q["short"])
    spec = get_template(template)
    fps = spec.meta.export_fps or q["fps"]
    job_path = os.path.join(out_dir, "_job.json")
    with open(job_path, "w", encoding="utf-8") as f:
        json.dump({"template": template, "params": params, "settings": settings, "mode": "video",
                   "assets_dir": assets_dir}, f)
    cmd = [sys.executable, "-m", "manim", "-r", f"{w},{h}", "--fps", str(fps), "--disable_caching",
           "--media_dir", os.path.join(out_dir, "_video_media"), "-v", "WARNING", "--progress_bar", "none"]
    if fmt != "mp4":
        cmd += ["--format", fmt]
    if s.background.kind == "transparent":
        cmd.append("--transparent")
    cmd += [RUNNER, "StudioRender"]
    started = time.perf_counter()
    proc = subprocess.run(cmd, env={**os.environ, "COMPOSER_JOB": job_path}, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout[-2000:], proc.stderr[-4000:], file=sys.stderr)
        raise SystemExit(f"video render failed ({proc.returncode})")
    return time.perf_counter() - started


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("template")
    parser.add_argument("--preset", action="append", help="Only these presets (repeatable)")
    parser.add_argument("--aspects", default="16:9,9:16,1:1")
    parser.add_argument("--params", default=None, help="JSON merged over each preset's params")
    parser.add_argument("--settings", default=None, help="JSON merged over each preset's settings")
    parser.add_argument("--modes", default="poster,storyboard")
    parser.add_argument("--video", action="store_true", help="Also export a video per preset (first aspect)")
    parser.add_argument("--quality", default="720p", choices=sorted(QUALITIES))
    parser.add_argument("--format", default="mp4", choices=["mp4", "gif", "webm", "mov"])
    parser.add_argument("--assets", default=os.path.join(os.path.dirname(BACKEND), "workspace", "assets"))
    parser.add_argument("--out", default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    spec = get_template(args.template)
    presets = [p for p in spec.presets if not args.preset or p.id in args.preset]
    if not presets:
        raise SystemExit(f"no presets match {args.preset}")
    extra_params = json.loads(args.params) if args.params else {}
    extra_settings = json.loads(args.settings) if args.settings else {}
    os.makedirs(args.out, exist_ok=True)
    aspects = [a for a in args.aspects.split(",") if a in spec.meta.aspects]
    for preset in presets:
        params = {**preset.params, **extra_params}
        for aspect in aspects:
            settings = {**preset.settings, **extra_settings, "aspect": aspect}
            tag = f"{args.template}-{preset.id}-{aspect.replace(':', 'x')}"
            timings = []
            for mode in args.modes.split(","):
                path = os.path.join(args.out, f"{tag}-{mode}.png")
                took = render_preview(args.template, params, settings, mode, path, assets_dir=args.assets)
                timings.append(f"{mode} {took:5.2f}s")
            print(f"{tag:50s} " + "  ".join(timings), flush=True)
        if args.video:
            settings = {**preset.settings, **extra_settings, "aspect": aspects[0]}
            took = render_video(args.template, params, settings, args.out, args.quality, args.format, args.assets)
            print(f"{args.template}-{preset.id} video {args.quality} {args.format}: {took:.1f}s", flush=True)
    print(f"output: {args.out}")


if __name__ == "__main__":
    main()
