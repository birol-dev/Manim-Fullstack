"""Attach audio after Manim finishes its silent movie. No Manim imports.

Manim 0.18 hard-codes CLI ffmpeg/AAC in its sound writer (including WebM).
Studio instead copies the finished video stream and encodes only our PCM mix.
PyAV is used in the desktop bundle; the CLI fallback serves existing 0.18 installs.
"""
from __future__ import annotations

from fractions import Fraction
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import wave

from .audio import mixed_chunks, read_pcm, synthesize
from .sound import EFFECTS, SAMPLE_RATE


def record_cue(scene, name: str, offset=0.0):
    if name not in EFFECTS or not math.isfinite(offset) or offset < 0:
        raise ValueError("Use a known effect and a non-negative cue offset.")
    if scene.mode not in ("video", "motion") or scene.is_peek or not scene.s.sound.effects:
        return
    scene._sound_cues.append((name, float(scene.elapsed) + offset))


def install_sound(scene):
    scene._sound_cues = []
    if scene.mode not in ("video", "motion") or scene.is_peek:
        return
    # The caller already excluded dry runs, stills, peeks and GIFs.
    writer = scene.renderer.file_writer
    finish = writer.finish

    def finish_with_sound(*args, **kwargs):
        result = finish(*args, **kwargs)
        path = getattr(writer, "movie_file_path", None)
        if path and Path(path).suffix.lower() in (".mp4", ".webm", ".mov") and Path(path).is_file():
            sound = scene.s.sound
            if (sound.effects and sound.effects_volume and scene._sound_cues) or (
                    sound.music.volume and (sound.music.asset or sound.music.track)):
                music = None
                if sound.music.asset:
                    source = Path(scene.assets_dir) / sound.music.asset
                    music = read_pcm(source.read_bytes())
                elif sound.music.track:
                    music = synthesize(sound.music.track, music=True)
                mux_sound(str(path), sound, scene._sound_cues, music, scene.s.energy)
        return result

    writer.finish = finish_with_sound


def _pyav():
    try:
        import av
        return av if hasattr(av, "open") else None
    except ImportError:
        return None


def _command(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, timeout=120,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), **kwargs)


def mux_sound(path, sound, cues, music=None, energy="normal"):
    """Atomic replacement, copied video packets, exact PCM duration, bounded RAM."""
    target = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=".~sound-", suffix=target.suffix, dir=target.parent)
    os.close(fd)
    audio_path = temporary + ".wav"
    try:
        av = _pyav()
        if av is not None:
            _mux_av(av, path, temporary, sound, cues, music, energy)
        else:
            metadata = json.loads(_command(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                            "-show_entries", "stream=duration:format=duration", "-of", "json", path]).stdout)
            duration = float(metadata["streams"][0].get("duration") or metadata["format"]["duration"])
            with wave.open(audio_path, "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(SAMPLE_RATE)
                for chunk in mixed_chunks(duration, sound, cues, music, energy):
                    audio.writeframesraw((chunk * 32767).round().astype("<i2").tobytes())
            codec = "libopus" if target.suffix == ".webm" else "pcm_s16le" if target.suffix == ".mov" else "aac"
            args = ["ffmpeg", "-v", "error", "-y", "-i", path, "-i", audio_path, "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "copy", "-c:a", codec, "-t", str(duration)]
            if target.suffix == ".mp4":
                args += ["-movflags", "+faststart"]
            _command([*args, temporary])
        os.replace(temporary, path)
    finally:
        for leftover in (temporary, audio_path):
            if os.path.exists(leftover):
                os.unlink(leftover)


def _mux_av(av, source_path, output_path, sound, cues, music, energy):
    import numpy as np
    extension = Path(output_path).suffix
    codec = "libopus" if extension == ".webm" else "pcm_s16le" if extension == ".mov" else "aac"
    options = {"movflags": "+faststart"} if extension == ".mp4" else {}
    with av.open(source_path) as source, av.open(output_path, "w", options=options) as target:
        video = source.streams.video[0]
        duration = float(video.duration * video.time_base) if video.duration is not None else source.duration / av.time_base
        if hasattr(target, "add_stream_from_template"):
            copied = target.add_stream_from_template(video)
        else:
            copied = target.add_stream(template=video)
        copied.metadata.update(video.metadata)
        target.metadata.update(source.metadata)
        audio = target.add_stream(codec, rate=SAMPLE_RATE)
        audio.layout = "mono"
        fmt = "s16" if codec == "pcm_s16le" else "flt" if codec == "libopus" else "fltp"
        audio.format = fmt
        audio.bit_rate = 96000

        def audio_packets():
            position = 0
            size = 960 if codec == "libopus" else 1024
            for chunk in mixed_chunks(duration, sound, cues, music, energy, chunk_size=size):
                values = (chunk * 32767).round().astype(np.int16) if fmt == "s16" else chunk.astype(np.float32)
                frame = av.AudioFrame.from_ndarray(values.reshape(1, -1), format=fmt, layout="mono")
                frame.sample_rate = SAMPLE_RATE
                frame.time_base = Fraction(1, SAMPLE_RATE)
                frame.pts = position
                position += len(chunk)
                yield from audio.encode(frame)
            yield from audio.encode(None)

        packets = iter(audio_packets())
        pending = next(packets, None)
        for packet in source.demux(video):
            if packet.dts is None:
                continue
            while pending is not None and float(pending.dts * pending.time_base) <= float(packet.dts * packet.time_base):
                target.mux(pending)
                pending = next(packets, None)
            packet.stream = copied
            target.mux(packet)
        if pending is not None:
            target.mux(pending)
        for packet in packets:
            target.mux(packet)
