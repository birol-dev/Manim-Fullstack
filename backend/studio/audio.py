"""Original deterministic synthesis and bounded PCM mixing. No Manim imports.

Audio libraries are loaded only when audio is requested. PCM is stereo 48 kHz;
mixing works in chunks, even for hour-long timers. See assets/sounds/PROVENANCE.md.
"""
from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
import wave
from functools import lru_cache
from fractions import Fraction

from .sound import EFFECTS, MAX_AUDIO_SECONDS, MAX_STORED_AUDIO_BYTES, SAMPLE_RATE, TRACKS
from .loudness import limit_peak, normalize_loudness, volume_gain


def stereo(samples):
    import numpy as np
    values = np.asarray(samples, dtype=np.float32)
    return np.repeat(values[:, None], 2, axis=1) if values.ndim == 1 else values


def pcm_bytes(samples):
    import numpy as np
    raw = io.BytesIO()
    with wave.open(raw, "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes((np.clip(stereo(samples), -1, 1) * 32767).round().astype("<i2").tobytes())
    return raw.getvalue()


def read_pcm(data):
    import numpy as np
    if data.startswith(b"fLaC"):
        return _decode(data)
    with wave.open(io.BytesIO(data), "rb") as source:
        if source.getsampwidth() != 2 or source.getnchannels() not in (1, 2):
            raise ValueError("Expected normalized audio.")
        channels, rate = source.getnchannels(), source.getframerate()
        values = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2").reshape(-1, channels).astype(np.float32) / 32768
        if channels == 1:
            values = np.repeat(values, 2, axis=1)
        # Read pre-stereo workspace assets without modifying saved projects.
        if rate != SAMPLE_RATE:
            indices = np.arange(round(len(values) * SAMPLE_RATE / rate)) * rate / SAMPLE_RATE
            values = np.column_stack([np.interp(indices, np.arange(len(values)), values[:, ch]) for ch in range(2)]).astype(np.float32)
            values = normalize_loudness(values)
        return values


def _level(samples, peak=10 ** (-3 / 20)):
    import numpy as np
    maximum = float(np.max(np.abs(samples), initial=0))
    return (samples * (peak / maximum) if maximum else samples).astype(np.float32)


@lru_cache(maxsize=16)
def synthesize(name: str, *, music=False):
    import numpy as np
    if music:
        if name not in {t["id"] for t in TRACKS}:
            raise ValueError("Unknown music track.")
        step = {"calm": 0.75, "upbeat": 0.4, "playful": 0.5}[name]
        result = np.zeros((round(step * 32 * SAMPLE_RATE), 2), dtype=np.float64)
        # Original C/add9 -> Am7 -> Fmaj7 -> G/sus progression, no sampled audio.
        chords = ((48, 55, 62, 64), (45, 55, 60, 64), (41, 53, 57, 64), (43, 55, 60, 62))
        for i in range(32):
            chord = chords[i // 8]
            note = chord[(i * 3 if name == "playful" else i) % 4] + 12
            duration = step * (2.8 if name == "calm" else 1.7)
            t = np.arange(round(duration * SAMPLE_RATE)) / SAMPLE_RATE
            frequency = 440 * 2 ** ((note - 69) / 12)
            envelope = (1 - np.exp(-t / 0.012)) * np.exp(-t / (duration / 4))
            tone = (np.sin(2 * np.pi * frequency * t) + .18 * np.sin(4 * np.pi * frequency * t)) * envelope
            indices = (round(i * step * SAMPLE_RATE) + np.arange(len(t))) % len(result)
            pan = .22 * np.sin(i * 1.7)
            np.add.at(result[:, 0], indices, tone * (1 - pan))
            np.add.at(result[:, 1], indices, tone * (1 + pan))
        # Tiny edge fades make repeated PCM boundaries click-free.
        edge = round(.008 * SAMPLE_RATE)
        result[:edge] *= np.linspace(0, 1, edge)[:, None]
        result[-edge:] *= np.linspace(1, 0, edge)[:, None]
        return normalize_loudness(result)
    if name not in EFFECTS:
        raise ValueError("Unknown sound effect.")
    duration = {"tick": .07, "tick_final": .11, "pop": .14, "whoosh": .22,
                "reveal": .5, "correct": .65, "finish": .8, "sparkle": .6}[name]
    t = np.arange(round(duration * SAMPLE_RATE)) / SAMPLE_RATE
    if name == "whoosh":
        rng = np.random.default_rng(20261029)
        noise = rng.standard_normal(len(t))
        tone = np.convolve(noise, np.ones(12) / 12, mode="same")
        envelope = np.sin(np.pi * t / duration) ** 3
    elif name in ("tick", "tick_final", "pop"):
        frequency = {"tick": 640, "tick_final": 820, "pop": 360}[name]
        tone = np.sin(2 * np.pi * frequency * (t - .25 * t * t / duration))
        envelope = (1 - np.exp(-t / .003)) * np.exp(-t / (duration / 5))
    else:
        tone = np.zeros(len(t))
        for index, frequency in enumerate((523.25, 659.25, 783.99)):
            age = np.maximum(0, t - index * .045)
            tone += np.sin(2 * np.pi * frequency * age) * (1 - np.exp(-age / .005)) * np.exp(-age / .15)
        envelope = np.ones(len(t))
    result = tone * envelope
    edge = min(round(.008 * SAMPLE_RATE), len(t) // 3)
    result[-edge:] *= np.linspace(1, 0, edge)
    return stereo(_level(result))


def generated_file(cache: str, name: str, *, music=False) -> str:
    from .sound import AUDIO_VERSION
    directory = Path(cache)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"v{AUDIO_VERSION}-{'music' if music else 'effect'}-{name}.wav"
    if not path.is_file():
        data = pcm_bytes(synthesize(name, music=music))
        fd, temporary = tempfile.mkstemp(dir=directory, suffix=".wav")
        try:
            with os.fdopen(fd, "wb") as target:
                target.write(data)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return str(path)


def _decode(data: bytes):
    """Keep stereo; upmix mono and resample to 48 kHz with the codec stack."""
    import numpy as np
    try:
        import av
        if not hasattr(av, "open"):
            raise ImportError("PyAV is unavailable")
    except ImportError:
        # Manim 0.18 already needs an ffmpeg executable for video. New desktop
        # runtimes take the PyAV branch and never invoke a system media tool.
        try:
            reply = subprocess.run(["ffmpeg", "-v", "error", "-i", "pipe:0", "-vn", "-t", str(MAX_AUDIO_SECONDS + 1),
                                    "-ac", "2", "-ar", str(SAMPLE_RATE), "-f", "f32le", "pipe:1"],
                                   input=data, capture_output=True, timeout=30, check=True,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError("Couldn't read this audio. Choose an MP3, M4A/AAC, WAV or OGG file.") from exc
        samples = np.frombuffer(reply.stdout, dtype="<f4").reshape(-1, 2)
    else:
        chunks, count = [], 0
        try:
            with av.open(io.BytesIO(data)) as source:
                if source.streams.video or not source.streams.audio:
                    raise ValueError("Choose an audio file without video.")
                resampler = av.AudioResampler(format="fltp", layout="stereo", rate=SAMPLE_RATE)
                for frame in source.decode(source.streams.audio[0]):
                    for normalized in resampler.resample(frame):
                        chunk = normalized.to_ndarray().T.copy()
                        count += len(chunk)
                        if count > MAX_AUDIO_SECONDS * SAMPLE_RATE:
                            raise ValueError("Choose music of at most 10 minutes; Studio can loop it.")
                        chunks.append(chunk)
                for normalized in resampler.resample(None):
                    chunks.append(normalized.to_ndarray().T.copy())
            samples = np.concatenate(chunks).astype(np.float32) if chunks else np.empty((0, 2), np.float32)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("Couldn't decode this audio file.") from exc
    if not len(samples):
        raise ValueError("This file contains no playable audio.")
    if len(samples) > MAX_AUDIO_SECONDS * SAMPLE_RATE:
        raise ValueError("Choose music of at most 10 minutes; Studio can loop it.")
    return samples


def normalize_upload(data: bytes) -> bytes:
    """Store lossless FLAC, capped independently of the 50 MB source upload."""
    import numpy as np
    samples = normalize_loudness(_decode(data))
    try:
        import av
        if not hasattr(av, "open"):
            raise ImportError("PyAV is unavailable")
    except ImportError:
        try:
            result = subprocess.run(["ffmpeg", "-v", "error", "-i", "pipe:0", "-c:a", "flac", "-f", "flac", "pipe:1"],
                                    input=pcm_bytes(samples), capture_output=True, check=True, timeout=60,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError("Couldn't prepare this music. Try another audio file.") from exc
    else:
        buffer = io.BytesIO()
        with av.open(buffer, "w", format="flac") as output:
            stream = output.add_stream("flac", rate=SAMPLE_RATE)
            stream.layout = "stereo"
            stream.format = "s16"
            for start in range(0, len(samples), 4096):
                values = (samples[start:start + 4096] * 32767).round().astype(np.int16)
                frame = av.AudioFrame.from_ndarray(values.reshape(1, -1), format="s16", layout="stereo")
                frame.sample_rate = SAMPLE_RATE
                frame.pts = start
                frame.time_base = Fraction(1, SAMPLE_RATE)
                for packet in stream.encode(frame):
                    output.mux(packet)
            for packet in stream.encode(None):
                output.mux(packet)
        result = buffer.getvalue()
    if len(result) > MAX_STORED_AUDIO_BYTES:
        raise ValueError("Prepared music exceeds 64 MB. Choose a shorter track; Studio can loop it.")
    return result


def mixed_chunks(duration: float, sound, cues, music_samples=None, energy="normal", chunk_size=SAMPLE_RATE):
    """Yield exactly duration's stereo frames, with dB faders and smooth ducking."""
    import numpy as np
    total = max(0, round(duration * SAMPLE_RATE))
    effects = [(round(at * SAMPLE_RATE), synthesize(name)) for name, at in cues
               if sound.effects and sound.effects_volume and 0 <= at < duration]
    music = stereo(music_samples) if music_samples is not None else None
    fade = min(1.5, duration / 2) if sound.music.fade_out else 0
    lively = {"calm": .8, "normal": 1, "punchy": 1.08}.get(energy, 1)
    limiter_gain = 1.
    for start in range(0, total, chunk_size):
        end = min(total, start + chunk_size)
        indices = np.arange(start, end)
        result = np.zeros((end - start, 2), dtype=np.float32)
        if music is not None and len(music) and sound.music.volume:
            valid = np.ones(len(indices), dtype=bool) if sound.music.loop else indices < len(music)
            result[valid] = music[indices[valid] % len(music)] * volume_gain(sound.music.volume)
            if fade:
                result *= np.clip((total - 1 - indices) / (fade * SAMPLE_RATE), 0, 1)[:, None]
            result *= np.minimum(1, indices / (.025 * SAMPLE_RATE))[:, None]
        duck = np.ones(len(result), dtype=np.float32)
        effect_mix = np.zeros_like(result)
        for at, effect in effects:
            a, b = max(start, at), min(end, at + len(effect))
            if b > a:
                effect_mix[a-start:b-start] += effect[a-at:b-at] * volume_gain(sound.effects_volume) * lively
            # Gentle 35ms attack/180ms release; no abrupt gain edges.
            elapsed = (indices - at) / SAMPLE_RATE
            window = np.minimum(np.clip((elapsed + .035) / .035, 0, 1),
                                np.clip((len(effect) / SAMPLE_RATE + .18 - elapsed) / .18, 0, 1))
            duck = np.minimum(duck, 1 - .65 * window)
        limited, limiter_gain = limit_peak(result * duck[:, None] + effect_mix, initial_gain=limiter_gain, return_gain=True)
        yield limited


def audio_fingerprint():
    digest = hashlib.sha256()
    for name in ("sound.py", "audio.py", "audio_render.py", "loudness.py"):
        digest.update(Path(__file__).with_name(name).read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()[:16]
