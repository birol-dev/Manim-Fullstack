"""Crop provenance is optional, persistent, immutable and confined to the workspace."""
import copy
import json
from pathlib import Path

import pytest

from studio.storage import ImageCropStore
from tests.studio_fakes import tiny_png

RECIPE = {"source": "original.jpg", "position": {"x": .4, "y": -.2, "zoom": 2.5}, "ratio": 1, "shape": "circle"}


@pytest.fixture
def images(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "original.jpg").write_bytes(tiny_png(16, 10))
    (assets / "crop.png").write_bytes(tiny_png(6, 6))
    return ImageCropStore(str(tmp_path), str(assets))


def test_recipe_survives_a_new_store_and_does_not_change_image_bytes(images, tmp_path):
    before = Path(images.image_path("original.jpg")).read_bytes()
    assert images.write("crop.png", RECIPE) == RECIPE
    reopened = ImageCropStore(str(tmp_path), images.assets)
    assert reopened.read("crop.png") == RECIPE
    assert reopened.referring_crops("original.jpg") == ["crop.png"]
    assert Path(images.image_path("original.jpg")).read_bytes() == before
    assert images.write("crop.png", RECIPE) == RECIPE  # a retried request is idempotent
    assert Path(images.record_path("crop.png")).parent == tmp_path / "studio" / "image-crops"


def test_missing_records_and_images_have_no_crop_history(images):
    assert images.read("original.jpg") is None
    assert images.read("missing.png") is None
    assert images.referring_crops("original.jpg") == []
    with pytest.raises(FileNotFoundError):
        images.write("missing.png", RECIPE)
    with pytest.raises(FileNotFoundError):
        images.write("crop.png", {**RECIPE, "source": "missing.jpg"})


@pytest.mark.parametrize("name", ["../private.png", "..\\private.png", "/private.png", "C:\\private.png", "C:private.png",
                                  "one/two.png", "..", "NUL.png", "photo.jpg:stream.png", "a\x00.png", "a\n.png", ".hidden.png", "document.txt", 3])
def test_names_cannot_escape_or_address_non_images(images, name):
    with pytest.raises(ValueError):
        images.image_path(name)
    with pytest.raises(ValueError):
        images.write("crop.png", {**RECIPE, "source": name})


@pytest.mark.parametrize("patch", [
    {"position": None}, {"position": {"x": 0, "y": 0}}, {"position": {"x": True, "y": 0, "zoom": 1}},
    {"position": {"x": 2, "y": 0, "zoom": 1}}, {"position": {"x": 0, "y": 0, "zoom": 0}},
    {"position": {"x": 0, "y": 0, "zoom": 5}}, {"ratio": 0}, {"ratio": float("nan")}, {"ratio": True},
    {"position": {"x": float("inf"), "y": 0, "zoom": 1}}, {"ratio": 2}, {"shape": "square"}, {"shape": []},
])
def test_bad_recipes_are_not_written(images, patch):
    with pytest.raises(ValueError):
        images.write("crop.png", {**RECIPE, **patch})
    assert not Path(images.record_path("crop.png")).exists()


@pytest.mark.parametrize("damage", ["json", "list", "version", "name", "source", "position", "digest"])
def test_bad_records_fall_back_without_following_untrusted_paths(images, damage):
    images.write("crop.png", RECIPE)
    path = Path(images.record_path("crop.png"))
    data = json.loads(path.read_text())
    if damage == "json":
        path.write_text("{truncated")
    elif damage == "list":
        path.write_text("[]")
    else:
        if damage == "version": data["version"] = 2
        if damage == "name": data["name"] = "other.png"
        if damage == "source": data["crop"]["source"] = "../secret.png"
        if damage == "position": data["crop"]["position"]["zoom"] = -1
        if damage == "digest": data["image_hash"] = "bad"
        path.write_text(json.dumps(data))
    assert images.read("crop.png") is None
    assert images.referring_crops("original.jpg") == []


@pytest.mark.parametrize("name", ["original.jpg", "crop.png"])
def test_replaced_or_missing_images_invalidate_a_recipe(images, name):
    images.write("crop.png", RECIPE)
    Path(images.image_path(name)).write_bytes(b"replaced")
    assert images.read("crop.png") is None
    Path(images.image_path(name)).unlink()
    assert images.read("crop.png") is None
    assert images.referring_crops("original.jpg") == []


def test_recipes_cannot_form_chains_or_be_reassigned(images):
    images.write("crop.png", RECIPE)
    changed = copy.deepcopy(RECIPE)
    changed["position"]["zoom"] = 3
    with pytest.raises(FileExistsError): images.write("crop.png", changed)
    with pytest.raises(ValueError): images.write("crop.png", {**RECIPE, "source": "crop.png"})
    Path(images.image_path("second.png")).write_bytes(tiny_png(4, 4))
    with pytest.raises(ValueError): images.write("second.png", {**RECIPE, "source": "crop.png"})
    with pytest.raises(ValueError): images.write("original.jpg", {**RECIPE, "source": "second.png"})
    assert images.read("crop.png") == RECIPE


def test_image_and_record_symlinks_cannot_read_outside_the_workspace(images, tmp_path):
    outside = tmp_path / "outside.png"
    outside.write_bytes(tiny_png(4, 4))
    link = Path(images.assets) / "link.png"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("This Windows account cannot create symlinks.")
    with pytest.raises(ValueError): images.write("crop.png", {**RECIPE, "source": "link.png"})
    images.write("crop.png", RECIPE)
    record = Path(images.record_path("crop.png"))
    record.unlink()
    record.symlink_to(outside)
    assert images.read("crop.png") is None

