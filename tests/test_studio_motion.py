import asyncio
from pathlib import Path

import pytest

from studio.registry import TemplateError
from tests.studio_fakes import FakeMotionWorker, FakeRunner, RunnerFactory, make_service, wait_until


def run(coro):
    return asyncio.run(coro)


def terminal(service, rid):
    result = run(service.get_motion(rid))
    return result if result["status"] in ("done", "failed", "cancelled") else None


def test_motion_dimensions_cap_cache_and_invalidation(tmp_path):
    worker = FakeMotionWorker()
    service, still = make_service(tmp_path, motion_worker_factory=lambda: worker)
    try:
        for aspect, size in [("16:9", (720, 404)), ("9:16", (404, 720)), ("1:1", (720, 720)), ("4:5", (576, 720))]:
            first = run(service.start_motion("editor", "countdown", {"seconds": 300}, {"aspect": aspect}))
            result = wait_until(lambda: terminal(service, first["id"]))
            assert result["status"] == "done" and result["truncated"]
            assert (result["width"], result["height"]) == size
            assert result["fps"] == 15 and result["max_duration"] == 20
            assert not any(name.startswith("_") for name in result)
            assert worker.calls[-1]["job"]["max_duration"] == 20
            again = run(service.start_motion("editor", "countdown", {"seconds": 300}, {"aspect": aspect}))
            assert again["cached"] and again["status"] == "done" and again["url"] == result["url"]
        assert len(worker.calls) == 4 and not still.calls and service._exports is None
        changed = run(service.start_motion("editor", "countdown", {"seconds": 301}, {}))
        assert not changed["cached"]
        wait_until(lambda: terminal(service, changed["id"]))
        assert len(worker.calls) == 5
    finally:
        service.shutdown_sync()


def test_superseded_motion_is_killed_and_exports_still_run(tmp_path):
    worker, runner = FakeMotionWorker(block=True), FakeRunner()
    service, _ = make_service(tmp_path, motion_worker_factory=lambda: worker, runners=RunnerFactory(runner))
    try:
        first = run(service.start_motion("project", "countdown", {"seconds": 300}, {}))
        assert worker.started.wait(5)
        export = run(service.start_export("countdown", {"seconds": 3}, {}))
        assert runner.started.wait(5), "Exports must not wait behind motion previews"
        second = run(service.start_motion("project", "countdown", {"seconds": 4}, {}))
        assert worker.cancelled.wait(5)
        assert run(service.get_motion(first["id"]))["status"] == "cancelled"
        worker.release.set()
        result = wait_until(lambda: terminal(service, second["id"]))
        assert result["status"] == "done"
        wait_until(lambda: run(service.get_export(export["id"]))["status"] == "done")
        assert len(list(Path(service.previews_dir).glob("*.mp4"))) == 1
        assert not list(Path(service.previews_dir).glob(".~*"))
    finally:
        service.shutdown_sync()


def test_cancel_failure_and_retry(tmp_path):
    worker = FakeMotionWorker(block=True)
    service, _ = make_service(tmp_path, motion_worker_factory=lambda: worker)
    try:
        first = run(service.start_motion("editor", "countdown"))
        assert worker.started.wait(5)
        assert run(service.cancel_motion(first["id"]))["status"] == "cancelled"
        assert worker.cancelled.wait(5)
        worker.release.set()
        worker.fail = ValueError("private traceback")
        failed = run(service.start_motion("editor", "countdown"))
        result = wait_until(lambda: terminal(service, failed["id"]))
        assert result["status"] == "failed" and "private" not in result["error"]
        worker.fail = None
        retry = run(service.start_motion("editor", "countdown"))
        assert wait_until(lambda: terminal(service, retry["id"]))["status"] == "done"
        with pytest.raises(TemplateError):
            run(service.start_motion("../bad", "countdown"))
    finally:
        service.shutdown_sync()
