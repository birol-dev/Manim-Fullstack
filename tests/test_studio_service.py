"""The studio service without Manim: catalog, validation, preview cache, exports, projects, icons."""

import asyncio
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from studio import exports as exports_module
from studio import registry
from studio import service as service_module
from studio.errors import BusyError, NotFoundError, RenderError, RendererUnavailable, RenderTimeout
from studio.exports import INTERRUPTED, ConflictError, ManimVideoRunner, VideoJob
from studio.registry import TemplateError
from studio.service import StudioService
from studio.storage import png_size, prune_previews, slugify, tree_fingerprint
from studio.worker import WorkerCrashed, WorkerReplyError, WorkerStartError, WorkerTimeout
from tests.studio_fakes import STORYBOARD, FakeRunner, FakeWorker, RunnerFactory, make_service, tiny_png, wait_until

LAUNCH = {"seconds": 10, "title": "", "style": "big", "finish_text": "Happy New Year!", "confetti": True}


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def svc(tmp_path):
    service, worker = make_service(tmp_path)
    service.fake = worker
    yield service
    service.shutdown_sync()


# --------------------------------------------------------------------------- #
# Catalog
# --------------------------------------------------------------------------- #


def test_catalog_shape(svc):
    cat = run(svc.catalog())
    assert set(cat) >= {"sections", "templates", "themes", "aspects", "qualities", "formats"}
    countdown = next(t for t in cat["templates"] if t["id"] == "countdown")
    assert countdown["schema"]["properties"]["seconds"]["x-widget"] == "duration"
    assert countdown["defaults"]["seconds"] == 300
    assert {p["id"] for p in countdown["presets"]} >= {"launch-countdown"}
    timers = next(s for s in cat["sections"] if s["id"] == "timers")
    card = next(c for c in timers["cards"] if c["id"] == "launch-countdown")
    assert set(card) == {"id", "template", "title", "summary", "category", "params", "settings", "tags", "peek_url"}
    assert card["peek_url"] is None or (card["peek_url"].startswith("/api/studio/peeks/")
                                       and card["peek_url"].endswith(".mp4"))
    theme = cat["themes"][0]
    assert set(theme) == {"id", "name", "dark", "bg", "text", "accent"} and len(theme["accent"]) == 5
    assert [a["id"] for a in cat["aspects"]] == ["16:9", "9:16", "1:1", "4:5"]
    assert [q["id"] for q in cat["qualities"]] == ["draft", "720p", "1080p", "1080p60", "4k"]
    assert {"short", "fps", "label"} <= set(cat["qualities"][1])
    assert {f["id"] for f in cat["formats"]} == {"mp4", "gif", "webm", "mov", "png"}


def test_catalog_matches_registry(svc):
    try:
        expected = registry.catalog()
    except Exception as exc:  # another template is mid-edit; the service skips it
        pytest.skip(f"a template does not load right now: {exc}")
    cat = run(svc.catalog())

    def without_peek(card):
        assert "peek_url" in card
        return {key: value for key, value in card.items() if key != "peek_url"}

    sections = [{"id": section["id"], "title": section["title"],
                 "cards": [without_peek(card) for card in section["cards"]]} for section in cat["sections"]]
    templates = [{**template, "presets": [without_peek(card) for card in template["presets"]]}
                 for template in cat["templates"]]
    assert sections == expected["sections"]
    assert templates == expected["templates"]


def test_catalog_skips_a_broken_template(svc, monkeypatch):
    real = registry.get_template

    def flaky(template_id):
        if template_id == "countdown":
            raise SyntaxError("half-saved file")
        return real(template_id)

    monkeypatch.setattr(registry, "get_template", flaky)
    svc._catalog_cache = None
    cat = run(svc.catalog())
    assert "countdown" not in [t["id"] for t in cat["templates"]]


def test_template_info(svc):
    info = run(svc.template_info("countdown"))
    assert info["id"] == "countdown" and "schema" in info
    with pytest.raises(NotFoundError):
        run(svc.template_info("no_such_template"))


def test_prewarm_starts_the_worker_from_the_catalog(tmp_path):
    service, worker = make_service(tmp_path, prewarm=True)
    run(service.catalog())
    wait_until(lambda: worker.alive)
    service.shutdown_sync()


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #


def _errors(exc_info):
    return {e["field"]: e["message"] for e in exc_info.value.errors}


def test_validation_errors_have_field_paths(svc):
    with pytest.raises(TemplateError) as info:
        run(svc.preview("countdown", {"seconds": 1, "style": "zigzag", "nope": 1}, {"aspect": "3:2"}))
    fields = _errors(info)
    assert {"params.seconds", "params.style", "params.nope", "settings.aspect"} <= set(fields)
    assert svc.fake.calls == []


