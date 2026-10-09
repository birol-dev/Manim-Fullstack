"""Concurrent saves, creates, and renames (r2: lost updates, torn reads, create/rename races)."""

import hashlib
import os
import threading
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse

import main
from file_ops import content_version


@pytest.fixture
def ws(tmp_path):
    (tmp_path / "media").mkdir()
    with patch.object(main, "WORKSPACE_DIR", str(tmp_path)), patch.object(main, "MEDIA_DIR", str(tmp_path / "media")):
        yield tmp_path


def _call(fn, *args):
    """Run an endpoint function directly: (status, body)."""
    try:
        result = fn(*args)
    except HTTPException as exc:
        return exc.status_code, {"detail": exc.detail}
    if isinstance(result, JSONResponse):
        import json

        return result.status_code, json.loads(result.body)
    return 200, result


def _save(**kw):
    return _call(main.save_file, main.SaveRequest(**kw))


def _rename(old, new):
    return _call(main.rename_file, main.RenameRequest(old_name=old, new_name=new))


def _run_together(*fns):
    barrier = threading.Barrier(len(fns))
    results = [None] * len(fns)

    def run(i, fn):
        barrier.wait()
        results[i] = fn()

    threads = [threading.Thread(target=run, args=(i, fn)) for i, fn in enumerate(fns)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results


@pytest.mark.parametrize("round_", range(5))
def test_same_base_version_has_exactly_one_winner(ws, round_):
    status, body = _save(filename="race.py", code="x = 0\n")
    base = body["version"]
    results = _run_together(*[
        (lambda i=i: _save(filename="race.py", code=f"x = {i + 1}\n", base_version=base)) for i in range(20)
    ])
    winners = [body for status, body in results if status == 200]
    losers = [body for status, body in results if status != 200]
    assert len(winners) == 1
    on_disk = (ws / "race.py").read_bytes()
    assert winners[0]["version"] == content_version(on_disk)
    assert all(status == 412 for status, _ in results if status != 200)
    # Every loser is told the version that is on disk now.
    assert {body["current_version"] for body in losers} == {winners[0]["version"]}


def test_conflict_response_carries_current_version_and_etag(client, ws):
    (ws / "a.py").write_text("one\n")
    stale = client.get("/api/file-content?filename=a.py").json()["version"]
    current = client.post("/api/save", json={"filename": "a.py", "code": "two\n"}).json()["version"]
    res = client.post("/api/save", json={"filename": "a.py", "code": "three\n", "base_version": stale})
    assert res.status_code == 412
    assert res.json()["current_version"] == current
    assert res.headers["etag"] == f'"{current}"'
    assert "changed outside this tab" in res.json()["detail"]


def test_version_comes_from_the_bytes_written_not_a_reread(ws):
    """r2: the version was re-read from disk, so a write landing in between was attributed to this save."""
    real_write = main.atomic_write

    def write_then_someone_else_writes(path, data, **kw):
        version = real_write(path, data, **kw)
        with open(path, "wb") as f:
            f.write(b"# another process\n")
        return version

    with patch.object(main, "atomic_write", side_effect=write_then_someone_else_writes):
        status, body = _save(filename="v.py", code="mine = 1\n")
    assert status == 200
    assert body["version"] == hashlib.sha256(b"mine = 1\n").hexdigest()[:16]
    # So the next save based on it is refused instead of silently overwriting.
    status, body = _save(filename="v.py", code="mine = 2\n", base_version=body["version"])
    assert status == 412 and body["current_version"] == content_version(b"# another process\n")


def test_file_content_version_matches_the_code_returned(ws):
    """Code and version come from one read, so they always describe the same bytes."""
    (ws / "t.py").write_bytes(b"a" * 300_000)
    contents = [b"a" * 300_000, b"b" * 200_000]
    stop = threading.Event()
    mismatches = []

    def writer():
        i = 0
        while not stop.is_set():
            _save(filename="t.py", code=contents[i % 2].decode())
            i += 1

    def reader():
        while not stop.is_set():
            status, body = _call(main.get_file_content, "t.py")
            if status != 200:
                mismatches.append(("status", status))
                continue
            data = body["code"].encode()
            if data not in contents or content_version(data) != body["version"]:
                mismatches.append((len(data), body["version"]))

    threads = [threading.Thread(target=writer), threading.Thread(target=reader), threading.Thread(target=reader)]
    for t in threads:
        t.start()
    threading.Event().wait(1.0)
    stop.set()
    for t in threads:
        t.join()
    assert mismatches == []


def test_create_only_vs_rename_onto_the_same_name(ws):
    """r2 (Fixer #1): both used to succeed and one file's content was lost (29/30)."""
    for _ in range(30):
        (ws / "src.py").write_text("SRC = 1\n")
        created, renamed = _run_together(
            lambda: _save(filename="dst.py", code="CREATED = 1\n", create_only=True),
            lambda: _rename("src.py", "dst.py"),
        )
        statuses = sorted([created[0], renamed[0]])
        assert statuses in ([200, 400], [200, 409]), (created, renamed)
        content = (ws / "dst.py").read_text()
        if created[0] == 200:
            assert content == "CREATED = 1\n" and (ws / "src.py").read_text() == "SRC = 1\n"
        else:
            assert content == "SRC = 1\n" and not (ws / "src.py").exists()
        for name in ("src.py", "dst.py"):
            (ws / name).unlink(missing_ok=True)


def test_rename_never_replaces_a_file_saved_meanwhile(ws):
    for _ in range(30):
        (ws / "a.py").write_text("A = 1\n")
        saved, renamed = _run_together(
            lambda: _save(filename="b.py", code="B = 1\n"),
            lambda: _rename("a.py", "b.py"),
        )
        if saved[0] == 200 and renamed[0] == 200:
            # Rename first, then the save replaced its content: both acted on purpose,
            # the save is the newest write. The rename must never clobber the save.
            assert (ws / "b.py").read_text() == "B = 1\n"
        elif saved[0] == 200:
            assert renamed[0] == 400 and (ws / "a.py").read_text() == "A = 1\n"
        for name in ("a.py", "b.py"):
            (ws / name).unlink(missing_ok=True)


def test_parallel_create_only_has_one_winner(ws):
    results = _run_together(*[
        (lambda i=i: _save(filename="new.py", code=f"n = {i}\n", create_only=True)) for i in range(12)
    ])
    assert sorted(status for status, _ in results).count(200) == 1
    assert all(status in (200, 409) for status, _ in results)
    winner = next(body for status, body in results if status == 200)
    assert content_version((ws / "new.py").read_bytes()) == winner["version"]


def test_case_variants_share_one_lock_so_only_one_name_survives(ws):
    results = _run_together(
        lambda: _save(filename="Case.py", code="a\n", create_only=True),
        lambda: _save(filename="case.py", code="b\n", create_only=True),
    )
    assert sorted(status for status, _ in results) == [200, 409]
    assert len([p for p in ws.iterdir() if p.name.lower() == "case.py"]) == 1


def test_save_leaves_no_temp_files_and_keeps_newlines_exact(ws):
    status, body = _save(filename="nl.py", code="a\r\nb\n")
    assert status == 200
    assert (ws / "nl.py").read_bytes() == b"a\r\nb\n"
    assert [p.name for p in ws.iterdir() if p.is_file()] == ["nl.py"]


def test_rename_to_the_same_name_is_a_no_op(ws):
    (ws / "same.py").write_text("x\n")
    assert _rename("same.py", "same.py")[0] == 200
    assert (ws / "same.py").read_text() == "x\n"


def test_case_only_rename_still_works(ws):
    (ws / "low.py").write_text("x\n")
    status, body = _rename("low.py", "Low.py")
    assert status == 200 and body["new_name"] == "Low.py"
    assert [p.name for p in ws.iterdir() if p.is_file()] == ["Low.py"]


def test_startup_sweep_removes_interrupted_save_temp_files(ws):
    leftover = ws / ".~save-abc.tmp"
    leftover.write_text("partial")
    os.utime(leftover, (1, 1))
    main._sweep_temp_renders()
    assert not leftover.exists()
