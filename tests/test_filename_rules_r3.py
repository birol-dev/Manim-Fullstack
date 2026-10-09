"""Round 3 filename rule: shared vectors (also used by frontend/src/lib/format.rules.test.ts),
NFC storage, Unicode device names, Foo.PY, trailing dots/spaces, and files that already
exist under a name the rule now forbids."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

import main
from workspace_paths import (
    UnsafePathError,
    find_case_insensitive_match,
    fold_filename,
    to_script_name,
    validate_new_filename,
)

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "filename_rules.json").read_text("utf-8"))
NFD_CAFE = "cafe\u0301.py"
NFC_CAFE = "caf\u00e9.py"


def _validate(name):
    try:
        validate_new_filename(name, required_suffix=".py", forbid_temp_prefix=True)
        return None
    except UnsafePathError as exc:
        return str(exc)


@pytest.mark.parametrize("vec", FIXTURE["vectors"], ids=lambda v: repr(v["input"])[:40])
def test_shared_vectors(vec):
    assert to_script_name(vec["input"]) == vec["script_name"]
    assert _validate(vec["script_name"]) == vec["error"]


@pytest.mark.parametrize("vec", FIXTURE["direct_names"], ids=lambda v: repr(v["name"]))
def test_shared_direct_names(vec):
    assert _validate(vec["name"]) == vec["error"]


@pytest.mark.parametrize("vec", FIXTURE["collisions"], ids=lambda v: f'{v["a"]}|{v["b"]}')
def test_shared_collisions(vec):
    assert (fold_filename(vec["a"]) == fold_filename(vec["b"])) is vec["collide"]


def test_fixture_covers_the_round3_cases():
    inputs = {v["input"] for v in FIXTURE["vectors"]}
    for needed in ["Foo.PY", "x.py.", "x .py", "COM¹.py", "ＣＯＭ１.py", NFD_CAFE]:
        assert needed in inputs


def test_to_script_name_is_idempotent():
    for vec in FIXTURE["vectors"]:
        once = to_script_name(vec["input"])
        assert to_script_name(once) == once


def test_nfd_lookalike_is_a_collision(tmp_path):
    (tmp_path / NFD_CAFE).write_text("x")
    assert find_case_insensitive_match(str(tmp_path), NFC_CAFE) == NFD_CAFE


# ----------------------------------------------------------------- endpoints --

@pytest.fixture
def root(tmp_path):
    media = tmp_path / "media"
    assets = tmp_path / "assets"
    media.mkdir()
    assets.mkdir()
    with patch.object(main, "WORKSPACE_DIR", str(tmp_path)), patch.object(
        main, "MEDIA_DIR", str(media)
    ), patch.object(main, "ASSETS_DIR", str(assets)):
        yield tmp_path


def _names(root):
    return sorted(p.name for p in root.glob("*.py"))


def test_save_uppercase_extension_becomes_lowercase(client, root):
    res = client.post("/api/save", json={"filename": "Foo.PY", "code": "x = 1\n"})
    assert res.status_code == 200, res.text
    assert _names(root) == ["Foo.py"]


@pytest.mark.parametrize("name", ["x.py.", "x.py ", "x .py", "x..py", "x."])
def test_save_refuses_trailing_dots_and_spaces(client, root, name):
    res = client.post("/api/save", json={"filename": name, "code": "x = 1\n"})
    assert res.status_code == 400, name
    assert res.json()["detail"].startswith("Invalid script filename:")
    assert _names(root) == []


def test_save_stores_nfc_and_refuses_nfd_lookalike(client, root):
    res = client.post("/api/save", json={"filename": NFD_CAFE, "code": "x = 1\n"})
    assert res.status_code == 200
    assert _names(root) == [NFC_CAFE]
    again = client.post("/api/save", json={"filename": NFC_CAFE, "code": "x = 2\n"})
    assert again.status_code == 200
    assert _names(root) == [NFC_CAFE]


def test_rename_target_is_normalized(client, root):
    (root / "a.py").write_text("x = 1\n")
    res = client.post("/api/rename", json={"old_name": "a.py", "new_name": "B.PY"})
    assert res.status_code == 200, res.text
    assert _names(root) == ["B.py"]
    res = client.post("/api/rename", json={"old_name": "B.py", "new_name": "COM\u00b9.py"})
    assert res.status_code == 400
    assert "reserved device name" in res.json()["detail"]


def test_upload_name_is_stored_nfc(client, root):
    res = client.post("/api/upload-asset", files={"file": ("cafe\u0301.png", b"\x89PNG\r\n", "image/png")})
    assert res.status_code == 200, res.text
    assert [p.name for p in (root / "assets").iterdir()] == ["caf\u00e9.png"]


# Old.PY is not listed as a script (the list wants ".py"), so it is only covered for
# save/render below; the others are listed and must stay openable and renamable.
LEGACY = ["-legacy.py", "x .py", "COM\u00b9.py", NFD_CAFE, "_temp_run_keep.py"]


@pytest.mark.parametrize("legacy", LEGACY)
def test_existing_forbidden_name_open_rename_but_not_save(client, root, legacy):
    (root / legacy).write_text("x = 1\n")
    opened = client.get("/api/file-content", params={"filename": legacy})
    assert opened.status_code == 200, (legacy, opened.text)

    saved = client.post("/api/save", json={"filename": legacy, "code": "x = 2\n"})
    assert saved.status_code == 400, legacy
    assert saved.json()["detail"].startswith("Rename this file to save or render it:"), saved.json()
    assert (root / legacy).read_text() == "x = 1\n"
    assert len(_names(root)) == 1  # no Old.py / NFC copy next to it

    renamed = client.post("/api/rename", json={"old_name": legacy, "new_name": "fixed.py"})
    assert renamed.status_code == 200, (legacy, renamed.text)
    assert (root / "fixed.py").read_text() == "x = 1\n"


@pytest.mark.parametrize("legacy", ["-legacy.py", "x .py", "COM\u00b9.py", NFD_CAFE, "Old.PY"])
def test_existing_forbidden_name_render_says_rename(client, root, legacy):
    (root / legacy).write_text("from manim import *\nclass A(Scene):\n    def construct(self):\n        pass\n")
    with client.websocket_connect("/api/render") as ws:
        ws.send_json({"type": "start", "filename": legacy, "scene": "A", "quality": "l"})
        error, result = ws.receive_json(), ws.receive_json()
    assert error["type"] == "error"
    assert error["message"].startswith("Rename this file to save or render it:"), error
    assert result["status"] == "rejected"


def test_saving_over_an_uppercase_extension_file_says_rename(client, root):
    (root / "Old.PY").write_text("x = 1\n")
    saved = client.post("/api/save", json={"filename": "Old.PY", "code": "x = 2\n"})
    assert saved.status_code == 400
    assert saved.json()["detail"] == "Rename this file to save or render it: it would be saved as 'Old.py'."
    assert sorted(p.name for p in root.iterdir() if p.is_file()) == ["Old.PY"]


def test_missing_forbidden_name_render_is_still_invalid(client, root):
    with client.websocket_connect("/api/render") as ws:
        ws.send_json({"type": "start", "filename": "-ghost.py", "scene": "A", "quality": "l"})
        error, _ = ws.receive_json(), ws.receive_json()
    assert error["message"].startswith("Invalid script filename:")


def test_rename_status_codes_match_the_docs(client, root):
    # PROJECT_REFERENCE.md: 400 for an exact existing name, 409 only for a case/Unicode-form clash.
    (root / "a.py").write_text("x = 1\n")
    (root / "b.py").write_text("x = 2\n")
    (root / NFC_CAFE).write_text("x = 3\n")
    assert client.post("/api/rename", json={"old_name": "a.py", "new_name": "b.py"}).status_code == 400
    assert client.post("/api/rename", json={"old_name": "a.py", "new_name": "B.py"}).status_code == 409
    assert client.post("/api/rename", json={"old_name": "a.py", "new_name": "CAF\u00c9.py"}).status_code == 409
    assert client.post("/api/rename", json={"old_name": "missing.py", "new_name": "c.py"}).status_code == 404
    assert _names(root) == ["a.py", "b.py", NFC_CAFE]


def test_rename_fixes_an_nfd_legacy_name(client, root):
    (root / NFD_CAFE).write_text("x = 1\n")
    res = client.post("/api/rename", json={"old_name": NFD_CAFE, "new_name": NFD_CAFE})
    assert res.status_code == 200, res.text
    assert res.json()["new_name"] == NFC_CAFE
    assert _names(root) == [NFC_CAFE]


# --------------------------------------------------------------------------- #
# Round 4: every Unicode space counts as a space; U+2028/U+2029 are invisible
# --------------------------------------------------------------------------- #


def test_whitespace_list_is_exactly_python_isspace():
    import sys
    import unicodedata

    from workspace_paths import WHITESPACE_CHARS

    expected = {
        chr(code)
        for code in range(sys.maxunicode + 1)
        if chr(code).isspace() or unicodedata.category(chr(code)) == "Zs"
    }
    assert set(WHITESPACE_CHARS) == expected
    assert FIXTURE["whitespace_chars"] == [f"U+{ord(ch):04X}" for ch in WHITESPACE_CHARS]


@pytest.mark.parametrize("code", FIXTURE["whitespace_chars"])
def test_every_unicode_space_is_a_space(code):
    import unicodedata

    ch = chr(int(code[2:], 16))
    assert _validate(f"{ch}x.py") is not None
    assert _validate(f"x{ch}.py") is not None
    assert _validate(f"x.py{ch}") is not None
    assert to_script_name(f"x{ch}").endswith(unicodedata.normalize("NFC", ch))  # left alone, so it is refused


def test_fixture_covers_the_round4_cases():
    names = {v["name"] for v in FIXTURE["direct_names"]} | {v["script_name"] for v in FIXTURE["vectors"]}
    for needed in ["\u00a0x.py", "x\u00a0.py", "x\u3000.py", "CON\u2028.x.py", "a\u2029b.py"]:
        assert needed in names
        assert _validate(needed) is not None
    assert _validate("CON\u2028.x.py") == "Filename cannot contain control or invisible characters."
    # A space inside the stem is still fine.
    assert _validate("a\u00a0b.py") is None and _validate("a\u3000b.py") is None


def test_existing_files_with_a_space_lookalike_stay_reachable(root):
    ws = root
    (ws / "old\u00a0.py").write_text("x = 1\n")
    assert main.get_file_content("old\u00a0.py")["code"] == "x = 1\n"
    status = main.rename_file(main.RenameRequest(old_name="old\u00a0.py", new_name="old.py"))
    assert (ws / "old.py").exists() and status
