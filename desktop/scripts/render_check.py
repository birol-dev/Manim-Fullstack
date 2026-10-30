r"""Real Studio render smoke, using the interpreter that launches this script.

    desktop\.runtime\python.exe -B desktop\scripts\render_check.py

No pytest or installed FFmpeg is required when PyAV is available. All renders
use a temporary workspace and real workers/export subprocesses. Exit 1 on any
failure; keep checking the remaining cases so one run gives the whole matrix.
"""
from __future__ import annotations

import asyncio
from fractions import Fraction
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def probe(path, fmt, *, alpha=False, audio=False, fps=None, size=None):
    """Check the actual container, decoded pixels/alpha and decoded audio."""
    require(path.is_file() and path.stat().st_size > 0, f"Missing/empty output: {path}")
    from PIL import Image
    if fmt == "png":
        with Image.open(path) as image:
            image.load()
            require(image.format == "PNG", f"Expected PNG, got {image.format}")
            if size:
                require(image.size == size, f"Expected {size}, got {image.size}")
            if alpha:
                require(image.mode == "RGBA" and image.getchannel("A").getextrema()[0] < 255,
                        "PNG lost transparency")
        return f"PNG {image.width}x{image.height}, alpha={alpha}, audio=no"

    with path.open("rb") as source:
        header = source.read(32)
    if fmt in ("mp4", "mov"):
        require(header[4:8] == b"ftyp", f"Not an ISO media container: {header!r}")
        require((header[8:12] == b"qt  ") == (fmt == "mov"), f"Wrong MP4/MOV brand: {header[8:12]!r}")
    elif fmt == "webm":
        require(header[:4] == b"\x1aE\xdf\xa3", "Not a WebM/Matroska container")
    elif fmt == "gif":
        require(header[:6] in (b"GIF87a", b"GIF89a"), "Not a GIF container")

    try:
        import av
        require(callable(getattr(av, "open", None)), "PyAV is unavailable")
    except (ImportError, AssertionError):
        return probe_ffmpeg(path, fmt, alpha=alpha, audio=audio, fps=fps, size=size)

    import numpy as np
    with av.open(str(path)) as container:
        require(len(container.streams.video) == 1, "Expected one video stream")
        video = container.streams.video[0]
        require(bool(container.streams.audio) == audio, f"Expected audio={audio}, got {len(container.streams.audio)} streams")
        if fps:
            require(video.average_rate == Fraction(fps), f"Expected {fps} fps, got {video.average_rate}")
        if size:
            require((video.width, video.height) == size, f"Wrong resolution: {video.width}x{video.height}")
        # FFmpeg's native VP9 decoder discards WebM's auxiliary alpha plane.
        # libvpx-vp9 exposes it; checking codec pixel format alone misses this.
        if alpha and fmt == "webm":
            decoder = av.CodecContext.create("libvpx-vp9", "r")
            decoder.extradata = video.codec_context.extradata
            frames = (frame for packet in container.demux(video) for frame in decoder.decode(packet))
        else:
            frames = container.decode(video)
        count, transparent = 0, False
        for frame in frames:
            count += 1
            if alpha and not transparent:
                transparent = bool(np.any(frame.to_ndarray(format="rgba")[:, :, 3] < 255))
        require(count > 0, "Video contains no decodable frames")
        if alpha:
            require(transparent, f"{fmt.upper()} lost its alpha plane")
        codec = video.codec_context.name
    if audio:
        with av.open(str(path)) as container:
            stream = container.streams.audio[0]
            expected = {"mp4": "aac", "webm": "opus", "mov": "pcm_s16le"}[fmt]
            require(stream.codec_context.name == expected, f"Expected {expected}, got {stream.codec_context.name}")
            require(stream.codec_context.sample_rate == 48000 and len(stream.codec_context.layout.channels) == 2,
                    "Audio must be 48 kHz stereo")
            peak = max((float(np.max(np.abs(frame.to_ndarray().astype(float))))
                        for frame in container.decode(stream)), default=0)
            require(peak > 0, "Audio stream is empty/silent")
    return f"{fmt.upper()} {codec}, {count} frames, alpha={alpha}, audio={audio}"


