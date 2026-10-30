"""Manim 0.18/0.22 output and encoder boundaries used by Studio.

No eager Manim import: the service/export queue must also work without Manim.
0.22 captures an immutable OutputSpec when a scene is created; changing legacy
flags afterwards cannot change that scene's output intent.
"""
from __future__ import annotations

from pathlib import Path


def output_config(*, still=False, format="mp4", transparent=False, dry_run=False, cfg=None):
    """tempconfig values for a still, movie, or timing-only pass.

    Keep the legacy flags/order on 0.18. On 0.22 save_last_frame is an alias
    for format=png, so a subsequent format=mp4 would undo the still request.
    """
    if cfg is None:
        from manim import config as cfg
    if hasattr(cfg, "write_to_movie"):
        return {"save_last_frame": still, "write_to_movie": not still and not dry_run,
                "format": format, "transparent": transparent, "dry_run": dry_run}
    return {"format": "none" if dry_run else "png" if still else format,
            "transparent": transparent, "dry_run": dry_run}


def output_cli_args(format, transparent=False):
    """Flags shared by both CLIs; do not import Manim in the parent process."""
    args = ["--progress_bar=none"]
    if format != "mp4":
        args += ["--format", format]
    if transparent:
        args.append("--transparent")
    return args


def writes_movie(scene):
    """Whether this scene writes video (including GIF), excluding dry runs/stills."""
    spec = getattr(scene.renderer.file_writer, "output_spec", None)
    if spec is not None:
        return spec.is_video
    from manim import config
    return not config.dry_run and config.write_to_movie


def written_movie(writer):
    """The primary video/GIF artifact, never a silent cached segment.

    0.22 publishes final_file_path after draining its encoder jobs; legacy GIFs
    have a separate path from movie_file_path. Call after writer.finish().
    """
    spec = getattr(writer, "output_spec", None)
    if spec is not None:
        if not spec.is_video:
            return None
        path = getattr(writer, "final_file_path", None) or writer.movie_file_path
    else:
        from manim import config
        path = getattr(writer, "gif_file_path" if config.format == "gif" else "movie_file_path", None)
    return Path(path) if path else None


def movie_has_sound(scene):
    """GIF is time-based output in 0.22 but cannot contain an audio stream."""
    if not writes_movie(scene):
        return False
    spec = getattr(scene.renderer.file_writer, "output_spec", None)
    if spec is not None:
        return not spec.is_gif
    from manim import config
    return config.format != "gif"


def observe_encoded_frames(writer, progress):
    """Observe encoding, not queue submission, including repeated frozen frames.

    0.18 writes synchronously; 0.19-0.21 use encode_and_write_frame; 0.22
    creates per-segment encoders whose write_frame takes keyword-only repeat.
    Wrap each encoder before its worker thread is started. Never touch partial
    file lists/sections or count a failed encode as completed.
    """
    if hasattr(writer, "_create_segment_encoder"):
        create = writer._create_segment_encoder

        def create_observed(*args, **kwargs):
            encoder = create(*args, **kwargs)
            write = encoder.write_frame

            def write_repeated(frame, *, repeat=1):
                for _ in range(repeat):
                    write(frame, repeat=1)
                    progress.completed(1)

            encoder.write_frame = write_repeated
            return encoder

        writer._create_segment_encoder = create_observed
    elif hasattr(writer, "encode_and_write_frame"):
        progress.write_frame = writer.encode_and_write_frame
        writer.encode_and_write_frame = progress.write_batch
    else:
        progress.write_frame = writer.write_frame
        writer.write_frame = progress.write