def test_unknown_template_theme_mode_and_shapes(svc):
    with pytest.raises(TemplateError) as info:
        run(svc.preview("nope", {}, {}))
    assert _errors(info).keys() == {"template"}
    with pytest.raises(TemplateError) as info:
        run(svc.preview("countdown", {}, {"theme": "neon"}))
    assert _errors(info).keys() == {"settings.theme"}
    with pytest.raises(TemplateError) as info:
        run(svc.preview("countdown", {}, {}, mode="video"))
    assert _errors(info).keys() == {"mode"}
    with pytest.raises(TemplateError) as info:
        run(svc.preview("countdown", ["not", "a", "dict"], {}))
    assert _errors(info).keys() == {"params"}
    with pytest.raises(TemplateError) as info:
        run(svc.preview("countdown", {}, {}, short=5000))
    assert _errors(info).keys() == {"short"}
    with pytest.raises(TemplateError) as info:
        run(svc.preview("countdown", {"title": "x" * 300_000}, {}))
    assert _errors(info).keys() == {"params"}


def test_length_outside_the_templates_range(svc):
    spec = next((s for s in (registry.get_template(t) for t in registry.template_ids() if t != "countdown")
                 if not s.meta.length_from_params and s.meta.max_length < 3600), None)
    if spec is None:
        pytest.skip("no fixed-length template installed")
    with pytest.raises(TemplateError) as info:
        svc._validate(spec.id, {}, {"length": spec.meta.max_length + 1, "aspect": spec.meta.default_aspect})
    assert "settings.length" in _errors(info)
    # countdown's length comes from its params, so settings.length is not range-checked
    svc._validate("countdown", {}, {"length": 3000})


# --------------------------------------------------------------------------- #
# Previews
# --------------------------------------------------------------------------- #


def test_poster_is_rendered_once_then_cached(svc):
    first = run(svc.preview("countdown", LAUNCH, {"aspect": "9:16", "theme": "pop"}))
    assert first["cached"] is False and first["mode"] == "poster"
    assert first["url"].startswith("/media/studio/previews/") and first["url"].endswith(".png")
    assert (first["width"], first["height"]) == (360, 640)
    assert os.path.isfile(first["path"])
    assert os.path.dirname(first["path"]) == svc.previews_dir
    job = svc.fake.calls[0]["job"]
    assert job["mode"] == "poster" and job["assets_dir"] == svc.assets_dir
    assert job["params"]["seconds"] == 10 and job["params"]["subtitle"] == ""  # normalized with defaults
    assert (svc.fake.calls[0]["width"], svc.fake.calls[0]["height"]) == (360, 640)

    again = run(svc.preview("countdown", dict(LAUNCH), {"theme": "pop", "aspect": "9:16"}))
    assert again["cached"] is True and again["url"] == first["url"]
    assert len(svc.fake.calls) == 1
    # Spelling a default explicitly is the same input.
    same = run(svc.preview("countdown", {**LAUNCH, "subtitle": ""}, {"theme": "pop", "aspect": "9:16"}))
    assert same["cached"] is True
    other = run(svc.preview("countdown", {**LAUNCH, "seconds": 11}, {"theme": "pop", "aspect": "9:16"}))
    assert other["cached"] is False and other["url"] != first["url"]
    leftovers = [n for n in os.listdir(svc.previews_dir) if n.startswith(".~")]
    assert leftovers == []


def test_storyboard_returns_its_metadata(svc):
    result = run(svc.preview("countdown", LAUNCH, {}, mode="storyboard"))
    assert result["storyboard"] == STORYBOARD
    assert (result["width"], result["height"]) == (200, 90)  # the sheet's own size
    assert os.path.isfile(os.path.splitext(result["path"])[0] + ".json")
    assert run(svc.preview("countdown", LAUNCH, {}, mode="storyboard"))["cached"] is True
    poster = run(svc.preview("countdown", LAUNCH, {}))
    assert poster["cached"] is False and "storyboard" not in poster


def test_kit_change_restarts_worker_and_misses_cache(svc, monkeypatch):
    monkeypatch.setattr(svc, "_kit_fingerprint", lambda: "kit-a")
    run(svc.preview("countdown", {}, {}))
    assert svc.fake.stops == 0
    monkeypatch.setattr(svc, "_kit_fingerprint", lambda: "kit-b")
    result = run(svc.preview("countdown", {}, {}))
    assert result["cached"] is False and svc.fake.stops == 1 and len(svc.fake.calls) == 2


def test_template_file_change_misses_cache_and_reloads_schema(svc, monkeypatch):
    stamp = {"value": "one"}
    real = service_module.tree_fingerprint
    monkeypatch.setattr(service_module, "tree_fingerprint",
                        lambda *roots: stamp["value"] if roots and roots[0].endswith("countdown") else real(*roots))
    run(svc.preview("countdown", {}, {}))
    old_spec = registry.get_template("countdown")
    stamp["value"] = "two"
    assert run(svc.preview("countdown", {}, {}))["cached"] is False
    assert registry.get_template("countdown") is not old_spec  # re-read from disk


def test_reuploaded_asset_refreshes_the_preview(svc):
    os.makedirs(svc.assets_dir, exist_ok=True)
    logo = os.path.join(svc.assets_dir, "logo.png")
    with open(logo, "wb") as f:
        f.write(tiny_png(4, 4))
    settings = {"brand": {"logo": "logo.png"}}
    run(svc.preview("countdown", {}, settings))
    assert run(svc.preview("countdown", {}, settings))["cached"] is True
    with open(logo, "wb") as f:
        f.write(tiny_png(8, 8))
    os.utime(logo, (1, 1))
    assert run(svc.preview("countdown", {}, settings))["cached"] is False


