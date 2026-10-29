"""Offline peek bakes and read-only catalog lookup; no catalog renders in tests."""
import json
import importlib
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from studio import bake_peeks, peeks
from studio.bake_posters import BAKE_COMMAND, preset_requests
from studio.service import StudioService
from tests.media_bytes import MP4
from tests.studio_fakes import FakeMotionWorker, FakeWorker


def seed(service, folder):
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for card, settings in preset_requests(service):
        key = peeks.peek_key(service, card, settings)
        manifest[f'{card["template"]}/{card["id"]}'] = key
        (folder / f"{key}.mp4").write_bytes(MP4)
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def test_every_catalog_preset_has_a_current_baked_peek(tmp_path):
    problems = peeks.check_baked(StudioService(str(tmp_path)))
    assert not problems, f"Missing/stale preset peeks: {', '.join(problems)}. Run `{BAKE_COMMAND}`."


def test_shipped_peek_size_budgets():
    files = [p for p in peeks.PEEKS_DIR.rglob("*") if p.is_file()]
    assert all(p.stat().st_size <= peeks.MAX_FILE_BYTES for p in files if p.suffix == ".mp4")
    assert sum(p.stat().st_size for p in files) <= peeks.MAX_TOTAL_BYTES


def test_fake_bakes_cover_every_preset_and_detect_stale_missing_and_bad_manifest(tmp_path):
    service = StudioService(str(tmp_path / "work"))
    folder = tmp_path / "peeks"
    manifest = seed(service, folder)
    assert not peeks.check_baked(service, folder)
    name, key = next(iter(manifest.items()))
    manifest[name] = "wrong"
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert peeks.check_baked(service, folder) == [name]
    manifest[name] = key
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (folder / f"{key}.mp4").unlink()
    assert peeks.check_baked(service, folder) == [name]
    (folder / f"{key}.mp4").mkdir()
    assert peeks.check_baked(service, folder) == [name]
    (folder / f"{key}.mp4").rmdir()
    for invalid in ("[]", "broken", "null"):
        (folder / "manifest.json").write_text(invalid, encoding="utf-8")
        assert len(peeks.check_baked(service, folder)) == len(manifest)


def test_size_checks_include_unreferenced_movies_and_all_folder_contents(tmp_path, monkeypatch):
    service = StudioService(str(tmp_path / "work"))
    folder = tmp_path / "peeks"
    manifest = seed(service, folder)
    name, key = next(iter(manifest.items()))
    (folder / f"{key}.mp4").write_bytes(b"x" * (peeks.MAX_FILE_BYTES + 1))
    assert name in peeks.check_baked(service, folder)
    assert any("exceeds 300000" in p for p in peeks.check_baked(service, folder))
    monkeypatch.setattr(peeks, "MAX_TOTAL_BYTES", 100)
    assert any("peeks folder" in p for p in peeks.check_baked(service, folder))


def test_keys_track_all_preview_inputs_and_peek_version(tmp_path, monkeypatch):
    service = StudioService(str(tmp_path))
    card, settings = next(preset_requests(service))
    key = peeks.peek_key(service, card, settings)
    assert peeks.peek_key(service, card, {**settings, "theme": "midnight"}) != key
    assert peeks.peek_key(service, {**card, "params": {**card["params"], "headline": "Changed"}}, settings) != key
    for method in ("_refresh_template", "_kit_fingerprint", "_icons_fingerprint"):
        with monkeypatch.context() as patch:
            patch.setattr(service, method, lambda *args: "changed")
            assert peeks.peek_key(service, card, settings) != key
    monkeypatch.setattr(peeks, "VERSION", peeks.VERSION + 1)
    assert peeks.peek_key(service, card, settings) != key


def test_catalog_urls_are_current_and_never_start_workers(tmp_path, monkeypatch):
    folder = tmp_path / "peeks"
    monkeypatch.setattr(peeks, "PEEKS_DIR", folder)
    worker = FakeWorker()
    service = StudioService(str(tmp_path / "work"), worker_factory=lambda: worker,
                            motion_worker_factory=lambda: pytest.fail("Catalog must never start motion renders"))
    assert all(card["peek_url"] is None for template in service._catalog_sync()["templates"] for card in template["presets"])
    manifest = seed(service, folder)
    catalog = service._catalog_sync()  # cached schema must still pick up newly baked assets
    assert all(card["peek_url"] for section in catalog["sections"] for card in section["cards"])
    name, key = next(iter(manifest.items()))
    assert service.peek_path(key).read_bytes() == MP4
    (folder / f"{key}.mp4").unlink()
    card = next(c for t in service._catalog_sync()["templates"] for c in t["presets"] if f'{c["template"]}/{c["id"]}' == name)
    assert card["peek_url"] is None
    assert not worker.calls and service._motion is None


def test_clip_window_keeps_last_frame_and_caps_at_67_frames():
    assert bake_peeks.clip_window(2) == (0, 30)
    assert bake_peeks.clip_window(4.5) == (1, 67)
    assert bake_peeks.clip_window(20) == (233, 67)


