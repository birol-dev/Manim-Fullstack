"""Sound contract, synthesis, event timing, cache compatibility and real media probes."""
import asyncio
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

import numpy as np
import pytest
from pydantic import ValidationError

from studio.audio import mixed_chunks, pcm_bytes, read_pcm, synthesize
from studio.schema import RenderSettings
from studio.sound import EFFECTS, SAMPLE_RATE, SoundSettings, TRACKS
from studio.storage import visual_source, tree_fingerprint
from tests.studio_fakes import make_service


@pytest.mark.parametrize("name", EFFECTS)
def test_effects_deterministic_click_free_and_below_peak_ceiling(name):
    first = synthesize(name)
    synthesize.cache_clear()
    second = synthesize(name)
    assert pcm_bytes(first) == pcm_bytes(second)
    assert np.isfinite(first).all() and 0 < np.max(np.abs(first)) <= 10 ** (-16 / 20) + 1e-6
    assert abs(first[0]) < 1e-5 and abs(first[-1]) < 1e-5
    assert len(read_pcm(pcm_bytes(first))) == len(first)


@pytest.mark.parametrize("track", [t["id"] for t in TRACKS])
def test_original_loops_are_deterministic_and_have_quiet_boundaries(track):
    first = pcm_bytes(synthesize(track, music=True))
    synthesize.cache_clear()
    assert first == pcm_bytes(synthesize(track, music=True))
    samples = read_pcm(first)
    assert np.max(np.abs(samples)) <= .551
    assert abs(samples[0]) < 1e-5 and abs(samples[-1]) < 1e-5


def test_mix_loops_trims_fades_ducks_and_never_clips():
    music = np.full(SAMPLE_RATE, .5, np.float32)
    sound = SoundSettings(music={"track": "calm", "volume": 1, "fade_out": True})
    result = np.concatenate(list(mixed_chunks(3.25, sound, [], music)))
    assert len(result) == round(3.25 * SAMPLE_RATE)
    assert result[-1] == 0 and result[SAMPLE_RATE + 100] > 0
    sound.music.loop = False
    stopped = np.concatenate(list(mixed_chunks(3.25, sound, [], music)))
    assert np.all(stopped[SAMPLE_RATE:] == 0)
    sound.music.loop = True
    sound.music.fade_out = False
    ducked = np.concatenate(list(mixed_chunks(2, sound, [("finish", .5)], music)))
    assert abs(ducked[round(.49 * SAMPLE_RATE)]) < .16  # duck attack before effect
    crowded = np.concatenate(list(mixed_chunks(2, sound, [("finish", .5)] * 30, music)))
    assert np.isfinite(crowded).all() and np.max(np.abs(crowded)) <= .89001


@pytest.mark.parametrize("sound", [
    {"effects_volume": -1}, {"effects_volume": float("nan")}, {"effects_volume": float("inf")},
    {"music": {"volume": 1.1}}, {"music": {"track": "unknown"}},
    {"music": {"asset": "../song.wav"}}, {"music": {"url": "https://example.com/audio.mp3"}},
    {"music": {"asset": "audio-" + "a" * 32 + ".wav", "track": "calm"}},
])
def test_settings_refuse_invalid_levels_paths_and_ambiguous_sources(sound):
    with pytest.raises(ValidationError):
        RenderSettings(sound=sound)


def test_default_effects_and_shared_catalog_schema(tmp_path):
    service, _ = make_service(tmp_path)
    assert RenderSettings().sound.effects
    catalog = asyncio.run(service.catalog())
    assert len(catalog["music_tracks"]) == 3
    assert "sound" in catalog["settings_schema"]["properties"]


def test_audio_never_changes_visual_keys_but_changes_motion(tmp_path):
    service, _ = make_service(tmp_path)
    spec, params, settings, _ = service._validate("countdown", {"seconds": 10}, {})
    changed = {**settings, "sound": {"effects": False, "music": {"track": "calm", "volume": 1}}}
    for mode in ("poster", "storyboard", "peek-v1-15-4.5-250000"):
        assert service._preview_key(spec, params, settings, mode, 360) == service._preview_key(spec, params, changed, mode, 360)
    assert service._preview_key(spec, params, settings, "motion-15-20", 720) != service._preview_key(spec, params, changed, "motion-15-20", 720)