@pytest.mark.parametrize("error, expected", [
    (WorkerReplyError("ValueError: bad layout", "tb"), RenderError),
    (WorkerTimeout("took too long"), RenderTimeout),
    (WorkerCrashed("crashed"), RenderError),
    (WorkerStartError("No module named 'manim'"), RendererUnavailable),
    (FileNotFoundError(2, "No such file"), RendererUnavailable),
])
def test_worker_failures_become_studio_errors(svc, error, expected):
    svc.fake.fail = error
    with pytest.raises(expected) as info:
        run(svc.preview("countdown", {}, {}))
    assert info.type is expected
    assert os.listdir(svc.previews_dir) == []  # nothing half-written is left behind


def test_cache_is_pruned_to_its_limit(tmp_path):
    folder = tmp_path / "previews"
    folder.mkdir()
    for i in range(8):
        (folder / f"k{i}.png").write_bytes(tiny_png(1, 1))
        (folder / f"k{i}.json").write_text("{}")
        os.utime(folder / f"k{i}.png", (1000 + i, 1000 + i))
    (folder / ".~stale.png").write_bytes(b"x")
    os.utime(folder / ".~stale.png", (1, 1))
    assert prune_previews(str(folder), keep=5) == 3
    names = sorted(os.listdir(folder))
    assert names == sorted([f"k{i}.{ext}" for i in range(3, 8) for ext in ("png", "json")])


def test_service_prunes_after_rendering(tmp_path):
    service, worker = make_service(tmp_path, cache_limit=2)
    for seconds in (5, 6, 7, 8):
        run(service.preview("countdown", {"seconds": seconds}, {}))
    assert len([n for n in os.listdir(service.previews_dir) if n.endswith(".png")]) == 2
    service.shutdown_sync()


def test_helpers():
    assert slugify("Happy New Year!") == "happy-new-year"
    assert slugify("Ça va? Ünïcode") == "ca-va-unicode"
    assert slugify("!!!", fallback="countdown") == "countdown"
    assert len(slugify("word " * 30)) <= 40
    assert png_size(os.devnull) is None


def test_tree_fingerprint_follows_edits(tmp_path):
    (tmp_path / "a.py").write_text("x = 1")
    (tmp_path / "__pycache__").mkdir()
    before = tree_fingerprint(str(tmp_path))
    (tmp_path / "__pycache__" / "a.cpython-312.pyc").write_bytes(b"junk")
    assert tree_fingerprint(str(tmp_path)) == before
    (tmp_path / "a.py").write_text("x = 22")
    assert tree_fingerprint(str(tmp_path)) != before


# --------------------------------------------------------------------------- #
# Exports
# --------------------------------------------------------------------------- #


def _settled(svc, export_id):
    return wait_until(lambda: (lambda e: e if e["status"] in ("done", "failed", "cancelled") else None)(
        run(svc.get_export(export_id))))


def test_export_lifecycle(tmp_path):
    runner = FakeRunner("block")
    svc, worker = make_service(tmp_path, runners=RunnerFactory(runner))
    export = run(svc.start_export("countdown", LAUNCH, {"theme": "pop"}, format="mp4", quality="720p",
                                  title="Happy New Year!"))
    assert export["status"] == "queued" and export["progress"] is None
    assert (export["width"], export["height"], export["fps"]) == (1280, 720, 15)  # META.export_fps wins
    assert runner.started.wait(5)
    rendering = run(svc.get_export(export["id"]))
    assert rendering["status"] == "rendering"
    assert rendering["progress"] == 37  # (animation 1 at 50%) of 4 plays from the storyboard
    assert rendering["message"] == "Rendering animation 2 of 4"
    assert worker.calls[0]["job"]["mode"] == "storyboard"  # the plan for the progress total
    job = json.loads(open(runner.job.job_file, encoding="utf-8").read())
    assert job["mode"] == "video" and job["params"]["seconds"] == 10 and job["assets_dir"] == svc.assets_dir
    assert runner.job.timeout >= 120 and (runner.job.width, runner.job.height, runner.job.fps) == (1280, 720, 15)

    runner.release.set()
    done = _settled(svc, export["id"])
    assert done["status"] == "done" and done["progress"] == 100
    assert done["filename"] == f"happy-new-year-{export['id']}.mp4"
    assert done["url"] == "/media/studio/exports/" + done["filename"]
    assert done["size"] > 0 and done["duration"] == STORYBOARD["length"]
    assert run(svc.cancel_export(export["id"])) == done
    assert os.path.isfile(os.path.join(svc.exports_dir, done["filename"]))
    assert not os.path.exists(os.path.dirname(runner.job.job_file))  # the job folder is cleaned up
    assert [e["id"] for e in run(svc.list_exports())] == [export["id"]]
    svc.shutdown_sync()


