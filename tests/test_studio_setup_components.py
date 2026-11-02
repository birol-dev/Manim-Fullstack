"""What the app needs: detection, pinned installs, PATH, and the setup routes."""

import hashlib
import io
import os
import threading
import zipfile

import pytest
from fastapi.responses import JSONResponse

import main
from studio import api as api_module
from studio import service as service_module
from studio import setup_components
from studio.setup_components import ComponentsError, ComponentManager, UnknownComponent
from studio.setup_mcp import McpSetup
from tests.conftest import LocalClient
from tests.studio_fakes import make_service, wait_until

CONNECTION = {"stdio": {"command": "C:/Manim/python.exe", "args": ["-B", "C:/Manim/mcp_server.py"]},
              "url": "http://127.0.0.1:8000/mcp/", "token": None}


def make_manager(tmp_path, *, platform="windows", mode="desktop", manim="0.18.1", webview2="120.0.2210.144",
                 which=None, pins=None, downloader=None):
    return ComponentManager(
        str(tmp_path / "ws"), platform=platform, mode=mode, env={}, environ={},
        which=which or (lambda _name: None), pins=pins, downloader=downloader,
        manim_probe=lambda: manim, webview2_probe=lambda: webview2)


def zip_bytes(files: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for name, data in files.items():
            bundle.writestr(name, data)
    return buffer.getvalue()


def pin_for(payload: bytes, root="tool", url="https://example.invalid/tool.zip"):
    return {"url": url, "sha256": hashlib.sha256(payload).hexdigest(), "root": root}


def downloader_for(payload: bytes, gate=None):
    def download(url, path, progress):
        if gate is not None:
            gate.wait(5)
        with open(path, "wb") as target:
            target.write(payload)
        progress(1.0)

    return download


def components_by_id(manager):
    return {item["id"]: item for item in manager.components()}


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #


def test_windows_reports_webview2_and_the_renderer(tmp_path):
    items = components_by_id(make_manager(tmp_path))
    assert list(items) == ["webview2", "renderer", "ffmpeg", "latex"]
    assert items["webview2"]["status"] == "ready" and items["webview2"]["required"] is True
    assert items["renderer"]["status"] == "ready" and items["renderer"]["required"] is True
    assert "0.18.1" in items["renderer"]["detail"]
    assert items["ffmpeg"]["status"] == "optional" and items["ffmpeg"]["required"] is False
    assert items["latex"]["status"] == "optional"


def test_a_missing_renderer_is_required_and_not_installable_here(tmp_path):
    items = components_by_id(make_manager(tmp_path, manim=None))
    assert items["renderer"]["status"] == "missing"
    assert items["renderer"]["can_install"] is False
    assert "installer" in items["renderer"]["detail"]


def test_macos_and_linux_name_the_exact_command(tmp_path):
    mac = components_by_id(make_manager(tmp_path, platform="macos"))
    assert "webview2" not in mac
    assert "brew install ffmpeg" in mac["ffmpeg"]["detail"]
    assert "brew install --cask basictex" in mac["latex"]["detail"]
    assert mac["ffmpeg"]["can_install"] is False

    linux = components_by_id(make_manager(tmp_path, platform="linux"))
    assert "sudo apt install ffmpeg" in linux["ffmpeg"]["detail"]
    assert "sudo apt install texlive-latex-recommended" in linux["latex"]["detail"]
    assert linux["latex"]["can_install"] is False


def test_source_mode_does_not_require_webview2(tmp_path):
    assert components_by_id(make_manager(tmp_path, mode="source"))["webview2"]["required"] is False


def test_tools_in_the_workspace_are_found(tmp_path):
    manager = make_manager(tmp_path)
    ffmpeg = tmp_path / "ws" / "studio" / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
    latex = tmp_path / "ws" / "studio" / "tools" / "latex" / "bin" / "windows" / "latex.exe"
    ffmpeg.parent.mkdir(parents=True)
    latex.parent.mkdir(parents=True)
    ffmpeg.write_bytes(b"ffmpeg")
    latex.write_bytes(b"latex")

    items = components_by_id(manager)
    assert items["ffmpeg"]["status"] == "ready"
    assert items["latex"]["status"] == "ready"
    assert items["ffmpeg"]["can_install"] is False


def test_path_finds_a_tool_on_the_path(tmp_path):
    manager = make_manager(tmp_path, which=lambda name: f"/usr/bin/{name}" if name == "ffmpeg" else None)
    assert components_by_id(manager)["ffmpeg"]["status"] == "ready"


def test_detection_is_cached_for_a_few_seconds(tmp_path):
    calls = []

    def probe():
        calls.append(1)
        return "0.18.1"

    manager = ComponentManager(str(tmp_path / "ws"), platform="linux", mode="source", env={},
                               which=lambda _name: None, manim_probe=probe, webview2_probe=lambda: None)
    manager.components()
    manager.components()
    assert len(calls) == 1
    manager.invalidate()
    manager.components()
    assert len(calls) == 2


# --------------------------------------------------------------------------- #
# Installs
# --------------------------------------------------------------------------- #


def test_a_verified_install_lands_in_the_tools_folder(tmp_path):
    payload = zip_bytes({"tool/bin/ffmpeg.exe": b"MZ-fake"})
    gate = threading.Event()
    manager = make_manager(tmp_path, pins={"ffmpeg": pin_for(payload)},
                           downloader=downloader_for(payload, gate))
    started = manager.install("ffmpeg")
    assert started["status"] == "installing"

    gate.set()
    wait_until(lambda: components_by_id(manager)["ffmpeg"]["status"] == "ready")
    installed = tmp_path / "ws" / "studio" / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
    assert installed.read_bytes() == b"MZ-fake"
    leftovers = [name for name in os.listdir(tmp_path / "ws" / "studio" / "tools") if name.startswith(".")]
    assert leftovers == []


def test_a_bad_digest_fails_without_installing(tmp_path):
    payload = zip_bytes({"tool/bin/ffmpeg.exe": b"MZ-fake"})
    pin = {"url": "https://example.invalid/tool.zip", "sha256": "0" * 64, "root": "tool"}
    manager = make_manager(tmp_path, pins={"ffmpeg": pin}, downloader=downloader_for(payload))
    manager.install("ffmpeg")

    item = wait_until(lambda: (lambda entry: entry if entry["status"] == "failed" else None)(
        components_by_id(manager)["ffmpeg"]))
    assert "damaged" in item["detail"]
    assert not (tmp_path / "ws" / "studio" / "tools" / "ffmpeg").exists()
    assert [name for name in os.listdir(tmp_path / "ws" / "studio" / "tools") if name.startswith(".")] == []


def test_zip_slip_is_refused(tmp_path):
    payload = zip_bytes({"../escaped.txt": b"nope", "tool/bin/ffmpeg.exe": b"MZ"})
    manager = make_manager(tmp_path, pins={"ffmpeg": pin_for(payload)}, downloader=downloader_for(payload))
    manager.install("ffmpeg")

    item = wait_until(lambda: (lambda entry: entry if entry["status"] == "failed" else None)(
        components_by_id(manager)["ffmpeg"]))
    assert "unsafe" in item["detail"]
    assert not (tmp_path / "ws" / "studio" / "escaped.txt").exists()
    assert not (tmp_path / "ws" / "studio" / "tools" / "ffmpeg").exists()


def test_only_one_install_runs_per_component(tmp_path):
    payload = zip_bytes({"tool/bin/ffmpeg.exe": b"MZ"})
    gate = threading.Event()
    calls = []

    def download(url, path, progress):
        calls.append(1)
        gate.wait(5)
        with open(path, "wb") as target:
            target.write(payload)
        progress(1.0)

    manager = make_manager(tmp_path, pins={"ffmpeg": pin_for(payload)}, downloader=download)
    first = manager.install("ffmpeg")
    wait_until(lambda: len(calls) == 1)
    second = manager.install("ffmpeg")
    assert first["status"] == second["status"] == "installing"
    assert len(calls) == 1
    gate.set()
    wait_until(lambda: components_by_id(manager)["ffmpeg"]["status"] == "ready")
    assert len(calls) == 1


def test_install_refuses_what_it_cannot_fetch(tmp_path):
    manager = make_manager(tmp_path)
    with pytest.raises(UnknownComponent):
        manager.install("printer")
    with pytest.raises(ComponentsError):
        manager.install("renderer")
    with pytest.raises(ComponentsError) as info:
        make_manager(tmp_path, platform="linux").install("ffmpeg")
    assert "sudo apt install ffmpeg" in str(info.value)


def test_tools_folders_are_added_to_path_once(tmp_path):
    tools = tmp_path / "tools"
    (tools / "ffmpeg" / "bin").mkdir(parents=True)
    (tools / "latex" / "bin" / "windows").mkdir(parents=True)
    env = {"PATH": os.pathsep.join(["C:/Windows", "C:/Other"])}

    added = setup_components.add_tools_to_path(str(tools), env)
    assert added == [str(tools / "ffmpeg" / "bin"), str(tools / "latex" / "bin" / "windows")]
    assert env["PATH"].split(os.pathsep)[:2] == added
    assert setup_components.add_tools_to_path(str(tools), env) == []
    assert env["PATH"].split(os.pathsep).count(added[0]) == 1


def test_reveal_uses_the_platform_command(monkeypatch, tmp_path):
    seen = []

    class Result:
        returncode = 0

    monkeypatch.setattr(setup_components.host, "_execute", lambda args: seen.append(args) or Result())
    setup_components.reveal_folder(str(tmp_path), "windows")
    setup_components.reveal_folder(str(tmp_path), "macos")
    setup_components.reveal_folder(str(tmp_path), "linux")
    assert seen == [["explorer", str(tmp_path)], ["open", str(tmp_path)], ["xdg-open", str(tmp_path)]]


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #


@pytest.fixture
def studio(tmp_path, monkeypatch):
    svc, _ = make_service(tmp_path)
    monkeypatch.setattr(service_module, "service", svc)
    yield svc
    svc.shutdown_sync()


@pytest.fixture
def manager(tmp_path):
    return ComponentManager(str(tmp_path / "ws"), platform="windows", mode="desktop", env={}, environ={},
                            which=lambda _name: None, manim_probe=lambda: "0.18.1",
                            webview2_probe=lambda: "120.0.2210.144")


@pytest.fixture
def api(studio, manager, tmp_path, monkeypatch):
    async def connection(_request):
        return JSONResponse(CONNECTION)

    monkeypatch.setattr(main, "studio_connection", connection)
    monkeypatch.setattr(api_module, "get_setup_components", lambda: manager)
    monkeypatch.setattr(api_module, "get_setup_mcp", lambda: McpSetup(
        home=str(tmp_path), appdata=str(tmp_path / "appdata"), localappdata=str(tmp_path / "localappdata"),
        platform="windows", which=lambda _name: None))
    return LocalClient(main.app, base_url="http://localhost")


def test_status_route_reports_components_apps_and_folder(api, studio):
    body = api.get("/api/studio/setup/status").json()
    assert body["platform"] == "windows" and body["mode"] == "desktop"
    assert {item["id"] for item in body["components"]} == {"webview2", "renderer", "ffmpeg", "latex"}
    assert {item["id"] for item in body["ai_apps"]} == {
        "claude-desktop", "claude-code", "cursor", "vscode", "windsurf", "codex", "gemini-cli"}
    assert body["data_folder"] == studio.workspace_dir


def test_install_route_answers_202_and_progress_shows_in_status(api, manager, tmp_path):
    payload = zip_bytes({"tool/bin/ffmpeg.exe": b"MZ"})
    gate = threading.Event()
    manager.pins = {"ffmpeg": pin_for(payload)}
    manager._download = downloader_for(payload, gate)

    started = api.post("/api/studio/setup/components/ffmpeg/install")
    assert started.status_code == 202
    assert started.json()["status"] == "installing"
    during = next(item for item in api.get("/api/studio/setup/status").json()["components"]
                  if item["id"] == "ffmpeg")
    assert during["status"] == "installing" and isinstance(during["progress"], int)

    gate.set()
    wait_until(lambda: next(item for item in api.get("/api/studio/setup/status").json()["components"]
                            if item["id"] == "ffmpeg")["status"] == "ready")
    installed = tmp_path / "ws" / "studio" / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
    assert installed.read_bytes() == b"MZ"


def test_install_route_refuses_unknown_or_bundled_components(api):
    assert api.post("/api/studio/setup/components/printer/install").status_code == 404
    assert api.post("/api/studio/setup/components/renderer/install").status_code == 409


def test_reveal_route_opens_the_workspace_folder(api, studio, monkeypatch):
    seen = []
    monkeypatch.setattr(setup_components, "reveal_folder", lambda path: seen.append(path))
    assert api.post("/api/studio/setup/reveal-data-folder").status_code == 204
    assert seen == [studio.workspace_dir]
