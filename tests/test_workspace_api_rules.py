"""File-name rules and size limits."""
from unittest.mock import patch

import pytest

import main
from workspace_paths import UnsafePathError, find_case_insensitive_match, safe_basename, validate_new_filename

PY = ".py"


@pytest.fixture
def dirs(tmp_path):
    media = tmp_path / "media"
    assets = tmp_path / "assets"
    media.mkdir()
    assets.mkdir()
    with patch.object(main, "WORKSPACE_DIR", str(tmp_path)), patch.object(
        main, "MEDIA_DIR", str(media)
    ), patch.object(main, "ASSETS_DIR", str(assets)):
        yield tmp_path, media, assets


# ----------------------------------------------------------------- validator --

BAD_NEW_SCRIPT_NAMES = [
    ("a" * 266 + ".py", "too long"),
    ("é" * 130 + ".py", "too long"),
    ("a" * 101 + ".py", "100 characters"),
    ("..py", "name before the extension"),
    ("...py", "name before the extension"),
    ("..", ""),
    ("bad<name.py", "cannot contain"),
    ("bad>name.py", "cannot contain"),
    ('bad"name.py', "cannot contain"),
    ("bad|name.py", "cannot contain"),
    ("bad?name.py", "cannot contain"),
    ("bad*name.py", "cannot contain"),
    ("bad:name.py", "cannot contain"),
    ("tab\tname.py", ""),
    ("bell\x07.py", ""),
    ("rtl\u202ename.py", ""),
    ("-rf.py", "dash"),
    (".hidden.py", ""),
    ("CON.py", "reserved"),
    ("nul.py", "reserved"),
    ("com1.py", "reserved"),
    ("lpt9.tar.py", "reserved"),
    ("trailing.py ", ""),
    ("_temp_run_abc.py", "_temp_run_"),
    ("_TEMP_RUN_abc.py", "_temp_run_"),
    ("sub/dir.py", "folders"),
    ("sub\\dir.py", "folders"),
]


@pytest.mark.parametrize("name, reason", BAD_NEW_SCRIPT_NAMES)
def test_new_script_names_are_validated(name, reason):
    with pytest.raises(UnsafePathError) as info:
        validate_new_filename(name, required_suffix=PY, forbid_temp_prefix=True)
    assert reason.lower() in str(info.value).lower()


@pytest.mark.parametrize("name", ["scene.py", "Intro_2.py", "my-scene.py", "ünïcode.py", "a" * 100 + ".py"])
def test_reasonable_names_pass(name):
    assert validate_new_filename(name, required_suffix=PY, forbid_temp_prefix=True) == name


def test_existing_legacy_names_stay_reachable():
    # Old files that break the creation rules can still be opened, renamed, or deleted.
    assert safe_basename("-old.py", required_suffix=PY) == "-old.py"
    assert safe_basename("_temp_run_legacy.py", required_suffix=PY) == "_temp_run_legacy.py"


def test_find_case_insensitive_match(tmp_path):
    (tmp_path / "Intro.py").write_text("x")
    assert find_case_insensitive_match(str(tmp_path), "intro.py") == "Intro.py"
    assert find_case_insensitive_match(str(tmp_path), "Intro.py") is None
    assert find_case_insensitive_match(str(tmp_path), "other.py") is None
    assert find_case_insensitive_match(str(tmp_path / "missing"), "x.py") is None


# ----------------------------------------------------------------- endpoints --

def _no_host_path(detail, root):
    assert str(root) not in detail
    assert "/workspace" not in detail and "Errno" not in detail


def test_overlong_save_name_is_a_clean_400(client, dirs):
    root, _, _ = dirs
    res = client.post("/api/save", json={"filename": "a" * 270 + ".py", "code": "x = 1\n"})
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert detail.startswith("Invalid script filename:")
    _no_host_path(detail, root)


# /api/save trims surrounding spaces itself, so "trailing.py " is saved as "trailing.py".
@pytest.mark.parametrize("name", [n for n, _ in BAD_NEW_SCRIPT_NAMES if n == n.strip()])
def test_save_refuses_bad_names(client, dirs, name):
    root, _, _ = dirs
    res = client.post("/api/save", json={"filename": name, "code": "x = 1\n"})
    assert res.status_code == 400, name
    _no_host_path(res.json()["detail"], root)
    assert [p.name for p in root.glob("*.py")] == []


def test_save_and_rename_refuse_case_collisions(client, dirs):
    root, _, _ = dirs
    assert client.post("/api/save", json={"filename": "Intro.py", "code": "x = 1\n"}).status_code == 200
    assert client.post("/api/save", json={"filename": "other.py", "code": "x = 2\n"}).status_code == 200

    clash = client.post("/api/save", json={"filename": "intro.py", "code": "x = 3\n"})
    assert clash.status_code == 409
    assert "differ only by case" in clash.json()["detail"]

    renamed = client.post("/api/rename", json={"old_name": "other.py", "new_name": "INTRO.py"})
    assert renamed.status_code == 409
    assert (root / "other.py").exists()

    # Changing only the case of the file itself is still allowed.
    ok = client.post("/api/rename", json={"old_name": "Intro.py", "new_name": "intro.py"})
    assert ok.status_code == 200
    assert sorted(p.name for p in root.glob("*.py")) == ["intro.py", "other.py"]


