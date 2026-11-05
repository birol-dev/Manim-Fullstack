"""Small contact sheets for completed Author renders."""

from base64 import b64encode
from io import BytesIO
import math
from pathlib import Path
import shutil
import subprocess
from urllib.parse import unquote

from fastapi import HTTPException
from PIL import Image, ImageDraw


FRAME_SIZE = (416, 234)


def output_file(workspace, url):
    if not url.startswith("/media/"):
        raise FileNotFoundError
    root = (Path(workspace) / "media").resolve()
    path = (root / unquote(url[len("/media/"):])).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise FileNotFoundError
    return path


def output_stamp(path):
    stat = path.stat()
    return stat.st_ino, stat.st_mtime_ns, stat.st_size


def _sample_times(duration):
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Invalid video duration")
    end = max(0, duration - 0.05)
    return list(dict.fromkeys(round(end * fraction, 3) for fraction in (0.08, 0.35, 0.64, 0.96)))


def _scaled(image):
    image = image.convert("RGB")
    image.thumbnail(FRAME_SIZE, Image.Resampling.LANCZOS)
    return image


def _av_frames(path, av):
    with av.open(str(path)) as media:
        stream = media.streams.video[0]
        unit = float(stream.time_base)
        start = (stream.start_time or 0) * unit
        duration = stream.duration * unit if stream.duration else (media.duration or 0) / av.time_base
        frames = []
        for seconds in _sample_times(duration):
            media.seek(int((start + seconds) / unit), stream=stream, backward=True)
            sample = None
            for frame in media.decode(stream):
                sample = frame
                if frame.time is None or frame.time - start >= seconds:
                    break
            if sample is not None:
                time = seconds if sample.time is None else max(0, sample.time - start)
                frames.append((round(time, 3), _scaled(sample.to_image())))
        return duration, frames


def _ffmpeg_frames(path):
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise HTTPException(503, "Install PyAV or FFmpeg with ffprobe to inspect video frames.")
    options = {"timeout": 10, "stderr": subprocess.DEVNULL,
               "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    duration = float(subprocess.check_output([ffprobe, "-v", "error", "-show_entries", "format=duration",
                                              "-of", "csv=p=0", str(path)], **options))
    frames = []
    width, height = FRAME_SIZE
    for seconds in _sample_times(duration):
        png = subprocess.check_output([ffmpeg, "-v", "error", "-ss", str(seconds), "-i", str(path),
                                       "-frames:v", "1", "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease",
                                       "-c:v", "png", "-f", "image2pipe", "pipe:1"], **options)
        if png:
            with Image.open(BytesIO(png)) as frame:
                frames.append((seconds, _scaled(frame)))
    return duration, frames


def _frames(path, kind):
    if kind == "image":
        with Image.open(path) as image:
            return 0, [(0, _scaled(image))]
    try:
        import av
    except ImportError:
        return _ffmpeg_frames(path)
    return _av_frames(path, av)


def inspect_render(workspace, render, stamp):
    output = render.get("output")
    if render["status"] != "done" or not output:
        raise HTTPException(409, "Wait for the scene render to finish before inspecting it.")
    try:
        path = output_file(workspace, output["url"])
        if output_stamp(path) != stamp:
            raise HTTPException(409, "The output changed. Inspect the most recent render of this scene.")
        duration, frames = _frames(path, output["kind"])
        if output_stamp(path) != stamp:
            raise HTTPException(409, "The output changed while it was being inspected. Try the most recent render.")
    except FileNotFoundError:
        raise HTTPException(404, "This render's output is missing from Author mode.") from None
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(422, "Studio couldn't decode this render's frames.") from None
    if not frames:
        raise HTTPException(422, "Studio couldn't find any video frames to inspect.")

    width, height = FRAME_SIZE
    columns = min(2, len(frames))
    rows = math.ceil(len(frames) / columns)
    pad, label = 10, 24
    sheet = Image.new("RGB", (columns * (width + pad) + pad, rows * (height + label + pad) + pad), "#191e24")
    draw = ImageDraw.Draw(sheet)
    for index, (seconds, frame) in enumerate(frames):
        x = pad + index % columns * (width + pad)
        y = pad + index // columns * (height + label + pad)
        draw.rectangle((x, y, x + width - 1, y + height - 1), fill="black")
        sheet.paste(frame, (x + (width - frame.width) // 2, y + (height - frame.height) // 2))
        draw.text((x, y + height + 6), f"{seconds:.2f} s", fill="#e5eaf1")
    image = BytesIO()
    sheet.save(image, format="PNG")
    return {"duration": round(duration, 3), "timestamps": [time for time, _ in frames],
            "data": b64encode(image.getvalue()).decode("ascii")}
