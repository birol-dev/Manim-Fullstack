"""The workspace preferences store (merge, validation, caps, atomic writes) and its routes."""

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from starlette.testclient import TestClient

import main
from studio import preferences as preferences_module
from studio import service as service_module
from studio.preferences import MAX_BYTES, MAX_RECENT_COLORS, MAX_SEEN_EXPORTS, PreferenceStore
from studio.registry import TemplateError
from tests.conftest import LocalClient
from tests.studio_fakes import make_service


@pytest.fixture
def store(tmp_path):
    return PreferenceStore(str(tmp_path))


@pytest.fixture
def studio(tmp_path, monkeypatch):
    svc, _ = make_service(tmp_path)
    monkeypatch.setattr(service_module, "service", svc)
    yield svc
    svc.shutdown_sync()


@pytest.fixture
def api(studio):
    return LocalClient(main.app, base_url="http://localhost")


# --------------------------------------------------------------------------- #
# The store
# --------------------------------------------------------------------------- #


def test_missing_file_reads_as_empty_and_creates_nothing(store):
    assert store.read() == {}
    assert not os.path.exists(store.path)


def test_update_merges_partial_objects_and_persists(store):
    assert store.update({"appearance": "dark"}) == {"appearance": "dark"}
    assert store.update({"sidebar_collapsed": True}) == {"appearance": "dark", "sidebar_collapsed": True}
    assert store.read() == {"appearance": "dark", "sidebar_collapsed": True}
    with open(store.path, encoding="utf-8") as f:
        assert json.load(f) == {"appearance": "dark", "sidebar_collapsed": True}
    # An explicit "no choice" is stored as null, not dropped.
    assert store.update({"template_categories_open": None})["template_categories_open"] is None
    assert store.read()["template_categories_open"] is None
    # An empty patch only reports what is stored.
    assert store.update({}) == store.read()


def test_values_are_validated_with_field_errors(store):
    with pytest.raises(TemplateError) as info:
        store.update({"appearance": "neon", "sidebar_collapsed": "yes", "template_categories_open": 1})
    assert {e["field"] for e in info.value.errors} == {"appearance", "sidebar_collapsed", "template_categories_open"}
    with pytest.raises(TemplateError) as info:
        store.update({"colour": "red"})
    assert info.value.errors == [{"field": "colour", "message": "Unknown preference."}]
    with pytest.raises(TemplateError) as info:
        store.update(["not", "an", "object"])
    assert info.value.errors[0]["field"] == "body"
    assert store.read() == {}  # nothing invalid was written
    assert not os.path.exists(store.path)


def test_recent_colors_are_normalized_and_capped(store):
    colors = [f"#{n:02x}3366" for n in range(MAX_RECENT_COLORS)]
    assert store.update({"recent_colors": colors})["recent_colors"] == [color.upper() for color in colors]
    assert store.update({"recent_colors": ["abc123"]})["recent_colors"] == ["#ABC123"]
    with pytest.raises(TemplateError) as info:
        store.update({"recent_colors": colors + ["#123456"]})
    assert info.value.errors[0]["field"] == "recent_colors"
    for bad in (["#12345"], ["red"], [1], "not-a-list", None):
        with pytest.raises(TemplateError):
            store.update({"recent_colors": bad})
    assert store.read()["recent_colors"] == ["#ABC123"]


def test_seen_exports_are_capped(store):
    ids = [f"export-{n}" for n in range(MAX_SEEN_EXPORTS)]
    assert store.update({"seen_exports": ids})["seen_exports"] == ids
    with pytest.raises(TemplateError) as info:
        store.update({"seen_exports": ids + ["one-more"]})
    assert info.value.errors[0]["field"] == "seen_exports"
    for bad in (["../outside"], [""], [3], {}, None):
        with pytest.raises(TemplateError):
            store.update({"seen_exports": bad})


def test_setup_preferences_validate_and_persist(store):
    values = store.update({"onboarding_done": True, "brand_name": "Ana's Studio", "brand_color": "2563eb",
                           "default_format": "mp4", "default_theme": "midnight"})
    assert values == {"onboarding_done": True, "brand_name": "Ana's Studio", "brand_color": "#2563EB",
                      "default_format": "mp4", "default_theme": "midnight"}
    assert store.update({"brand_color": None, "default_format": None, "default_theme": None}) == {
        "onboarding_done": True, "brand_name": "Ana's Studio", "brand_color": None,
        "default_format": None, "default_theme": None}

    with pytest.raises(TemplateError) as info:
        store.update({"onboarding_done": "yes", "brand_name": "x" * 81, "brand_color": "blue",
                      "default_format": 3, "default_theme": ["dark"]})
    assert {e["field"] for e in info.value.errors} == {
        "onboarding_done", "brand_name", "brand_color", "default_format", "default_theme"}
    assert store.read()["brand_name"] == "Ana's Studio"


