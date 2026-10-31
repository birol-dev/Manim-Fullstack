"""Portable project files: one saved file that opens on another computer, safely."""

import base64
import hashlib
import io
import json
import os
import stat
import zipfile
from urllib.parse import unquote

import numpy as np
import pytest
from PIL import Image

import main
from studio import portable, registry
from studio import service as service_module
from studio.errors import StudioError
from studio.storage import ImageCropStore
from tests.conftest import LocalClient
from tests.studio_fakes import FakeRunner, RunnerFactory, make_service, tiny_png


def make(tmp_path, name="ws"):
    folder = tmp_path / name
    folder.mkdir(parents=True, exist_ok=True)
    svc, worker = make_service(folder, runners=RunnerFactory(FakeRunner("ok")))
    svc.fake = worker
    return svc


def write_asset(svc, name, data):
    os.makedirs(svc.assets_dir, exist_ok=True)
    with open(os.path.join(svc.assets_dir, name), "wb") as target:
        target.write(data)
    return name


def colored_png(width, height, color):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, "PNG")
    return buffer.getvalue()


def agent_name(data, extension=".png"):
    """The name add_image_sync gives these bytes (content, not the file it came from)."""
    return f"agent-{hashlib.sha256(data).hexdigest()[:16]}{extension}"


def music(svc):
    import numpy as np

    from studio.audio import pcm_bytes

    t = np.arange(4800) / 48000
    return svc.upload_audio_sync(pcm_bytes(np.sin(2 * np.pi * 440 * t) * .2), "music.wav")["name"]


def document(template="countdown", title="School video", params=None, settings=None, version=1):
    return {"format": version, "app_version": "test", "template": template, "title": title,
            "params": params or {}, "settings": settings or {}}


def zipped(entries, compression=zipfile.ZIP_DEFLATED):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression) as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return buffer.getvalue()


def open_file(svc, data, filename="file.manimstudio"):
    return svc.open_project_file_sync(base64.b64encode(data).decode("ascii"), filename)


def countdown_document(title="School video", **params):
    return document(template="countdown", title=title,
                    params={"seconds": 30, "title": "Read", **params},
                    settings={"aspect": "16:9", "theme": "clean"})


def test_a_real_project_with_an_image_logo_and_sound_round_trips(tmp_path):
    svc = make(tmp_path, "first")
    photo = write_asset(svc, "photo.png", tiny_png(36, 24))
    logo = write_asset(svc, "logo.png", tiny_png(20, 10))
    track = music(svc)
    preset = next(item for item in registry.get_template("celebration").presets if item.id == "happy-birthday")
    project = svc.create_project_sync(
        "celebration", {**preset.params, "photo": photo},
        {**preset.settings, "aspect": "9:16", "brand": {"logo": logo},
         "sound": {"music": {"asset": track}}},
        "School video")

    saved = svc.project_file_sync(project["id"])
    try:
        raw = open(saved["path"], "rb").read()
    finally:
        os.unlink(saved["path"])
    assert saved["filename"] == "school-video.manimstudio" and saved["note"] is None
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = set(archive.namelist())
        project_bytes = archive.read("project.json")
        carried = json.loads(project_bytes)
    assert names == {"project.json", "assets/photo.png", "assets/logo.png", f"assets/{track}"}
    assert set(carried) == {"format", "app_version", "template", "title", "params", "settings"}
    assert carried["template"] == "celebration" and carried["title"] == "School video"
    # Nothing about this computer: no drive, no workspace path, no project id or timestamps.
    assert b"C:" not in project_bytes
    assert str(tmp_path).encode("utf-8") not in project_bytes
    assert b'"id"' not in project_bytes and b'"created"' not in project_bytes

    second = make(tmp_path, "second")
    result = open_file(second, raw)
    opened = result["project"]
    assert opened["id"] != project["id"] and result["notes"] == []
    assert opened["title"] == "School video"
    assert opened["params"]["photo"].startswith("agent-") and opened["params"]["photo"].endswith(".png")
    assert opened["settings"]["brand"]["logo"].startswith("agent-")
    assert opened["settings"]["sound"]["music"]["asset"].startswith("audio-")
    assert open(os.path.join(second.assets_dir, opened["params"]["photo"]), "rb").read() == tiny_png(36, 24)
    assert open(os.path.join(second.assets_dir, opened["settings"]["brand"]["logo"]), "rb").read() == tiny_png(20, 10)
    assert os.path.isfile(second.audio_path(opened["settings"]["sound"]["music"]["asset"]))

    # With the original and the copy in hand, a real poster renders pixel-for-pixel the same.
    pytest.importorskip("manim")
    from studio.dev import render_preview

    Image.new("RGB", (60, 40), "#2563EB").save(os.path.join(svc.assets_dir, "picture.png"))
    Image.new("RGB", (48, 24), "#E11D48").save(os.path.join(svc.assets_dir, "brand.png"))
    settings = {"aspect": "9:16", "theme": "clean", "brand": {"logo": "brand.png"}}
    params = {**preset.params, "photo": "picture.png"}
    original = tmp_path / "original.png"
    replay = tmp_path / "replay.png"
    render_preview("celebration", params, settings, "poster", str(original), short=180,
                   assets_dir=svc.assets_dir, media_dir=str(tmp_path / "media-original"))
    project = svc.create_project_sync("celebration", params, settings, "Rendered")
    saved = svc.project_file_sync(project["id"])
    try:
        raw = open(saved["path"], "rb").read()
    finally:
        os.unlink(saved["path"])
    again = open_file(make(tmp_path, "third"), raw)["project"]
    render_preview("celebration", again["params"], again["settings"], "poster", str(replay), short=180,
                   assets_dir=os.path.join(str(tmp_path), "third", "ws", "assets"),
                   media_dir=str(tmp_path / "media-replay"))
    with Image.open(original) as first, Image.open(replay) as second_image:
        assert np.array_equal(np.asarray(first.convert("RGB")), np.asarray(second_image.convert("RGB")))


