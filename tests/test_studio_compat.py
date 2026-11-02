"""Output intent and finalized artifacts across the legacy and OutputSpec APIs."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from studio.compat import movie_has_sound, output_cli_args, output_config, written_movie, writes_movie


@pytest.mark.parametrize("still,dry_run,expected", [(True, False, "png"), (False, False, "mp4"),
                                                   (False, True, "none")])
def test_output_spec_config_uses_one_unambiguous_format(still, dry_run, expected):
    # A 0.22 config has no write_to_movie; unknown tempconfig keys are ignored.
    values = output_config(still=still, dry_run=dry_run, transparent=True, cfg=SimpleNamespace())
    assert values == {"format": expected, "transparent": True, "dry_run": dry_run}


def test_legacy_output_flags_preserve_still_and_motion_behavior():
    assert output_config(still=True, cfg=SimpleNamespace(write_to_movie=True)) == {
        "save_last_frame": True, "write_to_movie": False, "format": "mp4", "transparent": False, "dry_run": False}
    assert output_config(cfg=SimpleNamespace(write_to_movie=True))["write_to_movie"] is True


@pytest.mark.parametrize("video,gif,sound", [(True, False, True), (True, True, False), (False, False, False)])
def test_sound_uses_captured_output_spec_not_mutable_global_config(video, gif, sound):
    scene = SimpleNamespace(renderer=SimpleNamespace(file_writer=SimpleNamespace(
        output_spec=SimpleNamespace(is_video=video, is_gif=gif))))
    assert writes_movie(scene) == video
    assert movie_has_sound(scene) == sound


def test_movie_path_prefers_completed_artifact_and_refuses_stills():
    writer = SimpleNamespace(output_spec=SimpleNamespace(is_video=True),
                             final_file_path=Path("finished.mov"), movie_file_path=Path("planned.mov"),
                             partial_movie_files=["silent-cache.mp4"])
    assert written_movie(writer) == Path("finished.mov")
    writer.final_file_path = None
    assert written_movie(writer) == Path("planned.mov")
    writer.output_spec.is_video = False
    assert written_movie(writer) is None


def test_legacy_gif_path_is_not_the_intermediate_movie():
    manim = pytest.importorskip("manim")
    if not hasattr(manim.config, "write_to_movie"):
        pytest.skip("Legacy file-writer contract")
    writer = SimpleNamespace(movie_file_path="silent.mp4", gif_file_path="finished.gif")
    with manim.tempconfig({"format": "gif"}):
        assert written_movie(writer) == Path("finished.gif")


@pytest.mark.parametrize("fmt", ["mp4", "webm", "mov", "gif", "png"])
def test_cli_keeps_formats_and_progress_compatible(fmt):
    args = output_cli_args(fmt, transparent=fmt in ("webm", "mov", "png"))
    assert args.count("--progress_bar=none") == 1
    assert "--write_to_movie" not in args
    if fmt != "mp4":
        assert args[args.index("--format") + 1] == fmt


def test_real_tempconfig_restores_movie_intent_after_transparent_still():
    manim = pytest.importorskip("manim")
    original = manim.config.copy()
    with manim.tempconfig(output_config(still=True, transparent=True)):
        assert manim.config.save_last_frame and manim.config.transparent
        if hasattr(manim.config, "write_to_movie"):
            assert not manim.config.write_to_movie
        else:
            assert manim.config.format == "png"
    assert manim.config == original
    with manim.tempconfig(output_config()):
        assert not manim.config.save_last_frame and not manim.config.transparent
    assert manim.config == original