def probe_ffmpeg(path, fmt, *, alpha, audio, fps, size):
    """Independent fallback for dev installs which do not have PyAV."""
    require(shutil.which("ffprobe") and shutil.which("ffmpeg"), "Install PyAV or provide ffprobe + ffmpeg")
    result = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)],
                            capture_output=True, check=True, timeout=30)
    streams = json.loads(result.stdout)["streams"]
    video = next(s for s in streams if s["codec_type"] == "video")
    sound = [s for s in streams if s["codec_type"] == "audio"]
    require(bool(sound) == audio, f"Expected audio={audio}, got {len(sound)} streams")
    if fps:
        require(Fraction(video["r_frame_rate"]) == Fraction(fps), f"Wrong fps: {video['r_frame_rate']}")
    if size:
        require((video["width"], video["height"]) == size, "Wrong resolution")
    args = ["ffmpeg", "-v", "error"]
    if alpha and fmt == "webm":
        args += ["-c:v", "libvpx-vp9"]
    args += ["-i", str(path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgba", "pipe:1"]
    frame = subprocess.run(args, capture_output=True, check=True, timeout=30).stdout
    require(bool(frame), "No decodable video frame")
    if alpha:
        require(min(frame[3::4]) < 255, f"{fmt.upper()} lost its alpha plane")
    if audio:
        require(sound[0]["codec_name"] == {"mp4": "aac", "webm": "opus", "mov": "pcm_s16le"}[fmt], "Wrong audio codec")
        require(sound[0]["sample_rate"] == "48000" and sound[0]["channels"] == 2, "Audio must be 48 kHz stereo")
        pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-f", "s16le", "pipe:1"],
                             capture_output=True, check=True, timeout=30).stdout
        require(any(pcm), "Audio stream is empty/silent")
    return f"{fmt.upper()} {video['codec_name']}, alpha={alpha}, audio={audio} (FFmpeg probe)"


async def wait_for(get, record, timeout=240, observe=lambda record: None):
    deadline = time.monotonic() + timeout
    while True:
        record = await get(record["id"])
        observe(record)
        if record["status"] not in ("queued", "rendering"):
            detail = record.get("error") or record.get("message") or record["status"]
            require(record["status"] == "done", f"{record['status']}: {detail}")
            return record
        require(time.monotonic() < deadline, f"Render timed out: {record['id']}")
        await asyncio.sleep(.05)


async def check_all(workspace, check):
    from studio.registry import all_templates
    from studio.service import StudioService
    service = StudioService(str(workspace), preview_timeout=120, export_timeout=180)
    # Force real renders even when a gallery bake exists for a first preset.
    service._seed_poster = lambda *args: False
    try:
        for spec in all_templates():
            preset = spec.presets[0]
            settings = {"aspect": spec.meta.default_aspect, **preset.settings}
            for mode in ("poster", "storyboard"):
                async def preview(spec=spec, preset=preset, settings=settings, mode=mode):
                    result = await service.preview(spec.id, preset.params, settings, mode=mode)
                    require(not result["cached"], "Smoke must exercise the real worker")
                    if mode == "storyboard":
                        require(result["storyboard"]["frames"] > 0, "Empty storyboard")
                        require(result["storyboard"]["length"] > 0, "Storyboard did not advance time")
                    return probe(Path(result["path"]), "png")
                await check(f"{spec.id}/{preset.id} {mode}", preview)

        params = {"seconds": 3, "style": "big", "title": "", "confetti": False}
        settings = {"aspect": "16:9", "sound": {"effects": True, "music": {"track": "calm"}}}

        async def motion():
            record = await service.start_motion("render-check", "countdown", params, settings)
            record = await wait_for(service.get_motion, record)
            require(0 < record["duration"] <= 20.1, f"Invalid motion duration: {record['duration']}")
            path = Path(service.previews_dir) / record["url"].rsplit("/", 1)[-1]
            return probe(path, "mp4", audio=True, fps=15, size=(720, 404))
        await check("countdown motion + sound", motion)

        for fmt in ("mp4", "webm", "mov", "gif", "png"):
            async def export(fmt=fmt):
                alpha = fmt in ("webm", "mov", "png")
                options = {**settings, "background": {"kind": "transparent" if alpha else "theme"}}
                record = await service.start_export("countdown", params, options, format=fmt, quality="draft")
                progress = []
                def observe(record):
                    if "rendered_frames" in record:
                        progress.append((record["rendered_frames"], record["total_frames"]))
                record = await wait_for(service.get_export, record, observe=observe)
                require(record["fps"] == 15, "Timer must keep its own export fps")
                require(record["progress"] == 100, "Missing completed export progress")
                require(progress and progress[-1][0] == progress[-1][1] > 0, "Missing/incomplete frame progress")
                require([n for n, _ in progress] == sorted(n for n, _ in progress), "Frame progress regressed")
                return probe(Path(service.exports_dir) / record["filename"], fmt, alpha=alpha,
                             audio=fmt in ("mp4", "webm", "mov"), fps=15 if fmt not in ("gif", "png") else None,
                             size=(854, 480))
            await check(f"countdown draft {fmt}", export)
    finally:
        await service.shutdown()


def main():
    rows = []
    async def check(label, action):
        started = time.monotonic()
        try:
            detail = await action()
            status = "PASS"
        except Exception as exc:
            detail, status = f"{type(exc).__name__}: {exc}", "FAIL"
            traceback.print_exc()
        rows.append((label, status, detail))
        print(f"{status:4} {label}: {detail} ({time.monotonic() - started:.1f}s)", flush=True)

    try:
        import manim
        from manim import config  # a namespace import can hide WinError 5 on site-packages
        print(f"Interpreter: {sys.executable}\nManim: {manim.__version__}", flush=True)
        with tempfile.TemporaryDirectory(prefix="studio-render-check-") as folder:
            asyncio.run(check_all(Path(folder), check))
    except Exception as exc:
        rows.append(("runtime/workspace", "FAIL", f"{type(exc).__name__}: {exc}"))
        traceback.print_exc()
    print("\nCASE | RESULT | CHECKS")
    print("--- | --- | ---")
    for label, status, detail in rows:
        print(f"{label} | {status} | {detail}")
    failures = sum(status == "FAIL" for _, status, _ in rows)
    print(f"\n{len(rows) - failures} passed, {failures} failed")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
