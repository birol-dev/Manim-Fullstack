"""A brand logo renders in its corner, and a missing or broken upload changes nothing."""

import logging

import numpy as np
from PIL import Image
import pytest

pytest.importorskip("manim")

from studio import registry  # noqa: E402
from studio.dev import render_preview  # noqa: E402

PARAMS = {"seconds": 3, "title": "Launch time", "style": "ring", "finish_text": "Go!", "confetti": False}


def poster(path, settings, assets, media):
    render_preview("countdown", PARAMS, settings, "poster", str(path), short=180,
                   assets_dir=str(assets), media_dir=str(media))
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB")).copy()


def test_logo_draws_in_a_corner_and_bad_files_are_skipped(tmp_path, caplog):
    assets = tmp_path / "assets"
    assets.mkdir()
    Image.new("RGB", (96, 48), "#E11D48").save(assets / "brand.png")
    (assets / "broken.png").write_bytes(b"this is not a picture")

    base = {"aspect": "16:9", "theme": "clean"}
    plain = poster(tmp_path / "plain.png", base, assets, tmp_path / "media")

    with caplog.at_level(logging.WARNING, logger="studio.kit.scene"):
        missing = poster(tmp_path / "missing.png", {**base, "brand": {"logo": "missing.png"}},
                         assets, tmp_path / "media")
    assert "missing.png" in caplog.text

    with caplog.at_level(logging.WARNING, logger="studio.kit.scene"):
        broken = poster(tmp_path / "broken.png", {**base, "brand": {"logo": "broken.png"}},
                        assets, tmp_path / "media")
    assert "broken.png" in caplog.text

    # No logo (and no readable logo) is pixel-for-pixel today's render.
    assert np.array_equal(plain, missing)
    assert np.array_equal(plain, broken)

    logo = poster(tmp_path / "logo.png", {**base, "brand": {"logo": "brand.png"}}, assets, tmp_path / "media")
    difference = np.abs(logo.astype(int) - plain.astype(int)).max(axis=2)
    ys, xs = np.nonzero(difference > 2)
    assert len(xs) > 80, "the logo should be visible"
    height, width = plain.shape[:2]
    assert xs.min() > width * 0.6 and ys.min() > height * 0.6, "countdown's logo belongs bottom-right"
    painted = logo[ys, xs].astype(int)
    assert painted[:, 0].max() > 180 and painted[:, 0].mean() > painted[:, 1].mean()


def test_a_full_bleed_card_never_hides_the_logo(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    Image.new("RGB", (96, 48), "#FF00FF").save(assets / "brand.png")
    spec = registry.get_template("announcement")
    preset = next(item for item in spec.presets if item.id == "event-invite")
    path = tmp_path / "poster.png"
    render_preview("announcement", preset.params,
                   {**preset.settings, "aspect": "16:9", "brand": {"logo": "brand.png"}},
                   "poster", str(path), short=360, assets_dir=str(assets),
                   media_dir=str(tmp_path / "media"))

    with Image.open(path) as image:
        pixels = np.asarray(image.convert("RGB")).astype(int)
    magenta = (pixels[:, :, 0] > 240) & (pixels[:, :, 1] < 20) & (pixels[:, :, 2] > 240)
    ys, xs = np.nonzero(magenta)
    assert len(xs) > 40, "the ticket surface must not paint over the logo"
    assert xs.min() > pixels.shape[1] * 0.6 and ys.max() < pixels.shape[0] * 0.25
