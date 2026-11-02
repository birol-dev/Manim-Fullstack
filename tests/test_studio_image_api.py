"""Crop provenance endpoints leave plain image fields and the MCP upload contract intact."""
import base64
from pathlib import Path

import pytest

import main
from studio import service as service_module
from studio.storage import ImageCropStore
from tests.conftest import LocalClient
from tests.studio_fakes import make_service, tiny_png
from tests.test_studio_image_storage import RECIPE


@pytest.fixture
def images_api(tmp_path, monkeypatch):
    service, _worker = make_service(tmp_path)
    monkeypatch.setattr(service_module, "service", service)
    assets = Path(service.assets_dir)
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "original.jpg").write_bytes(tiny_png(16, 10))
    (assets / "crop.png").write_bytes(tiny_png(6, 6))
    yield LocalClient(main.app, base_url="http://localhost"), service
    service.shutdown_sync()


def test_get_and_save_recipe_and_reload(images_api):
    api, service = images_api
    assert api.get("/api/studio/images/original.jpg").json() == {"name": "original.jpg", "crop": None}
    result = api.post("/api/studio/images/crop.png/crop", json=RECIPE)
    assert result.status_code == 200, result.text
    assert result.json() == {"name": "crop.png", "crop": RECIPE}
    service.configure(service.workspace_dir, service.media_dir, service.assets_dir)
    assert api.get("/api/studio/images/crop.png").json() == result.json()
    assert api.post("/api/studio/images/crop.png/crop", json=RECIPE).status_code == 200
    project = api.post("/api/studio/projects", json={"template": "quote", "params": {"avatar": "crop.png"}})
    assert project.status_code == 201, project.text
    assert project.json()["params"]["avatar"] == "crop.png"


def test_missing_bad_and_conflicting_records(images_api):
    api, service = images_api
    assert api.get("/api/studio/images/missing.png").status_code == 404
    assert api.post("/api/studio/images/crop.png/crop", json={**RECIPE, "source": "missing.jpg"}).status_code == 404
    assert api.post("/api/studio/images/crop.png/crop", json={**RECIPE, "source": "../outside.jpg"}).status_code == 422
    assert api.get("/api/studio/images/NUL.png").status_code == 422
    assert api.post("/api/studio/images/crop.png/crop", json={**RECIPE, "extra": True}).status_code == 422
    assert api.post("/api/studio/images/crop.png/crop", json={**RECIPE, "position": {"x": 0, "y": 0, "zoom": 10}}).status_code == 422
    api.post("/api/studio/images/crop.png/crop", json=RECIPE)
    changed = {**RECIPE, "position": {"x": 0, "y": 0, "zoom": 3}}
    assert api.post("/api/studio/images/crop.png/crop", json=changed).status_code == 409
    Path(ImageCropStore(service.workspace_dir, service.assets_dir).record_path("crop.png")).write_text("broken")
    assert api.get("/api/studio/images/crop.png").json() == {"name": "crop.png", "crop": None}


def test_mcp_style_image_has_no_recipe_and_still_uses_a_plain_name(images_api):
    api, _service = images_api
    uploaded = api.post("/api/studio/images", json={"data": base64.b64encode(tiny_png(4, 3)).decode()})
    assert uploaded.status_code == 201
    assert set(uploaded.json()) == {"name", "width", "height"}
    name = uploaded.json()["name"]
    assert api.get(f"/api/studio/images/{name}").json() == {"name": name, "crop": None}


@pytest.mark.parametrize("missing", ["source", "record"])
def test_deleted_source_or_record_falls_back_to_the_still_usable_crop(images_api, monkeypatch, missing):
    api, service = images_api
    monkeypatch.setattr(main, "ASSETS_DIR", service.assets_dir)
    crop = Path(service.assets_dir) / "crop.png"
    before = crop.read_bytes()
    assert api.post("/api/studio/images/crop.png/crop", json=RECIPE).status_code == 200
    project = api.post("/api/studio/projects", json={"template": "quote", "params": {"avatar": "crop.png"}}).json()
    if missing == "source":
        # Explicit user deletion stays allowed; no changes to the existing endpoint.
        deleted = api.delete("/api/assets", params={"filename": "original.jpg"})
        assert deleted.status_code == 200, deleted.text
        assert not (Path(service.assets_dir) / "original.jpg").exists()
    else:
        Path(ImageCropStore(service.workspace_dir, service.assets_dir).record_path("crop.png")).unlink()
    service.configure(service.workspace_dir, service.media_dir, service.assets_dir)
    info = api.get("/api/studio/images/crop.png")
    assert info.status_code == 200, info.text
    assert info.json() == {"name": "crop.png", "crop": None}
    assert api.get(f"/api/studio/projects/{project['id']}").json()["params"]["avatar"] == "crop.png"
    assert crop.read_bytes() == before
    assert api.get("/assets/crop.png").content == before
    # A subsequent Adjust can now save a new crop using the current image as its source.
    (Path(service.assets_dir) / "reframed.png").write_bytes(tiny_png(3, 3))
    saved = api.post("/api/studio/images/reframed.png/crop", json={**RECIPE, "source": "crop.png"})
    assert saved.status_code == 200, saved.text
    assert saved.json()["crop"]["source"] == "crop.png"

