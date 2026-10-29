"""Exercise the real packaged renderer through HTTP; no mocks or system render tools."""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import time
import urllib.request

from launcher import Backend, configure_logging, smoke


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-root", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--audio-formats", action="store_true", help="Also verify WebM/Opus, MOV/PCM and silent GIF.")
    args = parser.parse_args()
    configure_logging(args.data_dir)
    started = time.monotonic()
    with Backend(args.app_root, args.data_dir) as backend:
        smoke(backend)

        def fetch(path, payload=None):
            request = urllib.request.Request(backend.url + path,
                data=json.dumps(payload).encode() if payload is not None else None,
                headers={"Authorization": f"Bearer {backend.token}", "Content-Type": "application/json"})
            with backend.http.open(request, timeout=90) as response:
                return response.read()

        job = {"template": "countdown", "params": {"seconds": 5, "title": "Desktop runtime smoke", "style": "ring"},
               "settings": {"aspect": "16:9", "theme": "clean", "sound": {"music": {"track": "calm"}}}}
        preview = json.loads(fetch("/api/studio/preview", {**job, "mode": "poster", "short": 120}))
        from PIL import Image
        with Image.open(io.BytesIO(fetch(preview["url"]))) as image:
            image.load()
            assert image.format == "PNG" and min(image.size) >= 120
            poster_size = image.size
        print(f"Real embedded-runtime preview passed: {poster_size[0]} x {poster_size[1]} PNG", flush=True)
        export = json.loads(fetch("/api/studio/exports", {**job, "format": "mp4", "quality": "draft", "title": "Desktop smoke"}))
        deadline = time.monotonic() + 120
        while export["status"] not in ("done", "failed", "cancelled"):
            if time.monotonic() >= deadline:
                raise RuntimeError("Packaged MP4 smoke exceeded 120 seconds.")
            time.sleep(0.25)
            export = json.loads(fetch("/api/studio/exports/" + export["id"]))
        if export["status"] != "done":
            raise RuntimeError(f"Packaged MP4 smoke failed: {export.get('error')}")
        movie = fetch(export["url"])
        import av
        with av.open(io.BytesIO(movie)) as container:
            assert container.streams.audio and container.streams.audio[0].codec_context.name == "aac", "MP4 must contain AAC"
            video = container.streams.video[0]
            width, height = video.width, video.height
            frames = sum(1 for _ in container.decode(video))
            duration = float(container.duration / av.time_base) if container.duration else None
            assert width > 0 and height > 0 and frames >= 50
        with av.open(io.BytesIO(movie)) as container:
            import numpy as np
            audio_stream = container.streams.audio[0]
            assert audio_stream.codec_context.sample_rate == 48000
            assert len(audio_stream.codec_context.layout.channels) == 2
            audio_frames = list(container.decode(audio=0))
            audio_samples = sum(frame.samples for frame in audio_frames)
            peak = max(float(np.max(np.abs(frame.to_ndarray()))) for frame in audio_frames)
            assert audio_samples > 0 and 0 < peak < 1, "Audio must be audible and unclipped"
        report = {"runtime_python": __import__("sys").version.split()[0],
                  "manim": __import__("importlib.metadata", fromlist=["version"]).version("manim"),
                  "template": "countdown", "preview": {"width": poster_size[0], "height": poster_size[1]},
                  "mp4": {"width": width, "height": height, "frames": frames, "duration": duration, "bytes": len(movie),
                          "audio_codec": "aac", "audio_rate": 48000, "audio_channels": 2,
                          "audio_samples": audio_samples, "audio_peak": peak},
                  "elapsed_seconds": round(time.monotonic() - started, 2)}
        if args.audio_formats:
            report["sound_formats"] = {}
            for fmt, expected in (("webm", "opus"), ("mov", "pcm_s16le"), ("gif", None)):
                short = {**job, "params": {"seconds": 3, "title": "", "style": "big"}, "format": fmt, "quality": "draft"}
                export = json.loads(fetch("/api/studio/exports", short))
                deadline = time.monotonic() + 150
                while export["status"] in ("queued", "rendering") and time.monotonic() < deadline:
                    time.sleep(.25)
                    export = json.loads(fetch("/api/studio/exports/" + export["id"]))
                assert export["status"] == "done", export
                with av.open(io.BytesIO(fetch(export["url"]))) as container:
                    actual = container.streams.audio[0].codec_context.name if container.streams.audio else None
                    assert actual == expected, (fmt, actual)
                    if actual:
                        assert container.streams.audio[0].codec_context.sample_rate == 48000
                        assert len(container.streams.audio[0].codec_context.layout.channels) == 2
                        assert sum(frame.samples for frame in container.decode(audio=0)) > 0
                    report["sound_formats"][fmt] = actual
        (args.data_dir / "render-smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("Real embedded-runtime MP4 passed: " + json.dumps(report["mp4"]), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
