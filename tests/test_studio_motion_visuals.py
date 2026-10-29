"""Compare encoded warm previews to fresh stills of the very same live scene state."""
import shutil

import numpy as np
import pytest

pytest.importorskip("manim")

from studio import registry
from tests.studio_motion_visuals import probe_motion

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg is needed to decode motion frames")

CASES = [("announcement", "weekend-sale"), ("celebration", "happy-birthday"),
         ("celebration", "followers-milestone"), ("countdown", "classroom-timer"),
         ("countdown", "break-timer"), ("countdown", "launch-countdown"),
         ("quiz", "general-knowledge"), ("quote", "inspirational-quote"),
         ("year_in_review", "personal-year")]


@pytest.mark.parametrize("template,preset", CASES)
def test_encoded_motion_matches_fresh_scene_stills(tmp_path, template, preset):
    spec = registry.get_template(template).public()
    card = next(p for p in spec["presets"] if p["id"] == preset)
    _, metrics = probe_motion(tmp_path, template, card["params"],
                              {"aspect": spec["default_aspect"], **card["settings"]}, long_side=720)
    assert len(metrics) == 5
    for frame, difference in metrics.items():
        assert difference["stale_objects"] == 0, f"{preset} frame {frame}: detached objects in Cairo's render list"
        # Allow tiny Cairo edge/alpha differences between a reused context and a
        # fresh one (<0.1/255 mean, <0.2% pixels). The original countdown's stale
        # digits exceeded both limits and retained four detached glyph objects.
        assert difference["raw_mean"] < 0.1, (preset, frame, difference)
        assert difference["raw_bad_pixels"] < 0.002, (preset, frame, difference)
        # H.264's YUV420 chroma subsampling visibly affects tiny saturated text;
        # permit that codec error while also checking the actual encoded movie.
        assert difference["mean"] < 5.0, (preset, frame, difference)
        assert difference["bad_pixels"] < 0.06, (preset, frame, difference)


def test_counter_keeps_slots_when_the_number_changes_width(tmp_path):
    from manim import tempconfig
    from studio.kit.counter import Counter

    with tempconfig({"media_dir": str(tmp_path)}):
        counter = Counter(100, sample_values=(1000,)).set_z_index(23)
        slots = list(counter.submobjects)
        counter.set_value(9)
        assert counter.submobjects == slots[:1]
        assert all(not slot.has_points() for slot in slots[1:])
        size = counter.width, counter.height
        counter.shift(np.array([5, 4, 0]))
        assert (counter.width, counter.height) == pytest.approx(size)
        counter.set_value(1000)
        assert counter.submobjects[:3] == slots
        assert all(mob.z_index == 23 for mob in counter.get_family())
        assert len([slot for slot in counter.submobjects if slot.has_points()]) == len(counter.text_for(1000).replace(" ", "").replace("\u202f", ""))
        assert np.isfinite(counter.get_all_points()).all()