def test_a_corrupt_or_oversized_file_reads_as_empty(store):
    os.makedirs(os.path.dirname(store.path), exist_ok=True)
    with open(store.path, "w", encoding="utf-8") as f:
        f.write("{broken")
    assert store.read() == {}
    with open(store.path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"appearance": "dark", "sidebar_collapsed": "yes", "unknown": 1,
                            "recent_colors": ["#abc"]}))
    # Valid values survive; unknown and invalid ones are ignored.
    assert store.read() == {"appearance": "dark"}
    with open(store.path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"seen_exports": ["x" * 1000] * (MAX_BYTES // 1000 + 1)}))
    assert os.path.getsize(store.path) > MAX_BYTES
    assert store.read() == {}
    with open(store.path, "w", encoding="utf-8") as f:
        f.write(json.dumps(["not", "an", "object"]))
    assert store.read() == {}


def test_writes_are_atomic_and_concurrent_updates_merge(store):
    store.update({"appearance": "dark"})
    folder = os.path.dirname(store.path)
    assert [name for name in os.listdir(folder) if name.startswith(".~")] == []
    with open(store.path, encoding="utf-8") as f:
        assert json.load(f) == {"appearance": "dark"}
    barrier = threading.Barrier(2)

    def write(key, value):
        barrier.wait(5)
        store.update({key: value})

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda pair: write(*pair), [("sidebar_collapsed", True),
                                                  ("template_categories_open", False)]))
    assert store.read() == {"appearance": "dark", "sidebar_collapsed": True, "template_categories_open": False}
    assert [name for name in os.listdir(folder) if name.startswith(".~")] == []


def test_service_methods_use_the_workspace_store(studio):
    import asyncio

    assert asyncio.run(studio.get_preferences()) == {}
    merged = asyncio.run(studio.update_preferences({"appearance": "light"}))
    assert merged == {"appearance": "light"}
    assert asyncio.run(studio.get_preferences()) == {"appearance": "light"}
    path = os.path.join(studio.workspace_dir, "studio", "preferences.json")
    assert os.path.isfile(path)


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #


def test_preferences_routes_read_and_merge(api, studio):
    assert api.get("/api/studio/preferences").json() == {}
    res = api.patch("/api/studio/preferences", json={"appearance": "dark", "sidebar_collapsed": True})
    assert res.status_code == 200
    assert res.json() == {"appearance": "dark", "sidebar_collapsed": True}
    assert api.get("/api/studio/preferences").json() == res.json()
    assert api.patch("/api/studio/preferences", json={"recent_colors": ["#123456", "abcdef"]}).json() == {
        "appearance": "dark", "sidebar_collapsed": True, "recent_colors": ["#123456", "#ABCDEF"]}
    assert api.patch("/api/studio/preferences", json={"template_categories_open": None}).json()[
        "template_categories_open"] is None
    assert api.patch("/api/studio/preferences", json={}).status_code == 200
    path = os.path.join(studio.workspace_dir, "studio", "preferences.json")
    with open(path, encoding="utf-8") as f:
        assert json.load(f)["appearance"] == "dark"


def test_preferences_routes_answer_422_with_field_errors(api):
    res = api.patch("/api/studio/preferences", json={"appearance": "neon", "recent_colors": ["nope"]})
    assert res.status_code == 422
    body = res.json()
    assert body["detail"] == "Invalid preferences."
    assert {e["field"] for e in body["errors"]} == {"appearance", "recent_colors.0"}
    unknown = api.patch("/api/studio/preferences", json={"colour": "red"})
    assert unknown.status_code == 422 and unknown.json()["errors"][0]["field"] == "colour"
    not_json = api.patch("/api/studio/preferences", content=b"[1, 2]", headers={"content-type": "application/json"})
    assert not_json.status_code == 422 and not_json.json()["errors"][0]["field"] == "body"
    garbage = api.patch("/api/studio/preferences", content=b"{oops", headers={"content-type": "application/json"})
    assert garbage.status_code == 422
    assert api.get("/api/studio/preferences").json() == {}


def test_preferences_routes_use_the_desktop_session(monkeypatch, tmp_path):
    svc, _ = make_service(tmp_path)
    monkeypatch.setattr(service_module, "service", svc)
    monkeypatch.setenv("MANIM_API_TOKEN", "desktop-secret")
    client = TestClient(main.app, base_url="http://localhost")
    try:
        assert client.get("/api/studio/preferences").status_code == 401
        assert client.patch("/api/studio/preferences", json={"appearance": "dark"}).status_code == 401
        paired = client.get("/api/desktop/session?token=desktop-secret", follow_redirects=False)
        assert paired.status_code == 303
        assert client.get("/api/studio/preferences").status_code == 200
        assert client.patch("/api/studio/preferences", json={"appearance": "dark"}).status_code == 200
    finally:
        svc.shutdown_sync()