@pytest.mark.parametrize("format", ["mp4", "png"])
def test_same_title_exports_use_the_full_id(tmp_path, monkeypatch, format):
    ids = iter(["abcdef000001", "abcdef000002"])
    token_hex = exports_module.secrets.token_hex
    monkeypatch.setattr(exports_module.secrets, "token_hex", lambda n: next(ids) if n == 6 else token_hex(n))
    svc, _ = make_service(tmp_path)
    try:
        first, second = [_settled(svc, run(svc.start_export("countdown", {}, {}, format=format,
                                                          quality="draft", title="Same title"))["id"])
                         for _ in range(2)]
        assert first["filename"] == f"same-title-{first['id']}.{format}"
        assert second["filename"] == f"same-title-{second['id']}.{format}"
        run(svc.remove_export(first["id"]))
        assert os.path.isfile(os.path.join(svc.exports_dir, second["filename"]))
    finally:
        svc.shutdown_sync()


def test_export_publication_refuses_to_overwrite(tmp_path):
    svc, _ = make_service(tmp_path)
    manager = svc._export_manager()
    os.makedirs(svc.exports_dir)
    dest = os.path.join(svc.exports_dir, "same-title-abcdef000001.mp4")
    with open(dest, "wb") as f:
        f.write(b"original")
    source = tmp_path / "new.mp4"
    source.write_bytes(b"replacement")
    with pytest.raises(FileExistsError):
        manager._publish({"_slug": "same-title", "id": "abcdef000001"}, str(source), ".MP4")
    assert open(dest, "rb").read() == b"original"
    assert source.read_bytes() == b"replacement"


def test_queue_restart_rechecks_the_thread_after_join(tmp_path, monkeypatch):
    svc, _ = make_service(tmp_path)
    manager = svc._export_manager()
    joined = threading.Barrier(3)
    stopped = threading.Event()
    threads = []
    thread_class = threading.Thread

    class StoppingThread:
        def is_alive(self):
            return not stopped.is_set()

        def join(self, timeout):
            joined.wait(timeout=5)
            assert stopped.wait(5)

    def make_thread(*args, **kwargs):
        thread = thread_class(*args, **kwargs)
        if kwargs.get("name") == "studio-exports":
            threads.append(thread)
        return thread

    manager._thread = StoppingThread()
    manager._stopping = True
    monkeypatch.setattr(exports_module.threading, "Thread", make_thread)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = [pool.submit(svc.start_export_sync, "countdown", {}, {}, quality="draft")
                       for _ in range(2)]
            try:
                joined.wait(timeout=5)
            finally:
                stopped.set()
            exports = [future.result(timeout=5) for future in pending]
        assert len(threads) == 1
        assert all(_settled(svc, export["id"])["status"] == "done" for export in exports)
    finally:
        stopped.set()
        svc.shutdown_sync()
        for thread in threads:
            thread.join(5)


@pytest.mark.parametrize("format", ["mp4", "png"])
def test_cancel_during_publication_removes_the_output(tmp_path, monkeypatch, format):
    svc, _ = make_service(tmp_path)
    manager = svc._export_manager()
    publish = manager._publish
    published, release = threading.Event(), threading.Event()

    def paused_publish(*args):
        path = publish(*args)
        published.set()
        assert release.wait(5)
        return path

    monkeypatch.setattr(manager, "_publish", paused_publish)
    try:
        export = run(svc.start_export("countdown", {}, {}, format=format, quality="draft"))
        assert published.wait(5)
        assert manager.cancel(export["id"])["message"] == "Stopping"
        release.set()
        cancelled = _settled(svc, export["id"])
        assert cancelled["status"] == "cancelled" and "filename" not in cancelled
        assert os.listdir(svc.exports_dir) == []
    finally:
        release.set()
        svc.shutdown_sync()


def test_export_failure_and_slug_from_template(tmp_path):
    svc, _ = make_service(tmp_path, runners=RunnerFactory(FakeRunner("fail")))
    export = run(svc.start_export("countdown", {}, {}, quality="draft"))
    failed = _settled(svc, export["id"])
    assert failed["status"] == "failed" and "fake template broke" in failed["error"]
    assert failed["log"][-1] == "ValueError: the fake template broke"
    assert failed["title"] == "Countdown timer"
    svc.shutdown_sync()


def test_cancel_running_and_queued_exports(tmp_path):
    first, second = FakeRunner("block"), FakeRunner("ok")
    svc, _ = make_service(tmp_path, runners=RunnerFactory(first, second))
    running = run(svc.start_export("countdown", {}, {}, quality="draft"))
    queued = run(svc.start_export("countdown", {}, {}, quality="draft"))
    assert first.started.wait(5)
    assert run(svc.cancel_export(queued["id"]))["status"] == "cancelled"
    stopped = run(svc.cancel_export(running["id"]))
    assert stopped["status"] == "cancelled" and first.cancelled.is_set()
    assert not second.started.is_set()  # the queued one never ran
    assert not os.path.isdir(svc.exports_dir) or os.listdir(svc.exports_dir) == []
    with pytest.raises(NotFoundError):
        run(svc.cancel_export("ffffffffffff"))
    svc.shutdown_sync()