def test_a_cropped_photo_carries_its_crop_and_poster_to_another_computer(tmp_path):
    svc = make(tmp_path, "first")
    source_bytes = colored_png(120, 80, "#F59E0B")
    crop_bytes = colored_png(40, 40, "#2563EB")
    source = write_asset(svc, "portrait.png", source_bytes)
    cropped = write_asset(svc, "portrait-crop.png", crop_bytes)
    recipe = {"source": source, "position": {"x": .3, "y": -.2, "zoom": 2}, "ratio": 1, "shape": "circle"}
    svc.save_image_crop_sync(cropped, recipe)
    preset = next(item for item in registry.get_template("celebration").presets if item.id == "happy-birthday")
    params = {**preset.params, "photo": cropped}
    settings = {**preset.settings, "aspect": "9:16", "theme": "clean"}
    project = svc.create_project_sync("celebration", params, settings, "Cropped photo")

    saved = svc.project_file_sync(project["id"])
    try:
        raw = open(saved["path"], "rb").read()
    finally:
        os.unlink(saved["path"])
    assert saved["note"] is None
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        carried = json.loads(archive.read("project.json"))
        names = set(archive.namelist())
    assert carried["crops"] == {cropped: recipe}
    # The crop's original travels too, or the recipe cannot be restored.
    assert names == {"project.json", f"assets/{cropped}", f"assets/{source}"}

    second = make(tmp_path, "second")
    result = open_file(second, raw)
    opened = result["project"]
    assert result["notes"] == []
    assert opened["params"]["photo"] == agent_name(crop_bytes)
    stored_crop = opened["params"]["photo"]
    stored_source = agent_name(source_bytes)
    assert ImageCropStore(second.workspace_dir, second.assets_dir).read(stored_crop) == {
        **recipe, "source": stored_source}
    with open(os.path.join(second.assets_dir, stored_source), "rb") as original_source:
        assert original_source.read() == source_bytes

    # Opening the same file again reuses the same stored names and leaves the crop alone.
    again = open_file(second, raw)
    assert again["notes"] == []
    assert again["project"]["params"]["photo"] == stored_crop
    assert ImageCropStore(second.workspace_dir, second.assets_dir).read(stored_crop) == {
        **recipe, "source": stored_source}

    pytest.importorskip("manim")
    from studio.dev import render_preview

    original, replay = tmp_path / "original.png", tmp_path / "replay.png"
    render_preview("celebration", params, settings, "poster", str(original), short=180,
                   assets_dir=svc.assets_dir, media_dir=str(tmp_path / "media-original"))
    render_preview("celebration", opened["params"], opened["settings"], "poster", str(replay), short=180,
                   assets_dir=second.assets_dir, media_dir=str(tmp_path / "media-replay"))
    with Image.open(original) as first, Image.open(replay) as second_image:
        assert np.array_equal(np.asarray(first.convert("RGB")), np.asarray(second_image.convert("RGB")))


