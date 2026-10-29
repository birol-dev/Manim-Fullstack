"""Shipped gallery artwork must exactly match current preset requests."""
import os
from pathlib import Path
import shutil

from studio.bake_posters import BAKE_COMMAND, POSTERS_DIR, check_baked, preset_requests
from studio.service import StudioService
from studio.storage import tree_fingerprint
from tests.studio_fakes import FakeWorker


def test_every_catalog_preset_has_a_current_baked_poster(tmp_path):
    service = StudioService(str(tmp_path))
    problems = check_baked(service)
    assert not problems, f"Missing/stale preset posters: {', '.join(problems)}. Run `{BAKE_COMMAND}`."


def test_fresh_cache_seeds_all_presets_without_rendering(tmp_path):
    worker = FakeWorker()
    service = StudioService(str(tmp_path), worker_factory=lambda: worker)
    for card, settings in preset_requests(service):
        result = service.preview_sync(card["template"], card["params"], settings)
        assert result["cached"], f"Rebake with `{BAKE_COMMAND}`: {card['id']}"
        assert Path(result["path"]).read_bytes() == (POSTERS_DIR / Path(result["path"]).name).read_bytes()
    assert not worker.calls


def test_changed_content_ignores_bake(tmp_path):
    worker = FakeWorker()
    service = StudioService(str(tmp_path), worker_factory=lambda: worker)
    card, settings = next(preset_requests(service))
    result = service.preview_sync(card["template"], {**card["params"], "headline": "New content"}, settings)
    assert not result["cached"] and len(worker.calls) == 1


def test_fingerprints_survive_copy_and_timestamp_changes(tmp_path):
    source, target = tmp_path / "a" / "kit", tmp_path / "b" / "kit"
    source.mkdir(parents=True)
    (source / "scene.py").write_text("example", encoding="utf-8")
    target.parent.mkdir()
    shutil.copytree(source, target)
    os.utime(target / "scene.py", (1, 1))
    assert tree_fingerprint(str(source)) == tree_fingerprint(str(target))
    (source / "scene.py").write_bytes(b"example\n")
    (target / "scene.py").write_bytes(b"example\r\n")
    assert tree_fingerprint(str(source)) == tree_fingerprint(str(target))