def test_encode_retries_crf_and_sets_portable_silent_mp4_flags(tmp_path):
    destination = tmp_path / "peek.mp4"
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        destination.write_bytes(b"x" * (251_000 if len(calls) == 1 else 200_000))
        assert kwargs["check"]

    bake_peeks.encode(tmp_path / "source.mp4", destination, 20, 250_000, "poster.png", 480, 270, run=fake_run)
    assert len(calls) == 2
    command = calls[-1]
    for option, value in (("-c:v", "libx264"), ("-pix_fmt", "yuv420p"), ("-movflags", "+faststart"),
                          ("-r", "15"), ("-frames:v", "67"), ("-crf", "30")):
        assert command[command.index(option) + 1] == value
    assert "-an" in command
    filters = command[command.index("-filter_complex") + 1]
    assert "trim=start_frame=233:end_frame=300,setpts=PTS-STARTPTS" in filters
    assert "overlay=enable='eq(n,66)'" in filters and "scale=480:270" in filters


def test_encode_fails_closed_if_even_high_crf_exceeds_budget(tmp_path):
    destination = tmp_path / "peek.mp4"
    with pytest.raises(RuntimeError, match="Couldn't fit"):
        bake_peeks.encode("source", destination, 1, 100, "poster", 480, 270,
                          run=lambda *a, **k: destination.write_bytes(b"x" * 101))
    assert not destination.exists()


def test_bake_uses_motion_worker_with_exact_card_settings_and_prunes_old_files(tmp_path, monkeypatch):
    worker = FakeMotionWorker()
    service = StudioService(str(tmp_path / "work"), motion_worker_factory=lambda: worker, worker_factory=FakeWorker)
    folder = tmp_path / "peeks"
    folder.mkdir()
    (folder / "obsolete.mp4").write_bytes(MP4)
    monkeypatch.setattr(bake_peeks, "encode", lambda source, out, duration, budget, poster, w, h: out.write_bytes(MP4))
    requests = list(preset_requests(service))
    bake_peeks.bake(service, folder)
    assert not peeks.check_baked(service, folder)
    assert len(worker.calls) == len(requests)
    assert not (folder / "obsolete.mp4").exists()
    for call, (card, settings) in zip(worker.calls, requests):
        job = call["job"]
        assert job["mode"] == "motion" and job["peek"]
        assert job["template"] == card["template"]
        assert job["settings"]["aspect"] == settings["aspect"]
        assert max(call["width"], call["height"]) == 480
        assert call["width"] % 2 == call["height"] % 2 == 0
        _, params, validated, _ = service._validate(card["template"], card["params"], settings)
        assert job["params"] == params and job["settings"] == validated


def test_packaging_rejects_peeks_before_copying_or_building(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "desktop" / "scripts"))
    package = importlib.import_module("desktop.scripts.package")
    posters_module = importlib.import_module("backend.studio.bake_posters")
    peeks_module = importlib.import_module("backend.studio.peeks")
    monkeypatch.setattr(posters_module, "check_baked", lambda service: [])
    monkeypatch.setattr(peeks_module, "check_baked", lambda service: ["announcement/weekend-sale"])
    with pytest.raises(RuntimeError, match="Missing, stale or oversized gallery peeks") as caught:
        package.main()
    assert BAKE_COMMAND in str(caught.value)


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="FFmpeg/ffprobe are needed for the tiny encoding probe")
def test_tiny_motion_render_stops_at_poster_and_encodes_its_last_frame(tmp_path, monkeypatch):
    pytest.importorskip("manim")
    import numpy as np
    from PIL import Image
    from pydantic import BaseModel
    from manim import RIGHT, Square
    from studio.kit.scene import StudioScene
    from studio.worker import _Child

    class Params(BaseModel):
        pass

    class Tiny(StudioScene):
        META = SimpleNamespace(default_length=1)

        def build(self):
            square = Square(side_length=1, fill_opacity=1, color="#FFCC44")
            self.add(square)
            self.play(square.animate.shift(RIGHT), run_time=0.2)
            self.poster()
            raise AssertionError("A peek must stop at the poster marker")

    Tiny.Params = Params
    child = _Child(None)
    monkeypatch.setattr(child, "template_class", lambda _: Tiny)
    poster, source, out = [tmp_path / name for name in ("poster.png", "source.mp4", "peek.mp4")]
    job = {"template": "tiny", "params": {}, "settings": {"aspect": "16:9"}}
    request = {"id": 1, "width": 64, "height": 36, "media_dir": str(tmp_path / "media")}
    still = child.render({**request, "job": {**job, "mode": "poster", "output": str(poster)}})
    assert still["ok"], still
    result = child.render({**request, "job": {**job, "mode": "motion", "peek": True,
                                              "max_duration": 4.5, "output": str(source)}})
    assert result["ok"], result
    assert result["duration"] == pytest.approx(4 / 15, abs=0.01)
    bake_peeks.encode(source, out, result["duration"], 250_000, poster, 64, 36)
    decoded = subprocess.run(["ffmpeg", "-v", "error", "-i", str(out), "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                             capture_output=True, check=True, timeout=30)
    frames = np.frombuffer(decoded.stdout, dtype=np.uint8).reshape(-1, 36, 64, 3)
    assert len(frames) == 4
    expected = np.asarray(Image.open(poster).convert("RGB"))
    assert np.abs(frames[-1].astype(float) - expected.astype(float)).mean() < 5
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(out)],
                           capture_output=True, check=True, timeout=30)
    streams = json.loads(probe.stdout)["streams"]
    assert len(streams) == 1
    assert streams[0]["codec_name"] == "h264" and streams[0]["pix_fmt"] == "yuv420p"
    assert streams[0]["r_frame_rate"] == "15/1"
    assert out.read_bytes().index(b"moov") < out.read_bytes().index(b"mdat")