def test_original_29_gallery_bakes_remain_current_with_sound(tmp_path):
    from studio.bake_posters import check_baked, preset_requests
    from studio import peeks
    original_templates = {"announcement", "celebration", "countdown", "quiz", "quote", "year_in_review"}
    from studio.service import StudioService
    from tests.studio_fakes import FakeWorker
    worker = FakeWorker()
    service = StudioService(str(tmp_path), worker_factory=lambda: worker)
    assert not [name for name in check_baked(service) if name.split("/")[0] in original_templates]
    assert not [name for name in peeks.check_baked(service) if name.split("/")[0] in original_templates]
    count = 0
    for card, settings in preset_requests(service):
        if card["template"] not in original_templates:
            continue
        result = service.preview_sync(card["template"], card["params"], {**settings, "sound": {"music": {"track": "playful"}}})
        assert result["cached"], card["id"]
        count += 1
    assert count == 29 and not worker.calls


def test_http_and_mcp_allow_the_same_bounded_base64_audio_request():
    from main import RequestBodyLimitMiddleware as Limits
    for path in ("/api/studio/audio", "/mcp", "/mcp/"):
        assert Limits.limit_for(path)[0] >= 4 * 50 * 1024 * 1024 / 3 + 1024
        assert Limits.limit_for(path)[0] <= 70 * 1024 * 1024


def test_sound_source_markers_preserve_visual_hash_but_runtime_tracks_them(tmp_path):
    path = tmp_path / "scene.py"
    baseline = b"before\nafter\n"
    path.write_bytes(b"before\n    self.cue('finish')  # studio-audio\n# studio-audio-begin\nanything\n# studio-audio-end\nafter\n")
    assert visual_source(path.read_bytes()) == baseline
    visual = tree_fingerprint(str(path), visual_only=True)
    runtime = tree_fingerprint(str(path))
    path.write_bytes(path.read_bytes().replace(b"finish", b"correct"))
    assert tree_fingerprint(str(path), visual_only=True) == visual
    assert tree_fingerprint(str(path)) != runtime
    path.write_bytes(path.read_bytes().replace(b"before", b"visual change"))
    assert tree_fingerprint(str(path), visual_only=True) != visual
    with pytest.raises(ValueError):
        visual_source(b"# studio-audio-begin\n")


def capture_cues(template, params, tmp_path, settings=None):
    pytest.importorskip("manim")
    import importlib
    from manim import tempconfig
    from studio.kit import runtime
    cls = importlib.import_module(f"studio.templates.{template}.scene").Template
    runtime.set_job({"mode": "video", "params": params, "settings": settings or {}})
    try:
        with tempconfig({"dry_run": True, "media_dir": str(tmp_path), "verbosity": "ERROR", "progress_bar": "none",
                         "pixel_width": 192, "pixel_height": 108, "frame_width": 14.222222, "frame_height": 8, "frame_rate": 30}):
            scene = cls()
            scene.render()
            return scene._sound_cues
    finally:
        runtime.set_job(None)


@pytest.mark.parametrize("seconds,style,start", [(10, "ring", 5.6), (300, "ring", 295.6), (10, "big", 7)])
def test_countdown_cues_use_real_final_seconds_not_the_whole_timer(seconds, style, start, tmp_path):
    cues = capture_cues("countdown", {"seconds": seconds, "style": style, "title": "", "confetti": False}, tmp_path)
    ticks = [at for name, at in cues if name == "tick_final"]
    assert ticks == pytest.approx([start + i for i in range(3 if style == "big" else 5)], abs=.04)
    assert [name for name, _ in cues].count("finish") == 1
    assert cues[-1][1] > ticks[-1] + 1


def test_quiz_has_three_ticks_and_one_answer_chime(tmp_path):
    cues = capture_cues("quiz", {"think_seconds": 8}, tmp_path)
    assert [name for name, _ in cues] == ["tick", "tick", "tick", "correct"]
    assert np.diff([at for _, at in cues]) == pytest.approx([1, 1, 1], abs=.04)


