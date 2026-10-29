"""/api/studio routes over a service with a fake worker and runner (no Manim)."""

import pytest

import main
from studio import service as service_module
from tests.conftest import LocalClient
from tests.studio_fakes import FakeRunner, RunnerFactory, make_service, wait_until
from tests.studio_fakes import FakeMotionWorker

LAUNCH = {"seconds": 10, "title": "", "style": "big", "finish_text": "Happy New Year!", "confetti": True}


@pytest.fixture
def studio(tmp_path, monkeypatch):
    svc, worker = make_service(tmp_path, runners=RunnerFactory(FakeRunner("ok")))
    svc.fake = worker
    monkeypatch.setattr(service_module, "service", svc)
    yield svc
    svc.shutdown_sync()


@pytest.fixture
def api(studio):
    return LocalClient(main.app, base_url="http://localhost")


@pytest.fixture
def media_in_tmp(studio, monkeypatch):
    """Serve /media from the test service's media folder."""
    from starlette.staticfiles import StaticFiles

    mount = next(r for r in main.app.routes if getattr(r, "name", None) == "media")
    monkeypatch.setattr(mount, "app", StaticFiles(directory=studio.media_dir, check_dir=False))


def test_catalog(api):
    res = api.get("/api/studio/catalog")
    assert res.status_code == 200
    body = res.json()
    assert {"sections", "templates", "themes", "aspects", "qualities", "formats"} <= set(body)
    assert any(t["id"] == "countdown" for t in body["templates"])


def test_motion_routes_and_media(api, studio, media_in_tmp):
    worker = FakeMotionWorker()
    studio._motion_worker_factory = lambda: worker
    first = api.post("/api/studio/motion", json={"project": "editor", "template": "countdown"})
    assert first.status_code == 202
    rid = first.json()["id"]
    result = wait_until(lambda: (record if (record := api.get(f"/api/studio/motion/{rid}").json())["status"] == "done" else None))
    assert not any(key.startswith("_") for key in result)
    video = api.get(result["url"])
    assert video.status_code == 200 and video.headers["content-type"] == "video/mp4"
    assert api.delete(f"/api/studio/motion/{rid}").json()["status"] == "done"
    assert api.get("/api/studio/motion/missing").status_code == 404
    assert api.post("/api/studio/motion", json={"template": "countdown"}).status_code == 422
    assert api.post("/api/studio/motion", json={"project": "editor", "template": "countdown", "other": 1}).status_code == 422


def test_template_route(api):
    assert api.get("/api/studio/templates/countdown").json()["id"] == "countdown"
    missing = api.get("/api/studio/templates/nope")
    assert missing.status_code == 404 and "nope" in missing.json()["detail"]


def test_preview_and_cache(api, studio, media_in_tmp):
    body = {"template": "countdown", "params": LAUNCH, "settings": {"aspect": "1:1"}, "mode": "poster"}
    first = api.post("/api/studio/preview", json=body)
    assert first.status_code == 200, first.text
    data = first.json()
    assert set(data) == {"url", "mode", "width", "height", "cached", "ms"}  # no host path
    assert data["cached"] is False and (data["width"], data["height"]) == (360, 360)
    image = api.get(data["url"])  # served by the existing /media mount
    assert image.status_code == 200 and image.content.startswith(b"\x89PNG")
    assert api.post("/api/studio/preview", json=body).json()["cached"] is True
    board = api.post("/api/studio/preview", json={**body, "mode": "storyboard"}).json()
    assert board["storyboard"]["plays"] == 4 and board["mode"] == "storyboard"
    assert len(studio.fake.calls) == 2


def test_validation_errors(api, studio):
    res = api.post("/api/studio/preview", json={"template": "countdown", "params": {"seconds": 1},
                                                "settings": {"aspect": "2:1"}})
    assert res.status_code == 422
    body = res.json()
    assert body["detail"] == "Invalid input for countdown."
    assert {e["field"] for e in body["errors"]} == {"params.seconds", "settings.aspect"}
    unknown = api.post("/api/studio/preview", json={"template": "countdown", "colour": "red"})
    assert unknown.status_code == 422 and unknown.json()["errors"] == [{"field": "colour", "message": "Unknown field."}]
    not_json = api.post("/api/studio/preview", content=b"[1, 2]", headers={"content-type": "application/json"})
    assert not_json.status_code == 422 and not_json.json()["errors"][0]["field"] == "body"
    garbage = api.post("/api/studio/preview", content=b"{oops", headers={"content-type": "application/json"})
    assert garbage.status_code == 422
    assert api.post("/api/studio/preview", json={"template": "nope"}).json()["errors"][0]["field"] == "template"
    assert studio.fake.calls == []


def test_render_errors_map_to_status_codes(api, studio):
    from studio.worker import WorkerStartError, WorkerTimeout

    studio.fake.fail = WorkerTimeout("The preview took longer than 45 s and was stopped.")
    res = api.post("/api/studio/preview", json={"template": "countdown"})
    assert res.status_code == 504 and "45 s" in res.json()["detail"]
    studio.fake.fail = WorkerStartError("No module named 'manim'")
    assert api.post("/api/studio/preview", json={"template": "countdown"}).status_code == 503