def test_rename_target_rules(client, dirs):
    root, _, _ = dirs
    (root / "a.py").write_text("x = 1\n")
    for bad in ["..py", "_Temp_Run_x.py", "CON.py", "-x.py", "x" * 300 + ".py"]:
        res = client.post("/api/rename", json={"old_name": "a.py", "new_name": bad})
        assert res.status_code == 400, bad
        _no_host_path(res.json()["detail"], root)
    assert (root / "a.py").exists()


def test_delete_refuses_bad_names_cleanly(client, dirs):
    root, _, _ = dirs
    res = client.delete("/api/scripts", params={"filename": "a" * 300 + ".py"})
    assert res.status_code == 400
    _no_host_path(res.json()["detail"], root)
    res = client.delete("/api/assets", params={"filename": "../x.png"})
    assert res.status_code == 400


def test_render_refuses_temp_and_bad_names(client):
    with client.websocket_connect("/api/render") as ws:
        for name in ["_TEMP_RUN_x.py", "..py", "a" * 300 + ".py"]:
            ws.send_json({"type": "start", "filename": name, "scene": "Intro", "quality": "l"})
            error, result = ws.receive_json(), ws.receive_json()
            assert error["message"].startswith("Invalid script filename:"), name
            assert result["status"] == "rejected"


def _upload(client, name, data=b"\x89PNG\r\n", overwrite=None):
    params = {"overwrite": "true"} if overwrite else None
    return client.post("/api/upload-asset", params=params, files={"file": (name, data, "image/png")})


def test_upload_conflict_message_and_replaced_flag(client, dirs):
    _, _, assets = dirs
    first = _upload(client, "logo.png")
    assert first.status_code == 200
    assert first.json()["replaced"] is False

    again = _upload(client, "logo.png")
    assert again.status_code == 409
    assert "overwrite=true" in again.json()["detail"]
    assert "Confirm" in again.json()["detail"]

    replaced = _upload(client, "logo.png", b"\x89PNG new", overwrite=True)
    assert replaced.status_code == 200
    assert replaced.json()["replaced"] is True
    assert (assets / "logo.png").read_bytes() == b"\x89PNG new"

    fresh = _upload(client, "fresh.png", overwrite=True)
    assert fresh.status_code == 200
    assert fresh.json()["replaced"] is False


def test_upload_name_rules(client, dirs):
    root, _, assets = dirs
    assert _upload(client, "Logo.png").status_code == 200
    clash = _upload(client, "logo.png")
    assert clash.status_code == 409
    for bad in ["..png", "a" * 300 + ".png", "x<y.png", "-x.png", "AUX.png"]:
        res = _upload(client, bad)
        assert res.status_code == 400, bad
        assert res.json()["detail"].startswith("Invalid asset filename:")
        _no_host_path(res.json()["detail"], root)
    assert [p.name for p in assets.iterdir()] == ["Logo.png"]


def test_delete_media_refuses_parent_segments(client, dirs):
    _, media, _ = dirs
    keep = media / "images" / "keep.png"
    keep.parent.mkdir(parents=True)
    keep.write_bytes(b"png")
    res = client.delete("/api/media", params={"path": "videos/../images/keep.png"})
    assert res.status_code == 400
    assert keep.exists()


# --------------------------------------------------------------- size limits --

def test_code_limit_counts_utf8_bytes_not_json(client, dirs):
    root, _, _ = dirs
    limit = 1024
    # Control characters are escaped as \u00XX in JSON: 6x the bytes on the wire.
    code_text = "\x01" * limit
    with patch.object(main, "MAX_CODE_BYTES", limit), patch.object(
        main, "MAX_REQUEST_BODY_BYTES", 6 * limit + 64 * 1024
    ):
        ok = client.post("/api/save", json={"filename": "ctrl.py", "code": code_text})
        assert ok.status_code == 200
        multi = client.post("/api/parse-code", json={"code": "é" * (limit // 2)})
        assert multi.status_code == 200
        over = client.post("/api/parse-code", json={"code": "é" * (limit // 2 + 1)})
        assert over.status_code == 413
        assert f"({limit} bytes)" in over.json()["detail"]
    assert (root / "ctrl.py").read_text() == code_text


def test_raw_body_cap_is_separate(client):
    with patch.object(main, "MAX_REQUEST_BODY_BYTES", 128):
        res = client.post("/api/parse-code", json={"code": "x" * 200})
    assert res.status_code == 413
    assert res.json()["detail"] == "Request body exceeds maximum size (128 bytes)."


def test_default_body_cap_leaves_room_for_escaping():
    assert main.MAX_REQUEST_BODY_BYTES >= 6 * main.MAX_CODE_BYTES


def test_websocket_code_limit_uses_utf8_bytes(client, dirs):
    limit = 256
    with patch.object(main, "MAX_CODE_BYTES", limit), client.websocket_connect("/api/render") as ws:
        ws.send_json({"type": "start", "filename": "a.py", "scene": "Intro", "quality": "l",
                      "code": "é" * (limit // 2 + 1)})
        error, result = ws.receive_json(), ws.receive_json()
    assert "maximum size" in error["message"]
    assert result["status"] == "rejected"


def test_diagnostics_reports_max_code_bytes(client):
    with patch.object(main, "MAX_CODE_BYTES", 12345):
        data = client.get("/api/diagnostics").json()
    assert data["max_code_bytes"] == 12345