def test_png_export_uses_a_full_size_poster(tmp_path):
    svc, worker = make_service(tmp_path)
    export = run(svc.start_export("countdown", {}, {"aspect": "1:1"}, format="png", quality="1080p"))
    done = _settled(svc, export["id"])
    assert done["status"] == "done" and done["filename"].endswith(".png") and done["duration"] is None
    assert worker.calls[-1]["job"]["mode"] == "poster"
    assert (worker.calls[-1]["width"], worker.calls[-1]["height"]) == (1080, 1080)
    assert png_size(os.path.join(svc.exports_dir, done["filename"])) == (1080, 1080)
    svc.shutdown_sync()


def test_transparent_mp4_becomes_mov(svc):
    export = run(svc.start_export("countdown", {}, {"background": {"kind": "transparent"}}, quality="draft"))
    assert export["format"] == "mov" and export["transparent"] is True


def test_export_input_errors(svc):
    with pytest.raises(TemplateError) as info:
        run(svc.start_export("countdown", {}, {}, format="avi", quality="8k"))
    assert _errors(info).keys() == {"format", "quality"}
    with pytest.raises(TemplateError) as info:
        run(svc.start_export("countdown", {}, {}, title=5))
    assert _errors(info).keys() == {"title"}


def test_export_queue_is_capped(tmp_path):
    svc, _ = make_service(tmp_path, runners=RunnerFactory(FakeRunner("block")), max_active_exports=2)
    run(svc.start_export("countdown", {}, {}, quality="draft"))
    run(svc.start_export("countdown", {}, {}, quality="draft"))
    with pytest.raises(BusyError):
        run(svc.start_export("countdown", {}, {}, quality="draft"))
    svc.shutdown_sync()


def test_clean_shutdown_requeues_and_resumes_exports(tmp_path):
    blocker = FakeRunner("block")
    svc, _ = make_service(tmp_path, runners=RunnerFactory(FakeRunner("ok"), blocker))
    done = _settled(svc, run(svc.start_export("countdown", {"seconds": 5}, {}, quality="draft"))["id"])
    running = run(svc.start_export("countdown", {"seconds": 10}, {}, quality="draft"))
    queued = run(svc.start_export("countdown", {"seconds": 20}, {}, quality="draft"))
    assert blocker.started.wait(5)
    svc.shutdown_sync()  # a clean stop hands the active exports back to the queue

    assert run(svc.get_export(running["id"]))["status"] == "queued"
    saved = {e["id"]: e for e in json.load(open(svc.index_path, encoding="utf-8"))["exports"]}
    assert saved[done["id"]]["status"] == "done"
    for export in (running, queued):
        record = saved[export["id"]]
        assert record["status"] == "queued" and record["resume"] is True
        assert record["progress"] is None and record["message"] == exports_module.RESUMING
        assert record["request"] == export["request"]  # the same request retry_export would use
        assert not any(key.startswith("_") for key in record)

    class ParamsRunner(FakeRunner):
        def run(self, job, on_progress, on_log):
            with open(job.job_file, encoding="utf-8") as f:
                self.params = json.load(f)["params"]
            return super().run(job, on_progress, on_log)

    first = ParamsRunner("block")
    factory = RunnerFactory(first, ParamsRunner("ok"))
    again, _ = make_service(tmp_path, runners=factory)
    run(again.list_exports())
    assert first.started.wait(5)
    listed = {e["id"]: e for e in run(again.list_exports())}
    # The older export (the one that had been rendering) is resumed first; the
    # other waits with its resume flag until the queue picks it up.
    assert listed[running["id"]]["status"] == "rendering" and "resume" not in listed[running["id"]]
    assert listed[queued["id"]]["status"] == "queued" and listed[queued["id"]]["resume"] is True
    first.release.set()
    for export in (running, queued):
        resumed = _settled(again, export["id"])
        assert resumed["status"] == "done" and resumed["progress"] == 100
        assert "resume" not in resumed and resumed["request"] == export["request"]
    assert [r.params["seconds"] for r in factory.made] == [10, 20]

    # A done export whose file was deleted drops out of the list after a restart.
    os.unlink(os.path.join(again.exports_dir, done["filename"]))
    again.shutdown_sync()
    third, _ = make_service(tmp_path)
    try:
        assert done["id"] not in {e["id"] for e in run(third.list_exports())}
    finally:
        third.shutdown_sync()


def test_a_crash_without_resume_flags_still_fails_interrupted(tmp_path):
    index = tmp_path / "ws" / "studio" / "exports.json"
    index.parent.mkdir(parents=True)
    index.write_text(json.dumps({"version": 1, "exports": [
        {"id": "abcdef000001", "status": "rendering", "created": "2", "progress": 50},
        {"id": "abcdef000002", "status": "queued", "created": "1"},
    ]}), encoding="utf-8")
    runners = RunnerFactory()
    svc, _ = make_service(tmp_path, runners=runners)
    try:
        records = {e["id"]: e for e in run(svc.list_exports())}
        for export_id in ("abcdef000001", "abcdef000002"):
            assert records[export_id]["status"] == "failed"
            assert records[export_id]["error"] == INTERRUPTED
            assert "resume" not in records[export_id]
        assert runners.made == []  # nothing was resumed
    finally:
        svc.shutdown_sync()