@pytest.mark.parametrize("template,effect", [("announcement", "whoosh"), ("quote", "whoosh"), ("celebration", "sparkle")])
def test_message_templates_have_only_one_entrance_cue(template, effect, tmp_path):
    cues = capture_cues(template, {}, tmp_path)
    assert [name for name, _ in cues] == [effect]


def test_year_review_counts_settle_without_a_sound_on_every_frame(tmp_path):
    cues = capture_cues("year_in_review", {"style": "grid"}, tmp_path)
    assert [name for name, _ in cues] == ["pop", "tick", "tick", "tick", "tick"]


def test_effects_can_be_disabled(tmp_path):
    assert capture_cues("countdown", {"seconds": 10}, tmp_path, {"sound": {"effects": False}}) == []


@pytest.mark.parametrize("mode,peek", [("poster", False), ("storyboard", False), ("motion", True)])
def test_visual_only_modes_never_schedule_audio(mode, peek):
    from types import SimpleNamespace
    from studio.audio_render import record_cue
    scene = SimpleNamespace(mode=mode, is_peek=peek, s=RenderSettings(), elapsed=0, _sound_cues=[])
    record_cue(scene, "finish")
    assert scene._sound_cues == []


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="Source codec fixtures use the existing FFmpeg")
@pytest.mark.parametrize("extension,codec", [("mp3", "libmp3lame"), ("m4a", "aac"), ("aac", "aac"), ("ogg", "libvorbis"), ("wav", "pcm_s16le")])
def test_upload_decodes_each_supported_format(extension, codec, tmp_path):
    source = tmp_path / f"source.{extension}"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", "pipe:0", "-c:a", codec, str(source)],
                   input=pcm_bytes(synthesize("finish")), check=True, capture_output=True, timeout=20)
    service, _ = make_service(tmp_path)
    result = asyncio.run(service.upload_audio(source.read_bytes(), source.name))
    normalized = read_pcm(Path(service.audio_path(result["name"])).read_bytes())
    assert .7 < result["duration"] < 1.1
    assert np.max(np.abs(normalized)) <= .701


def test_upload_size_cap_and_missing_music_are_actionable(tmp_path, monkeypatch):
    import studio.service as module
    from studio.registry import TemplateError
    service, _ = make_service(tmp_path)
    monkeypatch.setattr(module, "MAX_AUDIO_BYTES", 4)
    with pytest.raises(TemplateError, match="50 MB"):
        asyncio.run(service.upload_audio(b"12345"))
    with pytest.raises(TemplateError, match="missing"):
        service.start_export_sync("quiz", settings={"sound": {"music": {"asset": "audio-" + "a" * 32 + ".wav"}}})


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="Manim 0.18 renderer needs its existing media tools")
@pytest.mark.parametrize("format,codec", [("mp4", "aac"), ("webm", "opus"), ("mov", "pcm_s16le"), ("gif", None)])
def test_tiny_real_writer_outputs_audio_in_each_video_container(format, codec, tmp_path):
    from types import SimpleNamespace
    from pydantic import BaseModel
    from manim import Square, tempconfig
    from studio.kit import runtime
    from studio.kit.scene import StudioScene
    class Empty(BaseModel):
        pass
    class Tiny(StudioScene):
        Params = Empty
        META = SimpleNamespace(default_length=.6)
        def build(self):
            square = Square(side_length=1, fill_opacity=1)
            self.add(square)
            self.cue("finish")
            self.play(square.animate.scale(.8), run_time=.2)
    runtime.set_job({"mode": "video", "settings": {"sound": {"music": {"track": "calm"}}}})
    try:
        with tempconfig({"format": format, "write_to_movie": True, "save_last_frame": False,
                         "movie_file_extension": ".mp4" if format == "gif" else f".{format}",
                         "pixel_width": 64, "pixel_height": 36, "frame_rate": 15, "frame_width": 14.222222,
                         "frame_height": 8, "media_dir": str(tmp_path), "output_file": "sound-probe",
                         "disable_caching": True, "verbosity": "ERROR", "progress_bar": "none"}):
            scene = Tiny()
            scene.render()
            writer = scene.renderer.file_writer
            path = writer.gif_file_path if format == "gif" else writer.movie_file_path
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)],
                               check=True, capture_output=True, timeout=20)
        audio = [s for s in json.loads(probe.stdout)["streams"] if s["codec_type"] == "audio"]
        assert (audio[0]["codec_name"] if audio else None) == codec
        if audio:
            assert abs(float(audio[0].get("duration", .6)) - .6) < .1
            decoded = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-f", "f32le", "-ac", "1", "pipe:1"],
                                     check=True, capture_output=True, timeout=20)
            samples = np.frombuffer(decoded.stdout, dtype="<f4")
            assert .001 < np.max(np.abs(samples)) < 1
    finally:
        runtime.set_job(None)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="0.18 upload fallback needs its existing FFmpeg")