def test_export_lifecycle(api, studio):
    res = api.post("/api/studio/exports", json={"template": "countdown", "params": LAUNCH, "format": "mp4",
                                                "quality": "720p", "title": "New Year"})
    assert res.status_code == 202, res.text
    export = res.json()
    assert export["status"] == "queued" and export["format"] == "mp4" and export["quality"] == "720p"
    done = wait_until(lambda: (lambda e: e if e["status"] == "done" else None)(
        api.get(f"/api/studio/exports/{export['id']}").json()))
    assert done["url"] == f"/media/studio/exports/new-year-{export['id']}.mp4"
    listed = api.get("/api/studio/exports").json()
    assert [e["id"] for e in listed] == [export["id"]]
    assert api.get("/api/studio/exports/000000000000").status_code == 404
    # DELETE on a finished export is a no-op cancel; ?remove=true forgets it and deletes the file.
    assert api.delete(f"/api/studio/exports/{export['id']}").json()["status"] == "done"
    assert api.delete(f"/api/studio/exports/{export['id']}?remove=true").status_code == 200
    assert api.get("/api/studio/exports").json() == []
    bad = api.post("/api/studio/exports", json={"template": "countdown", "format": "avi"})
    assert bad.status_code == 422 and bad.json()["errors"][0]["field"] == "format"


def test_cancel_running_export(tmp_path, monkeypatch):
    blocker = FakeRunner("block")
    svc, _ = make_service(tmp_path, runners=RunnerFactory(blocker))
    monkeypatch.setattr(service_module, "service", svc)
    api = LocalClient(main.app, base_url="http://localhost")
    try:
        export = api.post("/api/studio/exports", json={"template": "countdown", "quality": "draft"}).json()
        assert blocker.started.wait(5)
        assert api.get(f"/api/studio/exports/{export['id']}").json()["status"] == "rendering"
        res = api.delete(f"/api/studio/exports/{export['id']}")
        assert res.status_code == 200 and res.json()["status"] == "cancelled"
        assert api.delete(f"/api/studio/exports/{export['id']}?remove=true").status_code == 200
    finally:
        svc.shutdown_sync()


def test_projects_crud(api):
    assert api.get("/api/studio/projects").json() == []
    res = api.post("/api/studio/projects", json={"template": "countdown", "params": {"seconds": 1},
                                                 "settings": {}, "title": "Mine"})
    assert res.status_code == 201
    project = res.json()
    assert project["title"] == "Mine" and project["params"] == {"seconds": 1}
    pid = project["id"]
    assert api.get(f"/api/studio/projects/{pid}").json()["id"] == pid
    put = api.put(f"/api/studio/projects/{pid}", json={"params": {"seconds": 20}})
    assert put.status_code == 200 and put.json()["params"] == {"seconds": 20} and put.json()["title"] == "Mine"
    assert api.put(f"/api/studio/projects/{pid}", json={"template": "other"}).status_code == 422
    listed = api.get("/api/studio/projects").json()
    assert [p["id"] for p in listed] == [pid] and "poster_url" in listed[0]
    assert api.delete(f"/api/studio/projects/{pid}").json()["id"] == pid
    assert api.get(f"/api/studio/projects/{pid}").status_code == 404
    assert api.get("/api/studio/projects/..%2F..%2Fsecret").status_code == 404
    assert api.post("/api/studio/projects", json={"template": "nope"}).status_code == 422


def test_images_from_agents(api, studio):
    import base64

    from tests.studio_fakes import tiny_png

    res = api.post("/api/studio/images", json={"data": base64.b64encode(tiny_png(3, 2)).decode()})
    assert res.status_code == 201 and res.json()["name"].startswith("agent-") and res.json()["width"] == 3
    bad = api.post("/api/studio/images", json={"data": "bm90IGFuIGltYWdl"})
    assert bad.status_code == 422 and bad.json()["errors"][0]["field"] == "data"
    assert api.post("/api/studio/images", json={"data": "x", "name": "../x.png"}).status_code == 422


def test_icons(api, studio):
    import os

    with open(os.path.join(studio.icons_dir, "gift.svg"), "w") as f:
        f.write('<svg xmlns="http://www.w3.org/2000/svg"/>')
    assert api.get("/api/studio/icons").json() == ["gift"]
    res = api.get("/api/studio/icons/gift.svg")
    assert res.status_code == 200 and res.headers["content-type"].startswith("image/svg+xml")
    assert "sandbox" in res.headers["content-security-policy"] and res.headers["x-content-type-options"] == "nosniff"
    assert api.get("/api/studio/icons/missing.svg").status_code == 404
    assert api.get("/api/studio/icons/Gift.svg").status_code == 422
    assert api.get("/api/studio/icons/..%2Fgift.svg").status_code in (404, 422)
    assert api.get("/api/studio/icons/gift.png").status_code == 404


def test_security_middleware_covers_studio_routes(api, studio):
    evil = {"origin": "http://evil.example"}
    assert api.get("/api/studio/catalog", headers=evil).status_code == 403
    res = api.post("/api/studio/preview", json={"template": "countdown"}, headers=evil)
    assert res.status_code == 403
    assert api.post("/api/studio/exports", json={"template": "countdown"}, headers=evil).status_code == 403
    assert api.get("/api/studio/projects", headers={"host": "evil.example"}).status_code == 403
    assert studio.fake.calls == [] and api.get("/api/studio/exports").json() == []
    # The app's own origin is fine.
    assert api.get("/api/studio/catalog", headers={"origin": "http://localhost:5173"}).status_code == 200


def test_body_size_limit_applies(api, monkeypatch):
    monkeypatch.setattr(main, "MAX_REQUEST_BODY_BYTES", 1024)
    res = api.post("/api/studio/projects", json={"template": "countdown", "params": {"t": "x" * 4000}})
    assert res.status_code == 413