def test_a_resumed_export_whose_request_is_gone_fails_clearly(tmp_path):
    index = tmp_path / "ws" / "studio" / "exports.json"
    index.parent.mkdir(parents=True)
    index.write_text(json.dumps({"version": 1, "exports": [
        {"id": "abcdef000001", "status": "queued", "resume": True, "created": "1", "width": 640,
         "height": 360, "fps": 15, "format": "mp4",
         "request": {"template": "template-that-was-deleted", "params": {}, "settings": {}}},
    ]}), encoding="utf-8")
    svc, _ = make_service(tmp_path)
    try:
        record = run(svc.list_exports())[0]
        assert record["status"] == "failed" and "resume" not in record
        assert record["message"] == exports_module.RESUME_FAILED
        assert exports_module.RESUME_FAILED in record["error"]
        assert "template-that-was-deleted" in record["error"]
    finally:
        svc.shutdown_sync()


def test_cancel_and_remove_a_resumed_export(tmp_path):
    blocker = FakeRunner("block")
    svc, _ = make_service(tmp_path, runners=RunnerFactory(FakeRunner("ok"), blocker, blocker))
    _settled(svc, run(svc.start_export("countdown", {"seconds": 5}, {}, quality="draft"))["id"])
    running = run(svc.start_export("countdown", {"seconds": 10}, {}, quality="draft"))
    queued = run(svc.start_export("countdown", {"seconds": 20}, {}, quality="draft"))
    assert blocker.started.wait(5)
    svc.shutdown_sync()

    resumed_blocker = FakeRunner("block")
    again, _ = make_service(tmp_path, runners=RunnerFactory(resumed_blocker, FakeRunner("ok")))
    run(again.list_exports())
    assert resumed_blocker.started.wait(5)
    record = run(again.get_export(running["id"]))
    assert record["status"] == "rendering" and "resume" not in record  # cleared once started
    assert run(again.get_export(queued["id"]))["resume"] is True
    cancelled = run(again.cancel_export(running["id"]))
    assert cancelled["status"] == "cancelled"
    assert _settled(again, queued["id"])["status"] == "done"
    removed = run(again.remove_export(running["id"]))
    assert removed["id"] == running["id"]
    assert running["id"] not in {e["id"] for e in run(again.list_exports())}
    again.shutdown_sync()


def test_a_cancel_pending_at_shutdown_stays_cancelled(tmp_path):
    blocker = FakeRunner("block")
    svc, _ = make_service(tmp_path, runners=RunnerFactory(FakeRunner("ok"), blocker))
    _settled(svc, run(svc.start_export("countdown", {"seconds": 5}, {}, quality="draft"))["id"])
    running = run(svc.start_export("countdown", {"seconds": 10}, {}, quality="draft"))
    assert blocker.started.wait(5)
    manager = svc._export_manager()
    with manager._lock:  # the person pressed Cancel, then closed the app before it stopped
        manager._records[running["id"]]["_cancel"] = True
    svc.shutdown_sync()

    again, _ = make_service(tmp_path, runners=RunnerFactory(FakeRunner("ok")))
    record = run(again.get_export(running["id"]))
    assert record["status"] == "cancelled" and "resume" not in record
    again.shutdown_sync()


def test_history_pruning_keeps_finished_files(tmp_path):
    svc, _ = make_service(tmp_path)
    manager = svc._export_manager()
    manager.max_records = 1
    try:
        first = _settled(svc, run(svc.start_export("countdown", {}, {}, quality="draft"))["id"])
        second = _settled(svc, run(svc.start_export("countdown", {}, {}, quality="draft"))["id"])
        assert [record["id"] for record in manager.list()] == [second["id"], first["id"]]
        assert os.path.isfile(os.path.join(svc.exports_dir, first["filename"]))
        assert os.path.isfile(os.path.join(svc.exports_dir, second["filename"]))
    finally:
        svc.shutdown_sync()


@pytest.mark.parametrize("filename", ["../outside.mp4", "linked/outside.mp4", "link.mp4"])
def test_history_pruning_preserves_files_outside_exports(tmp_path, filename):
    svc, _ = make_service(tmp_path)
    manager = svc._export_manager()
    manager._ensure_loaded()
    manager.max_records = 1
    os.makedirs(svc.exports_dir)
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"keep")
    if filename == "../outside.mp4":
        filename = os.path.relpath(outside, svc.exports_dir)
    else:
        link = os.path.join(svc.exports_dir, filename.split("/")[0])
        try:
            os.symlink(tmp_path if "/" in filename else outside, link, target_is_directory="/" in filename)
        except OSError:
            pytest.skip("symlinks are unavailable")
    with manager._lock:
        manager._records = {"abcdef000001": {"id": "abcdef000001", "status": "done", "created": "1",
                                              "filename": filename},
                            "abcdef000002": {"id": "abcdef000002", "status": "failed", "created": "2"}}
        manager._save_locked()
    assert outside.read_bytes() == b"keep"
    assert [record["id"] for record in manager.list()] == ["abcdef000002"]