def test_http_mcp_upload_and_settings_parity(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from studio import api
    from studio.mcp_server import RestBridge, create_server
    from tests.test_studio_mcp import payload
    import httpx
    service, _ = make_service(tmp_path)
    original = api.service_module.service
    api.service_module.service = service
    app = FastAPI()
    app.include_router(api.router)
    data = pcm_bytes(synthesize("finish"))
    try:
        with TestClient(app) as client:
            uploaded = client.post("/api/studio/audio", files={"file": ("my music.wav", data, "audio/wav")})
            assert uploaded.status_code == 201, uploaded.text
            result = uploaded.json()
            assert client.get(result["url"]).content.startswith(b"RIFF")
            assert client.post("/api/studio/audio", json={"data": "invalid"}).status_code == 422
            assert client.get("/api/studio/sounds/music/calm.wav").content.startswith(b"RIFF")
            assert client.get("/api/studio/sounds/music/unknown.wav").status_code == 404
        server = create_server(service)
        added = payload(asyncio.run(server.call_tool("upload_audio", {"data_base64": base64.b64encode(data).decode(), "filename": "chime.wav"})))
        assert added["name"] == result["name"]
        tracks_result = asyncio.run(server.call_tool("list_music_tracks", {}))
        assert not tracks_result.is_error
        assert len([c for c in tracks_result.content if c.type == "text"]) == 3
        info = payload(asyncio.run(server.call_tool("get_template", {"template": "quiz"})))
        assert "sound" in info["settings_schema"]["properties"]
        settings = {"sound": {"music": {"asset": added["name"]}}}
        project = payload(asyncio.run(server.call_tool("create_project", {"template": "quiz", "settings": settings})))
        assert asyncio.run(service.get_project(project["id"]))["settings"] == settings
        async def bridge_scenario():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as http:
                bridge = RestBridge(http)
                assert (await bridge.upload_audio(base64.b64encode(data).decode()))["name"] == added["name"]
                assert len(await bridge.list_music_tracks()) == 3
        asyncio.run(bridge_scenario())
    finally:
        api.service_module.service = original
        service.shutdown_sync()


@pytest.mark.skipif(os.environ.get("STUDIO_AUDIO_REAL_TESTS") != "1", reason="Set STUDIO_AUDIO_REAL_TESTS=1 for actual export probes")
@pytest.mark.parametrize("format", ["mp4", "gif"])
def test_real_export_audio_streams(format, tmp_path):
    from studio.service import StudioService
    service = StudioService(str(tmp_path), export_timeout=120)
    try:
        job = asyncio.run(service.start_export("countdown", {"seconds": 3, "style": "big", "title": ""},
                                               {"sound": {"music": {"track": "calm"}}}, format=format, quality="draft"))
        deadline = time.monotonic() + 150
        while job["status"] in ("queued", "rendering") and time.monotonic() < deadline:
            time.sleep(.2)
            job = asyncio.run(service.get_export(job["id"]))
        assert job["status"] == "done", job
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(Path(service.exports_dir) / job["filename"])],
                               check=True, capture_output=True, timeout=20)
        streams = json.loads(probe.stdout)["streams"]
        audio = [stream for stream in streams if stream["codec_type"] == "audio"]
        assert (audio[0]["codec_name"] if audio else None) == ("aac" if format == "mp4" else None)
    finally:
        service.shutdown_sync()
