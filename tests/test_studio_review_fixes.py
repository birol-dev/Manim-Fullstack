"""Regression tests for the review fixes: fingerprint cache, export queue, lists, preferences, motion."""

import asyncio
import json
import os
import time

from studio import storage
from studio.exports import ExportManager
from studio.preferences import PreferenceStore
from tests.studio_fakes import FakeRunner, RunnerFactory, make_service, wait_until


def records(service):
    return service._export_manager().list()


# --------------------------------------------------------------------------- #
# Fingerprints
# --------------------------------------------------------------------------- #

def test_tree_fingerprint_reuses_unchanged_trees_and_sees_every_change(tmp_path, monkeypatch):
    root = tmp_path / "tpl"
    root.mkdir()
    scene = root / "scene.py"
    scene.write_text("x = 1\n", encoding="utf-8")
    past = time.time() - 60
    os.utime(scene, (past, past))
    first = storage.tree_fingerprint(str(root))

    reads = []
    original = storage._stat_into
    monkeypatch.setattr(storage, "_stat_into", lambda *args: (reads.append(args), original(*args)))
    assert storage.tree_fingerprint(str(root)) == first
    assert reads == []  # unchanged and old enough: no file was read again

    scene.write_text("x = 2\n", encoding="utf-8")  # same size, written just now
    assert storage.tree_fingerprint(str(root)) != first
    (root / "extra.py").write_text("", encoding="utf-8")
    second = storage.tree_fingerprint(str(root))
    (root / "extra.py").unlink()
    assert storage.tree_fingerprint(str(root)) != second


def test_tree_fingerprint_keeps_empty_and_missing_roots_distinct(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert storage.tree_fingerprint(str(empty)) != storage.tree_fingerprint(str(tmp_path / "missing"))


# --------------------------------------------------------------------------- #
# The export queue
# --------------------------------------------------------------------------- #

def _manager(tmp_path, **options):
    return ExportManager(exports_dir=str(tmp_path / "exports"), work_dir=str(tmp_path / "work"),
                         index_path=str(tmp_path / "exports.json"), media_root=str(tmp_path),
                         plan=lambda job: {}, still=None, runner_factory=options.pop("runner_factory", FakeRunner),
                         **options)


def _record():
    return {"template": "announcement", "title": "Video", "format": "mp4", "quality": "draft",
            "width": 854, "height": 480, "fps": 15}


def test_a_crash_in_the_queue_is_saved_with_a_finish_time(tmp_path):
    manager = _manager(tmp_path)

    def broken(export_id):
        raise RuntimeError("boom")

    manager._process = broken
    try:
        started = manager.start(_record(), {"template": "announcement", "params": {}, "settings": {}})
        failed = wait_until(lambda: (r := manager.get(started["id"]))["status"] == "failed" and r)
        assert failed["finished"]
        index = json.loads((tmp_path / "exports.json").read_text(encoding="utf-8"))
        assert index["exports"][0]["status"] == "failed"
    finally:
        manager.shutdown(timeout=5)


def test_closing_the_app_as_an_export_finishes_keeps_the_file(tmp_path):
    manager = _manager(tmp_path)
    publish = manager._publish

    def publish_then_close(record, src, ext):
        final = publish(record, src, ext)
        manager._stopping = True  # the app starts closing right after the file landed
        return final

    manager._publish = publish_then_close
    try:
        started = manager.start(_record(), {"template": "announcement", "params": {}, "settings": {}})
        done = wait_until(lambda: (r := manager.get(started["id"]))["status"] in ("done", "queued", "failed") and r)
        assert done["status"] == "done"
        assert "resume" not in done
        assert os.path.isfile(os.path.join(manager.exports_dir, done["filename"]))
    finally:
        manager.shutdown(timeout=5)


def test_a_list_writes_the_export_index_once(tmp_path):
    blocker = FakeRunner("block")
    service, _ = make_service(tmp_path, runners=RunnerFactory(blocker))
    try:
        manager = service._export_manager()
        saves = []
        original = manager._save_locked
        manager._save_locked = lambda: (saves.append(1), original())[1]
        service.start_batch_sync("announcement", {}, {"theme": "clean"}, mapping={"headline": 0},
                                 rows=[[f"Row {n}"] for n in range(12)], title_column=0, quality="draft")
        assert blocker.started.wait(5)
        assert len(saves) <= 3  # the list itself, plus the first row starting
        index = json.loads(open(manager.index_path, encoding="utf-8").read())
        assert len(index["exports"]) == 12
    finally:
        blocker.release.set()
        service.shutdown_sync()


def test_trying_one_failed_row_again_keeps_it_in_its_list(tmp_path):
    service, _ = make_service(tmp_path, runners=RunnerFactory(FakeRunner("fail"), FakeRunner("fail"),
                                                              FakeRunner("ok")))
    try:
        result = service.start_batch_sync("announcement", {}, {"theme": "clean"}, mapping={"headline": 0},
                                          rows=[["One"], ["Two"]], title_column=0, quality="draft")
        wait_until(lambda: len(records(service)) == 2 and all(r["status"] == "failed" for r in records(service)))
        first, second = sorted(records(service), key=lambda r: r["title"])
        again = asyncio.run(service.retry_export(first["id"]))
        assert again["batch_id"] == result["batch_id"]
        wait_until(lambda: service._export_manager().get(again["id"])["status"] == "done")
        statuses = sorted(r["status"] for r in records(service))
        assert statuses == ["done", "failed"]  # replaced in place; the other row is untouched
        assert service._export_manager().get(second["id"])["status"] == "failed"
        assert service.get_batch_sync(result["batch_id"])["counts"]["done"] == 1
    finally:
        service.shutdown_sync()


def test_the_batch_retry_route_takes_one_export_id(tmp_path):
    service, _ = make_service(tmp_path, runners=RunnerFactory(FakeRunner("fail"), FakeRunner("fail"),
                                                              FakeRunner("ok")))
    try:
        result = service.start_batch_sync("announcement", {}, {"theme": "clean"}, mapping={"headline": 0},
                                          rows=[["One"], ["Two"]], title_column=0, quality="draft")
        wait_until(lambda: len(records(service)) == 2 and all(r["status"] == "failed" for r in records(service)))
        target = records(service)[0]["id"]
        retried = service.retry_batch_sync(result["batch_id"], target)
        assert len(retried["retried"]) == 1
    finally:
        service.shutdown_sync()


# --------------------------------------------------------------------------- #
# Preferences and motion previews
# --------------------------------------------------------------------------- #

def test_the_last_export_choice_is_a_preference(tmp_path):
    store = PreferenceStore(str(tmp_path))
    assert store.update({"export_format": "webm", "export_quality": "1080p60"})["export_format"] == "webm"
    try:
        store.update({"export_format": "../mp4"})
    except Exception as exc:  # noqa: BLE001
        assert "export_format" in str(getattr(exc, "errors", exc))
    else:
        raise AssertionError("a bad export choice was accepted")


def test_motion_previews_come_back_after_a_shutdown(tmp_path):
    service, _ = make_service(tmp_path)
    first = service._motion_manager()
    service.shutdown_sync()
    second = service._motion_manager()
    try:
        assert second is not first
        assert not getattr(second, "closing", False)
    finally:
        service.shutdown_sync()
