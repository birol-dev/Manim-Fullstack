"""A brand logo renders in its corner, and a missing or broken upload changes nothing."""

import ast
import logging
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

pytest.importorskip("manim")

from studio import registry  # noqa: E402
from studio.dev import render_preview  # noqa: E402
from studio.formats import ASPECT_RATIOS  # noqa: E402

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


# --------------------------------------------------------------------------- #
# The placement contract, every template and every aspect (no render)
# --------------------------------------------------------------------------- #

LOGO_REGIONS = ("top-left", "top-right", "bottom-left", "bottom-right")
ASPECTS = tuple(ASPECT_RATIOS)


def _literal_assignments(path, class_name, names):
    """Literal ``name = value`` assignments in ``class_name``, without importing Manim."""
    found = {}
    for node in ast.parse(Path(path).read_text(encoding="utf-8")).body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for statement in node.body:
            if (isinstance(statement, ast.Assign) and len(statement.targets) == 1
                    and isinstance(statement.targets[0], ast.Name)
                    and statement.targets[0].id in names):
                try:
                    found[statement.targets[0].id] = ast.literal_eval(statement.value)
                except (ValueError, SyntaxError):
                    pass
    return found


def _scene_path(template_id):
    return Path(registry.TEMPLATES_DIR) / template_id / "scene.py"


def _logo_min_height():
    source = Path(registry.__file__).with_name("kit") / "scene.py"
    for node in ast.parse(source.read_text(encoding="utf-8")).body:
        if (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "LOGO_MIN_HEIGHT"):
            return ast.literal_eval(node.value)
    raise AssertionError("the kit declares no LOGO_MIN_HEIGHT")


@pytest.mark.parametrize("template_id", registry.template_ids())
def test_logo_region_is_valid_for_every_aspect(template_id):
    declared = _literal_assignments(_scene_path(template_id), "Template", {"logo_region"})
    region = declared.get("logo_region")
    assert region is not None, f"{template_id} needs its own logo_region"
    if isinstance(region, dict):
        assert set(region) == set(ASPECTS), f"{template_id} must name every aspect"
        corners = list(region.values())
    else:
        corners = [region]
    for corner in corners:
        assert corner in LOGO_REGIONS, f"{template_id}: {corner!r} is not a corner"


@pytest.mark.parametrize("template_id", registry.template_ids())
def test_logo_height_never_shrinks_below_the_floor(template_id):
    declared = _literal_assignments(_scene_path(template_id), "Template", {"logo_height"})
    height = declared.get("logo_height")
    if height is None:
        return
    if isinstance(height, dict):
        assert set(height) == set(ASPECTS), f"{template_id} must name every aspect"
        values = list(height.values())
    else:
        values = [height]
    for value in values:
        assert isinstance(value, (int, float)) and not isinstance(value, bool)
        assert _logo_min_height() <= value <= 15, f"{template_id}: {value} is outside the logo band"


@pytest.mark.parametrize("template_id", registry.template_ids())
def test_logo_reservations_only_name_real_aspects(template_id):
    declared = _literal_assignments(_scene_path(template_id), "Template",
                                    {"logo_reserved_aspects", "logo_reserved_layouts"})
    aspects = declared.get("logo_reserved_aspects")
    if aspects is not None:
        assert set(aspects) <= set(ASPECTS), f"{template_id}: unknown reserved aspect"
    layouts = declared.get("logo_reserved_layouts")
    if layouts is not None:
        assert isinstance(layouts, dict) and set(layouts) <= set(ASPECTS)
        for names in layouts.values():
            assert names and all(isinstance(name, str) for name in names)
