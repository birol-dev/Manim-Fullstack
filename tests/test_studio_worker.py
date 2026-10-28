"""The preview worker's parent side and protocol, against a fake child that needs no Manim.

The fake child uses the real ``studio.worker`` channel setup and request loop; only
``render`` is replaced, so stdout chatter, timeouts, crashes and recycling are real.
"""

import os
import sys
import textwrap

import pytest

from studio.worker import BACKEND_DIR, PreviewWorker, WorkerCrashed, WorkerReplyError, WorkerStartError, WorkerTimeout

FAKE_CHILD = textwrap.dedent('''
    import os, sys, time
    sys.path.insert(0, {backend!r})
    from studio import worker

    channel = worker._claim_protocol_channel()
    print("chatter from print before ready")
    os.write(1, b"chatter on fd 1\\n")

    class Fake(worker._Child):
        def render(self, request):
            job = request["job"]
            behavior = (job.get("params") or {{}}).get("behavior")
            print("render chatter", request["id"])
            os.write(1, b'@@studio {{"id": 999999, "ok": true}}\\n')  # fd 1 is stderr now: not a reply
            if behavior == "sleep":
                time.sleep(60)
            if behavior == "crash":
                os._exit(7)
            if behavior == "fail":
                return {{"id": request["id"], "ok": False, "error": "ValueError: nope", "traceback": "tb"}}
            with open(job["output"], "wb") as f:
                f.write(b"png")
            return {{"id": request["id"], "ok": True, "ms": 1, "output": job["output"], "pid": os.getpid()}}

    child = Fake(channel)
    if os.environ.get("FAKE_FATAL"):
        child.send({{"event": "fatal", "error": "ModuleNotFoundError: No module named 'manim'"}})
        sys.exit(3)
    if os.environ.get("FAKE_EXIT"):
        sys.exit(4)
    child.send({{"event": "ready", "pid": os.getpid(), "manim": "fake"}})
    sys.exit(child.serve(sys.stdin.buffer))
''')


@pytest.fixture
def fake_child(tmp_path):
    script = tmp_path / "fake_child.py"
    script.write_text(FAKE_CHILD.format(backend=BACKEND_DIR), encoding="utf-8")
    return [sys.executable, "-u", str(script)]


def _job(tmp_path, name="out.png", **params):
    return {"template": "countdown", "params": params, "settings": {}, "mode": "poster",
            "output": str(tmp_path / name)}


def test_render_round_trip_ignores_stdout_chatter(fake_child, tmp_path):
    worker = PreviewWorker(command=fake_child, request_timeout=20)
    try:
        reply = worker.render(_job(tmp_path), 64, 36)
        assert reply["ok"] and reply["output"].endswith("out.png") and (tmp_path / "out.png").exists()
        assert worker.info["event"] == "ready" and worker.starts == 1
        text = "\n".join(worker.log)
        assert "chatter from print before ready" in text and "chatter on fd 1" in text
        assert "render chatter" in text and "999999" in text  # went to the log, not the replies
        second = worker.render(_job(tmp_path, "two.png"), 64, 36)
        assert second["pid"] == reply["pid"]  # the same warm process
    finally:
        worker.stop()
    assert not worker.alive


def test_job_failure_keeps_the_worker(fake_child, tmp_path):
    worker = PreviewWorker(command=fake_child, request_timeout=20)
    try:
        with pytest.raises(WorkerReplyError) as info:
            worker.render(_job(tmp_path, behavior="fail"), 64, 36)
        assert "nope" in str(info.value) and info.value.traceback == "tb"
        pid = worker.pid
        worker.render(_job(tmp_path), 64, 36)
        assert worker.pid == pid
    finally:
        worker.close()


def test_timeout_kills_and_the_next_request_restarts(fake_child, tmp_path):
    worker = PreviewWorker(command=fake_child, request_timeout=20)
    try:
        worker.start()
        first_pid = worker.pid
        with pytest.raises(WorkerTimeout):
            worker.render(_job(tmp_path, behavior="sleep"), 64, 36, timeout=1.0)
        assert not worker.alive
        reply = worker.render(_job(tmp_path), 64, 36)
        assert reply["pid"] != first_pid and worker.starts == 2
    finally:
        worker.close()


def test_crash_is_reported_then_restarted(fake_child, tmp_path):
    worker = PreviewWorker(command=fake_child, request_timeout=20)
    try:
        with pytest.raises(WorkerCrashed):
            worker.render(_job(tmp_path, behavior="crash"), 64, 36)
        assert worker.render(_job(tmp_path), 64, 36)["ok"]
        assert worker.starts == 2
    finally:
        worker.close()


def test_recycles_after_max_jobs(fake_child, tmp_path):
    worker = PreviewWorker(command=fake_child, request_timeout=20, max_jobs=2)
    try:
        pids = [worker.render(_job(tmp_path, f"{i}.png"), 64, 36)["pid"] for i in range(3)]
        assert pids[0] == pids[1] != pids[2]
        assert worker.starts == 2
    finally:
        worker.close()


def test_dead_worker_between_jobs_is_replaced_silently(fake_child, tmp_path):
    worker = PreviewWorker(command=fake_child, request_timeout=20)
    try:
        worker.start()
        worker._proc.kill()
        worker._proc.wait()
        assert worker.render(_job(tmp_path), 64, 36)["ok"]
    finally:
        worker.close()


@pytest.mark.parametrize("variable, message", [("FAKE_FATAL", "could not load Manim"), ("FAKE_EXIT", "exited")])
def test_startup_failures(fake_child, tmp_path, monkeypatch, variable, message):
    monkeypatch.setenv(variable, "1")
    worker = PreviewWorker(command=fake_child, start_timeout=20)
    with pytest.raises(WorkerStartError) as info:
        worker.render(_job(tmp_path), 64, 36)
    assert message in str(info.value)
    assert not worker.alive


def test_child_environment(fake_child, tmp_path, monkeypatch):
    monkeypatch.setenv("COMPOSER_JOB", "/somewhere/job.json")
    worker = PreviewWorker(command=fake_child, media_dir=str(tmp_path / "media"))
    env = worker._env()
    assert "COMPOSER_JOB" not in env and env["STUDIO_WORKER_MEDIA"] == str(tmp_path / "media")
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert PreviewWorker().command[-2:] == ["-m", "studio.worker"]
    assert os.path.isdir(BACKEND_DIR)
