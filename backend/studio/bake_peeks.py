"""Bake-only motion previews, called by ``python -m backend.studio.bake_posters``."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

from . import peeks
from .bake_posters import preset_requests
from .formats import ASPECT_RATIOS


def clip_window(duration):
    # 67 frames = 4.467 s. Keep the final, explicitly encoded poster frame.
    frames = max(1, round(duration * peeks.FPS))
    count = min(frames, int(peeks.MAX_DURATION * peeks.FPS))
    return frames - count, count


def encode(source, destination, duration, budget, poster, width, height, *, run=subprocess.run):
    start, count = clip_window(duration)
    # Pin the terminal frame to the actual gallery PNG, scaled to the movie's
    # dimensions. This also removes raster/rounding differences between sizes
    # and poster-only updater shortcuts. The clip never runs past this moment.
    filters = (f"[0:v]trim=start_frame={start}:end_frame={start + count},setpts=PTS-STARTPTS[clip];"
               f"[1:v]scale={width}:{height}:flags=lanczos[still];"
               f"[clip][still]overlay=enable='eq(n,{count - 1})':shortest=1[peek]")
    for crf in (26, 30, 34, 38, 42, 46, 50, 51):
        run(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-loop", "1", "-i", str(poster), "-an",
             "-filter_complex", filters, "-map", "[peek]",
             "-frames:v", str(count), "-r", str(peeks.FPS), "-c:v", "libx264",
             "-preset", "slow", "-crf", str(crf), "-pix_fmt", "yuv420p",
             "-movflags", "+faststart", str(destination)],
            check=True, capture_output=True, timeout=120,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if 0 < destination.stat().st_size <= budget:
            return
    destination.unlink(missing_ok=True)
    raise RuntimeError(f"Couldn't fit {destination.name} within {budget} bytes")


def bake(service, folder=None):
    folder = Path(folder or peeks.PEEKS_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    cards = list(preset_requests(service))
    budget = min(peeks.TARGET_FILE_BYTES, (peeks.MAX_TOTAL_BYTES - 64_000) // max(1, len(cards)))
    work = Path(service.tmp_dir) / "peek-bake"
    work.mkdir(parents=True, exist_ok=True)
    manifest = {}
    # The same warm motion worker/render protocol as editor previews. No export
    # queue and no second renderer. This worker is used only by the offline bake.
    worker = service._motion_worker_factory()
    try:
        for card, settings in cards:
            spec, params, validated, render_settings = service._validate(card["template"], card["params"], settings)
            aspect = ASPECT_RATIOS[render_settings.aspect]
            width, height = [max(2, round(peeks.LONG_SIDE * side / max(aspect) / 2) * 2) for side in aspect]
            key = peeks.peek_key(service, card, settings)
            source, temporary = work / "source.mp4", work / "encoded.mp4"
            try:
                result = worker.render({"template": spec.id, "params": params, "settings": validated,
                    "assets_dir": service.assets_dir, "mode": "motion", "peek": True,
                    "max_duration": peeks.MAX_DURATION, "output": str(source)}, width, height,
                    timeout=max(600, service.preview_timeout))
                poster = service.preview_sync(card["template"], card["params"], settings)
                encode(source, temporary, result["duration"], budget, poster["path"], width, height)
                temporary.replace(folder / f"{key}.mp4")
            finally:
                source.unlink(missing_ok=True)
                temporary.unlink(missing_ok=True)
            name = f'{card["template"]}/{card["id"]}'
            manifest[name] = key
            print(f"Baked peek {name}: {key}", flush=True)
    finally:
        worker.close()
    temporary_manifest = folder / ".manifest.json"
    temporary_manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    temporary_manifest.replace(folder / "manifest.json")
    for path in folder.glob("*.mp4"):
        if path.stem not in manifest.values():
            path.unlink()
    problems = peeks.check_baked(service, folder)
    if problems:
        raise RuntimeError("Invalid peek bake: " + ", ".join(problems))
    print(f"Baked {len(manifest)} gallery peeks ({sum(p.stat().st_size for p in folder.iterdir() if p.is_file()):,} bytes).")