def test_an_existing_crop_here_is_not_overwritten_by_an_opened_file(tmp_path):
    svc = make(tmp_path, "first")
    source_bytes = colored_png(120, 80, "#F59E0B")
    crop_bytes = colored_png(40, 40, "#2563EB")
    source = write_asset(svc, "portrait.png", source_bytes)
    cropped = write_asset(svc, "portrait-crop.png", crop_bytes)
    sent = {"source": source, "position": {"x": .3, "y": -.2, "zoom": 2}, "ratio": 1, "shape": "circle"}
    svc.save_image_crop_sync(cropped, sent)
    project = svc.create_project_sync("celebration", {"photo": cropped}, {"aspect": "9:16"}, "Cropped")
    saved = svc.project_file_sync(project["id"])
    try:
        raw = open(saved["path"], "rb").read()
    finally:
        os.unlink(saved["path"])

    target = make(tmp_path, "second")
    stored = target.add_image_sync(crop_bytes)["name"]
    stored_source = target.add_image_sync(source_bytes)["name"]
    here = {"source": stored_source, "position": {"x": -.5, "y": .5, "zoom": 3}, "ratio": 1, "shape": "circle"}
    target.save_image_crop_sync(stored, here)

    result = open_file(target, raw)
    assert result["project"]["params"]["photo"] == stored
    assert ImageCropStore(target.workspace_dir, target.assets_dir).read(stored) == here
    assert any(note.startswith("portrait-crop.png") and "different crop" in note
               for note in result["notes"])


def test_a_file_without_crops_still_opens_with_its_picture_uncropped(tmp_path):
    svc = make(tmp_path)
    raw = zipped([("project.json", json.dumps(document(
        "celebration", params={"photo": "photo.png"}, settings={"aspect": "9:16"})).encode()),
        ("assets/photo.png", tiny_png(30, 20))])
    result = open_file(svc, raw)
    stored = result["project"]["params"]["photo"]
    assert stored == agent_name(tiny_png(30, 20))
    assert result["notes"] == []
    assert ImageCropStore(svc.workspace_dir, svc.assets_dir).read(stored) is None
    assert not os.path.isdir(os.path.join(svc.workspace_dir, "studio", "image-crops"))


def test_hostile_crops_open_safely_and_stay_inside_the_crop_folder(tmp_path):
    picture = tiny_png(12, 8)
    good = {"source": "photo.png", "position": {"x": 0, "y": 0, "zoom": 1}, "ratio": 2, "shape": "free"}
    cases = [
        (["not", "a", "dict"], False),
        ({"unknown.png": good, "../escape.png": good, "C:\\escape.png": good}, False),
        ({"photo.png": "not a recipe"}, False),
        ({"photo.png": None}, False),
        ({"photo.png": {**good, "source": "photo.png"}}, True),
        ({"photo.png": {**good, "source": "../../outside.png"}}, True),
        ({"photo.png": {**good, "source": "absent.png"}}, True),
        ({"photo.png": {**good, "source": "photo.png", "position": {"x": float("inf"), "y": 0, "zoom": 1}}}, True),
        ({"photo.png": {**good, "source": "photo.png", "ratio": float("nan")}}, True),
        ({"photo.png": {**good, "source": "photo.png", "shape": "1:0"}}, True),
    ]
    for index, (crops, named) in enumerate(cases):
        svc = make(tmp_path, f"hostile-{index}")
        doc = document("celebration", params={"photo": "photo.png"}, settings={"aspect": "9:16"})
        doc["crops"] = crops
        raw = zipped([("project.json", json.dumps(doc).encode()), ("assets/photo.png", picture)])
        opened = open_file(svc, raw)
        stored = opened["project"]["params"]["photo"]
        assert stored == agent_name(picture)
        assert bool(opened["notes"]) is named
        if named:
            assert "photo.png" in opened["notes"][0] and "default" in opened["notes"][0]
        assert ImageCropStore(svc.workspace_dir, svc.assets_dir).read(stored) is None
        crops_dir = os.path.join(svc.workspace_dir, "studio", "image-crops")
        assert not os.path.isdir(crops_dir) or os.listdir(crops_dir) == []
        assert all(entry.name.startswith("agent-") for entry in os.scandir(svc.assets_dir))
        home = tmp_path / f"hostile-{index}"
        assert not (home / "outside.png").exists() and not (home / "escape.png").exists()


