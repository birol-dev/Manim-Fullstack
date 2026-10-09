"""Optimistic-concurrency checks on /api/save (two tabs, rename/delete elsewhere)."""
from unittest.mock import patch

import main


def _open(client, name):
    res = client.get(f"/api/file-content?filename={name}")
    assert res.status_code == 200
    return res.json()


def test_file_content_and_save_return_a_version(client, tmp_path):
    with patch.object(main, "WORKSPACE_DIR", str(tmp_path)):
        (tmp_path / "demo.py").write_text("class Demo(Scene):\n    pass\n", encoding="utf-8")
        opened = _open(client, "demo.py")
        assert isinstance(opened["version"], str) and opened["version"]

        saved = client.post("/api/save", json={"filename": "demo.py", "code": "# v2\n", "base_version": opened["version"]})
        assert saved.status_code == 200
        assert saved.json()["version"] != opened["version"]
        # The version the save returns is what the next open reports.
        assert _open(client, "demo.py")["version"] == saved.json()["version"]


def test_save_with_stale_version_is_a_conflict_and_keeps_the_other_tabs_work(client, tmp_path):
    with patch.object(main, "WORKSPACE_DIR", str(tmp_path)):
        (tmp_path / "demo.py").write_text("original\n", encoding="utf-8")
        tab_a = _open(client, "demo.py")["version"]
        tab_b = _open(client, "demo.py")["version"]

        first = client.post("/api/save", json={"filename": "demo.py", "code": "from tab A\n", "base_version": tab_a})
        assert first.status_code == 200

        second = client.post("/api/save", json={"filename": "demo.py", "code": "from tab B\n", "base_version": tab_b})
        assert second.status_code == 412
        assert "changed outside this tab" in second.json()["detail"]
        assert (tmp_path / "demo.py").read_text(encoding="utf-8") == "from tab A\n"

        # Tab B can continue from the new version (after reloading or choosing to overwrite).
        retry = client.post(
            "/api/save", json={"filename": "demo.py", "code": "from tab B\n", "base_version": first.json()["version"]}
        )
        assert retry.status_code == 200
        assert (tmp_path / "demo.py").read_text(encoding="utf-8") == "from tab B\n"


def test_versioned_save_does_not_recreate_a_deleted_or_renamed_file(client, tmp_path):
    with patch.object(main, "WORKSPACE_DIR", str(tmp_path)):
        (tmp_path / "gone.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "moved.py").write_text("y = 2\n", encoding="utf-8")
        gone = _open(client, "gone.py")["version"]
        moved = _open(client, "moved.py")["version"]

        assert client.delete("/api/scripts?filename=gone.py").status_code == 200
        assert client.post("/api/rename", json={"old_name": "moved.py", "new_name": "renamed.py"}).status_code == 200

        res = client.post("/api/save", json={"filename": "gone.py", "code": "x = 3\n", "base_version": gone})
        assert res.status_code == 404
        assert "renamed or deleted" in res.json()["detail"]
        assert not (tmp_path / "gone.py").exists()

        res = client.post("/api/save", json={"filename": "moved.py", "code": "y = 3\n", "base_version": moved})
        assert res.status_code == 404
        assert not (tmp_path / "moved.py").exists()
        assert (tmp_path / "renamed.py").read_text(encoding="utf-8") == "y = 2\n"


def test_case_only_clash_stays_a_409_distinct_from_a_version_conflict(client, tmp_path):
    with patch.object(main, "WORKSPACE_DIR", str(tmp_path)):
        (tmp_path / "Demo.py").write_text("a\n", encoding="utf-8")
        res = client.post("/api/save", json={"filename": "demo.py", "code": "b\n"})
        assert res.status_code == 409
        assert "differ only by case" in res.json()["detail"]


def test_unversioned_save_still_creates_and_overwrites(client, tmp_path):
    """New files (and an explicit 'Overwrite') don't send a base version."""
    with patch.object(main, "WORKSPACE_DIR", str(tmp_path)):
        res = client.post("/api/save", json={"filename": "fresh.py", "code": "a = 1\n"})
        assert res.status_code == 200 and res.json()["version"]
        res = client.post("/api/save", json={"filename": "fresh.py", "code": "a = 2\n"})
        assert res.status_code == 200
        assert (tmp_path / "fresh.py").read_text(encoding="utf-8") == "a = 2\n"


def test_version_tracks_bytes_on_disk_not_the_request(client, tmp_path):
    """An edit made by another program (not through the API) is detected too."""
    with patch.object(main, "WORKSPACE_DIR", str(tmp_path)):
        (tmp_path / "ext.py").write_text("one\n", encoding="utf-8")
        version = _open(client, "ext.py")["version"]
        (tmp_path / "ext.py").write_text("edited in another editor\n", encoding="utf-8")
        res = client.post("/api/save", json={"filename": "ext.py", "code": "mine\n", "base_version": version})
        assert res.status_code == 412
        assert (tmp_path / "ext.py").read_text(encoding="utf-8") == "edited in another editor\n"


def test_create_only_never_overwrites(client, tmp_path):
    with patch.object(main, "WORKSPACE_DIR", str(tmp_path)):
        (tmp_path / "taken.py").write_text("theirs\n", encoding="utf-8")
        res = client.post("/api/save", json={"filename": "taken.py", "code": "mine\n", "create_only": True})
        assert res.status_code == 409
        assert res.json()["detail"] == "taken.py already exists."
        assert (tmp_path / "taken.py").read_text(encoding="utf-8") == "theirs\n"
        res = client.post("/api/save", json={"filename": "new_one.py", "code": "x = 1\n", "create_only": True})
        assert res.status_code == 200