@pytest.mark.parametrize("index", ["interrupted", "missing", "corrupt"])
def test_export_recovery_sweeps_abandoned_job_folders(tmp_path, index):
    svc, _ = make_service(tmp_path)
    manager = svc._export_manager()
    job_dir = os.path.join(manager.work_dir, "abcdef000001")
    orphan_dir = os.path.join(manager.work_dir, "abcdef000002")
    other_dir = os.path.join(manager.work_dir, "keep")
    for folder in (job_dir, orphan_dir, other_dir):
        os.makedirs(folder)
        with open(os.path.join(folder, "job.json"), "w") as f:
            f.write("{}")
    if index != "missing":
        with open(svc.index_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"exports": [{"id": "abcdef000001", "status": "rendering"}]})
                    if index == "interrupted" else "{broken")
    records = manager.list()
    if index == "interrupted":
        assert records[0]["status"] == "failed" and records[0]["error"] == INTERRUPTED
    else:
        assert records == []
    assert not os.path.exists(job_dir) and not os.path.exists(orphan_dir)
    assert os.path.isdir(other_dir)


def test_remove_a_finished_export(tmp_path):
    blocker = FakeRunner("block")
    svc, _ = make_service(tmp_path, runners=RunnerFactory(FakeRunner("ok"), blocker))
    done = _settled(svc, run(svc.start_export("countdown", {}, {}, quality="draft"))["id"])
    active = run(svc.start_export("countdown", {}, {}, quality="draft"))
    assert blocker.started.wait(5)
    with pytest.raises(ConflictError):
        run(svc.remove_export(active["id"]))
    run(svc.remove_export(done["id"]))
    assert not os.path.exists(os.path.join(svc.exports_dir, done["filename"]))
    assert done["id"] not in {e["id"] for e in run(svc.list_exports())}
    svc.shutdown_sync()


def test_manim_runner_arguments_and_failure_message():
    job = VideoJob(job_dir="j", job_file="j/job.json", media_dir="j/media", width=1280, height=720, fps=30,
                   format="webm", transparent=True, timeout=60)
    args = ManimVideoRunner.args(job)
    assert args[:4] == ["-r", "1280,720", "--fps", "30"]
    assert ["--format", "webm"] == args[args.index("--format"):args.index("--format") + 2]
    assert "--transparent" in args and "--disable_caching" in args
    mp4 = ManimVideoRunner.args(VideoJob("j", "f", "m", 2, 2, 15, "mp4", False, 1))
    assert "--format" not in mp4 and "--transparent" not in mp4
    lines = ["│ boxed ValueError line │", "ValueError: the headline is too long", "  more context"]
    assert ManimVideoRunner.failure_message(lines, {"exit_code": 1}) == "ValueError: the headline is too long"
    assert ManimVideoRunner.failure_message([], {"exit_code": 2}) == "Manim exited with code 2."


def test_manim_runner_drives_the_executor(tmp_path, monkeypatch):
    """The real runner, with ManimExecutor.execute faked: env, args, progress and output."""
    import executor

    seen = {}

    async def fake_execute(self, manim_path, script_name, scene_name, quality, use_opengl, log_callback, **kwargs):
        seen.update(script=script_name, scene=scene_name, kwargs=kwargs, cwd=self.workspace_dir,
                    timeout=self.render_timeout)
        await log_callback({"type": "progress", "percent": 40, "animation": 2})
        out = tmp_path / "media" / "videos" / "runner" / "720p30" / "StudioRender.mp4"
        out.parent.mkdir(parents=True)
        from tests.media_bytes import MP4
        out.write_bytes(MP4)
        await log_callback({"type": "file_ready", "abs_path": str(out)})
        return {"success": True, "status": "success"}

    monkeypatch.setattr(executor.ManimExecutor, "execute", fake_execute)
    progress = []
    job = VideoJob(str(tmp_path), str(tmp_path / "job.json"), str(tmp_path / "media"), 1280, 720, 30, "mp4",
                   False, 99)
    path = ManimVideoRunner().run(job, lambda a, p: progress.append((a, p)), lambda line: None)
    assert path.endswith("StudioRender.mp4") and progress == [(2, 40)]
    assert seen["script"].endswith(os.path.join("studio", "runner.py")) and seen["scene"] == "StudioRender"
    assert seen["kwargs"]["extra_env"] == {"COMPOSER_JOB": str(tmp_path / "job.json")}
    assert seen["kwargs"]["output_stem"] == "runner" and seen["cwd"] == str(tmp_path) and seen["timeout"] == 99


# --------------------------------------------------------------------------- #
# Projects
# --------------------------------------------------------------------------- #