def test_a_project_without_assets_still_saves_and_opens(tmp_path):
    svc = make(tmp_path)
    project = svc.create_project_sync("countdown", {"seconds": 30, "title": "Read"}, {}, "Plain timer")
    saved = svc.project_file_sync(project["id"])
    raw = open(saved["path"], "rb").read()
    os.unlink(saved["path"])
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert archive.namelist() == ["project.json"]
    opened = open_file(make(tmp_path, "other"), raw)
    assert opened["project"]["title"] == "Plain timer"
    assert opened["project"]["params"]["seconds"] == 30
    assert opened["notes"] == []


def test_a_missing_asset_is_named_and_the_project_still_opens(tmp_path):
    svc = make(tmp_path)
    project = svc.create_project_sync(
        "celebration", {"photo": "gone.png", "name": "Ada"}, {"brand": {"logo": "missing.png"}}, "Half here")
    info = svc.project_file_info_sync(project["id"])
    assert info["notes"] and "gone.png" in info["notes"][0] and "missing.png" in info["notes"][0]
    saved = svc.project_file_sync(project["id"])
    assert saved["note"] and "gone.png" in saved["note"]
    try:
        raw = open(saved["path"], "rb").read()
    finally:
        os.unlink(saved["path"])
    opened = open_file(make(tmp_path, "other"), raw)
    assert opened["project"]["params"]["photo"] is None
    assert opened["project"]["settings"]["brand"]["logo"] is None
    assert opened["notes"] and "gone.png" in opened["notes"][0]


def test_a_refused_asset_falls_back_to_the_designs_default(tmp_path):
    raw = zipped([("project.json", json.dumps(document(
        "celebration", params={"photo": "bad.png"}, settings={"aspect": "9:16"})).encode()),
        ("assets/bad.png", b"this is not a picture")])
    opened = open_file(make(tmp_path), raw)
    assert opened["project"]["params"]["photo"] is None
    assert len(opened["notes"]) == 1 and "bad.png" in opened["notes"][0]


def test_a_title_that_exists_becomes_a_copy_and_nothing_is_overwritten(tmp_path):
    svc = make(tmp_path)
    existing = svc.create_project_sync("countdown", {"seconds": 30}, {}, "School video")
    before = svc._read_project(svc._project_path(existing["id"]))
    opened = open_file(svc, zipped([("project.json", json.dumps(countdown_document()).encode())]))
    assert opened["project"]["id"] != existing["id"]
    assert opened["project"]["title"] == "School video (copy)"
    assert svc._read_project(svc._project_path(existing["id"])) == before
    assert len(svc.list_projects_sync()) == 2


def test_invalid_params_keep_what_is_valid_and_the_project_opens(tmp_path):
    doc = countdown_document(seconds="not a number")
    opened = open_file(make(tmp_path), zipped([("project.json", json.dumps(doc).encode())]))
    assert opened["project"]["params"]["title"] == "Read"
    assert opened["project"]["params"]["seconds"] == 300


def test_a_newer_format_says_to_update_the_app(tmp_path):
    raw = zipped([("project.json", json.dumps(document(version=2)).encode())])
    with pytest.raises(StudioError) as info:
        open_file(make(tmp_path), raw)
    assert "newer version" in str(info.value)


def test_an_unknown_design_says_to_update_the_app(tmp_path):
    raw = zipped([("project.json", json.dumps(document("not-a-design")).encode())])
    with pytest.raises(StudioError) as info:
        open_file(make(tmp_path), raw)
    assert str(info.value) == ("This video uses a design this app doesn't have yet. "
                               "Update the app, then open it again.")


@pytest.mark.parametrize("entries", [
    [("project.json", b"{}"), ("assets/../evil.png", b"x")],
    [("project.json", b"{}"), ("/evil.png", b"x")],
    [("project.json", b"{}"), ("C:/evil.png", b"x")],
    [("project.json", b"{}"), ("assets\\evil.png", b"x")],
    [("project.json", b"{}"), ("assets/extra/file.png", b"x")],
    [("project.json", b"{}"), ("notes.txt", b"x")],
])
def test_paths_that_escape_or_do_not_belong_are_refused(tmp_path, entries):
    with pytest.raises(portable.PortableError):
        open_file(make(tmp_path), zipped(entries))


def test_a_symlink_entry_is_refused(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("project.json", b"{}")
        info = zipfile.ZipInfo("assets/link.png")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "photo.png")
    with pytest.raises(portable.PortableError):
        open_file(make(tmp_path), buffer.getvalue())