def test_projects_crud(svc):
    assert run(svc.list_projects()) == []
    project = run(svc.create_project("countdown", {"seconds": 1}, {"theme": "pop"}, title="  Draft  "))
    assert project["title"] == "Draft" and project["params"] == {"seconds": 1}  # drafts may be invalid
    assert len(project["id"]) == 16 and project["created"] == project["updated"]
    assert project["poster_url"] is None
    path = os.path.join(svc.projects_dir, project["id"] + ".json")
    assert json.load(open(path, encoding="utf-8"))["template"] == "countdown"

    got = run(svc.get_project(project["id"]))
    assert got["params"] == {"seconds": 1}
    updated = run(svc.update_project(project["id"], params={"seconds": 30}))
    assert updated["params"] == {"seconds": 30} and updated["settings"] == {"theme": "pop"}
    assert updated["title"] == "Draft" and updated["updated"] >= project["updated"]
    assert run(svc.update_project(project["id"], title=None))["title"] == "Countdown timer"

    # A cached poster for the current content shows up in the list.
    assert run(svc.list_projects())[0]["poster_url"] is None
    poster = run(svc.preview("countdown", {"seconds": 30}, {"theme": "pop"}))
    listed = run(svc.list_projects())
    assert listed[0]["poster_url"] == poster["url"]
    assert set(listed[0]) >= {"id", "title", "template", "updated", "poster_url"}

    second = run(svc.create_project("countdown"))
    assert second["title"] == "Countdown timer" and second["params"] == {}
    assert [p["id"] for p in run(svc.list_projects())] == [second["id"], project["id"]]
    assert run(svc.delete_project(project["id"]))["id"] == project["id"]
    assert not os.path.exists(path)
    with pytest.raises(NotFoundError):
        run(svc.get_project(project["id"]))


def test_project_validation(svc):
    with pytest.raises(TemplateError) as info:
        run(svc.create_project("no_such"))
    assert _errors(info).keys() == {"template"}
    with pytest.raises(TemplateError):
        run(svc.create_project("countdown", params="nope"))
    with pytest.raises(TemplateError) as info:
        run(svc.create_project("countdown", {"notes": "x" * (300 * 1024)}))
    assert _errors(info).keys() == {"params"}
    with pytest.raises(TemplateError):
        run(svc.create_project("countdown", title="t" * 500))
    for bad in ("../../etc/passwd", "ABCDEF0123456789", "1234", None):
        with pytest.raises(NotFoundError):
            run(svc.get_project(bad))
    with pytest.raises(NotFoundError):
        run(svc.update_project("0123456789abcdef", title="x"))


def test_valid_project_params_are_stored_as_the_template_reads_them(svc):
    project = run(svc.create_project("countdown", {"seconds": "30"}))
    assert project["params"] == {"seconds": 30}  # only what was given, but in the template's types
    updated = run(svc.update_project(project["id"], params={"seconds": "45", "title": "Break"}))
    assert updated["params"] == {"seconds": 45, "title": "Break"}
    draft = run(svc.update_project(project["id"], params={"seconds": "soon"}))
    assert draft["params"] == {"seconds": "soon"}  # drafts that don't validate are kept as typed


def test_missing_aspect_uses_the_templates_default_format(svc):
    spec, _, settings = registry.validate_job("celebration", {}, {})
    assert settings.aspect == spec.meta.default_aspect == "9:16"
    assert registry.validate_job("celebration", {}, {"theme": "pop"})[2].aspect == "9:16"
    assert registry.validate_job("celebration", {}, {"aspect": "16:9"})[2].aspect == "16:9"


def test_agent_images_are_checked_and_named_by_content(svc):
    import base64

    png = tiny_png(4, 3)
    first = run(svc.add_image(base64.b64encode(png).decode()))
    assert first["name"].startswith("agent-") and first["name"].endswith(".png")
    assert (first["width"], first["height"]) == (4, 3)
    with open(os.path.join(svc.assets_dir, first["name"]), "rb") as f:
        assert f.read() == png
    again = run(svc.add_image("data:image/png;base64," + base64.b64encode(png).decode()))
    assert again["name"] == first["name"]
    svg = run(svc.add_image(base64.b64encode(b'<svg xmlns="http://www.w3.org/2000/svg"/>').decode()))
    assert svg["name"].endswith(".svg")
    for bad in ("not base64!", base64.b64encode(b"just text").decode(),
                base64.b64encode(b"<html><body/></html>").decode(), "", None):
        with pytest.raises(TemplateError) as info:
            run(svc.add_image(bad))
        assert _errors(info).keys() == {"data"}
    with pytest.raises(TemplateError):
        run(svc.add_image(b"\x89PNG" + b"0" * service_module.MAX_IMAGE_BYTES))


def test_corrupt_project_files_are_skipped(svc):
    os.makedirs(svc.projects_dir)
    with open(os.path.join(svc.projects_dir, "0123456789abcdef.json"), "w") as f:
        f.write("{broken")
    with open(os.path.join(svc.projects_dir, "notes.txt"), "w") as f:
        f.write("ignore me")
    assert run(svc.list_projects()) == []


# --------------------------------------------------------------------------- #
# Icons
# --------------------------------------------------------------------------- #


def test_icon_names_and_paths(svc):
    icons = svc.icons_dir
    for name in ("gift", "clock-2", "Bad Name", ".hidden"):
        with open(os.path.join(icons, name + ".svg"), "w") as f:
            f.write("<svg/>")
    assert run(svc.icon_names()) == ["clock-2", "gift"]
    assert svc.icon_path("gift").endswith("gift.svg")
    for bad in ("../gift", "Gift", "", "a" * 80, "gift.svg", ".hidden"):
        with pytest.raises(TemplateError):
            svc.icon_path(bad)
    with pytest.raises(NotFoundError):
        svc.icon_path("missing")


def test_missing_icons_folder(tmp_path):
    service = StudioService(str(tmp_path), icons_dir=str(tmp_path / "nope"), worker_factory=FakeWorker)
    assert run(service.icon_names()) == []