def test_duplicate_entry_names_are_refused(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("project.json", b"{}")
        archive.writestr("assets/photo.png", b"a")
        archive.writestr("assets/photo.png", b"b")
    with pytest.raises(portable.PortableError):
        open_file(make(tmp_path), buffer.getvalue())


def test_more_than_two_hundred_entries_are_refused(tmp_path):
    entries = [("project.json", b"{}")]
    entries += [(f"assets/{index}.png", b"x") for index in range(200)]
    with pytest.raises(portable.PortableError) as info:
        open_file(make(tmp_path), zipped(entries))
    assert "too many parts" in str(info.value)


def test_a_single_entry_over_its_limit_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(portable, "MAX_ENTRY_BYTES", 64)
    raw = zipped([("project.json", b'{"format":1,"template":"countdown"}'),
                  ("assets/big.png", b"x" * 100)])
    with pytest.raises(portable.PortableTooLarge):
        open_file(make(tmp_path), raw)


def test_total_uncompressed_size_is_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(portable, "MAX_TOTAL_BYTES", 100)
    raw = zipped([("project.json", b'{"format":1,"template":"countdown"}'),
                  ("assets/a.png", b"x" * 80)])
    with pytest.raises(portable.PortableTooLarge):
        open_file(make(tmp_path), raw)


def test_a_suspicious_compression_ratio_is_refused(tmp_path):
    raw = zipped([("project.json", b'{"format":1,"template":"countdown"}'),
                  ("assets/zeros.png", b"\x00" * (2 * 1024 * 1024))])
    with pytest.raises(portable.PortableError) as info:
        open_file(make(tmp_path), raw)
    assert "packed" in str(info.value)


def test_a_missing_project_json_or_a_bad_zip_is_refused(tmp_path):
    for raw in (zipped([("assets/a.png", b"x")]), b"not a zip", b""):
        with pytest.raises(portable.PortableError):
            open_file(make(tmp_path), raw)


def test_the_file_size_limit_is_checked_before_decoding(tmp_path, monkeypatch):
    monkeypatch.setattr(portable, "MAX_FILE_BYTES", 100)
    with pytest.raises(portable.PortableTooLarge):
        portable.decode_upload(base64.b64encode(b"x" * 200).decode())


def test_api_save_open_and_notes(tmp_path, monkeypatch):
    svc = make(tmp_path)
    project = svc.create_project_sync("celebration", {"photo": "gone.png", "name": "Ada"}, {}, "At school")
    monkeypatch.setattr(service_module, "service", svc)
    api = LocalClient(main.app, base_url="http://localhost")
    try:
        info = api.get(f"/api/studio/projects/{project['id']}/file/info")
        assert info.status_code == 200 and info.json()["filename"] == "at-school.manimstudio"
        assert "gone.png" in info.json()["notes"][0]

        saved = api.get(f"/api/studio/projects/{project['id']}/file")
        assert saved.status_code == 200
        assert saved.headers["content-type"] == "application/zip"
        assert ".manimstudio" in saved.headers["content-disposition"]
        assert "gone.png" in unquote(saved.headers["x-studio-note"])
        carried = saved.content
        assert zipfile.ZipFile(io.BytesIO(carried)).namelist() == ["project.json"]

        opened = api.post("/api/studio/projects/open", json={
            "data": base64.b64encode(carried).decode(), "filename": "at-school.manimstudio"})
        assert opened.status_code == 201, opened.text
        body = opened.json()
        assert body["project"]["id"] != project["id"] and "gone.png" in body["notes"][0]
        assert len(svc.list_projects_sync()) == 2

        bad = api.post("/api/studio/projects/open", json={"data": "bm90IGEgemlw"})
        assert bad.status_code == 422 and "Manim Studio file" in bad.json()["detail"]
        unknown = api.post("/api/studio/projects/open", json={"data": "x", "other": 1})
        assert unknown.status_code == 422
    finally:
        svc.shutdown_sync()


def test_the_open_route_gets_a_body_limit_for_its_size():
    limit, message = main.RequestBodyLimitMiddleware.limit_for("/api/studio/projects/open")
    assert limit >= 200 * 1024 * 1024
    assert "200 MB" in message
    assert main.RequestBodyLimitMiddleware.deadline_for("/api/studio/projects/open") == (
        main.BODY_DEADLINE_SECONDS * main.UPLOAD_DEADLINE_FACTOR)
    # Every other route keeps the small cap.
    assert main.RequestBodyLimitMiddleware.limit_for("/api/save")[0] == main.MAX_REQUEST_BODY_BYTES
