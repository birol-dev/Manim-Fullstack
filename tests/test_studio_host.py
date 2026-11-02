"""Host actions for finished exports: argv per platform, timeline handling and the REST routes."""

import os
import subprocess

import pytest

import main
from studio import host as host_module
from studio import service as service_module
from studio.host import HostError, HostUnsupported
from tests.conftest import LocalClient
from tests.studio_fakes import make_service

EXPORT_ID = "abcdef000001"
PATH = "/exports/clip.mp4"

WINDOWS_COPY = ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                "-Command", "Set-Clipboard -LiteralPath $env:MANIM_STUDIO_CLIPBOARD_FILE"]


class Finished:
    returncode = 0
    stdout = ""
    stderr = ""


class Broken:
    returncode = 1
    stdout = ""
    stderr = "clipboard is busy"


# --------------------------------------------------------------------------- #
# Platform helpers
# --------------------------------------------------------------------------- #


def test_capabilities_per_platform():
    assert host_module.capabilities("Windows") == {"reveal": True, "copy_file": True}
    assert host_module.capabilities("Darwin") == {"reveal": True, "copy_file": True}
    assert host_module.capabilities("Linux") == {"reveal": True, "copy_file": False}
    assert host_module.capabilities("FreeBSD") == {"reveal": False, "copy_file": False}


def test_reveal_argv_per_platform():
    assert host_module.reveal_args(PATH, "Windows") == 'explorer /select,"/exports/clip.mp4"'
    assert host_module.reveal_args(PATH, "Darwin") == ["open", "-R", PATH]
    assert host_module.reveal_args(PATH, "Linux") == ["xdg-open", "/exports"]


def test_windows_reveal_quotes_only_the_path_in_one_command_line():
    spaced = r"C:\Users\Jane Doe\a.mp4"
    assert host_module.reveal_args(spaced, "Windows") == r'explorer /select,"C:\Users\Jane Doe\a.mp4"'
    assert host_module.reveal_args(PATH, "Windows") == 'explorer /select,"/exports/clip.mp4"'
    with pytest.raises(HostError):
        host_module.reveal_args('/exports/say "hi".mp4', "Windows")


def test_copy_argv_per_platform():
    assert host_module.copy_args(PATH, "Windows") == WINDOWS_COPY
    assert PATH not in " ".join(WINDOWS_COPY)  # the path never becomes command text
    script = host_module.copy_args('/exports/a "b" \\ c.mp4', "Darwin")[-1]
    assert script == 'set the clipboard to (POSIX file "/exports/a \\"b\\" \\\\ c.mp4")'
    with pytest.raises(HostUnsupported) as info:
        host_module.copy_args(PATH, "Linux")
    assert info.value.status == 501


# --------------------------------------------------------------------------- #
# Running the action
# --------------------------------------------------------------------------- #


@pytest.fixture
def run(monkeypatch):
    seen = []

    def fake(args, **kwargs):
        seen.append((args, kwargs))
        return Finished()

    monkeypatch.setattr(host_module.subprocess, "run", fake)
    return seen


def test_reveal_runs_the_platform_command_with_a_timeout_and_no_shell(run):
    host_module.reveal(PATH, "Windows")
    spaced = r"C:\Users\Jane Doe\a.mp4"
    host_module.reveal(spaced, "Windows")
    host_module.reveal(PATH, "Darwin")
    host_module.reveal(PATH, "Linux")
    assert [entry[0] for entry in run] == [
        'explorer /select,"/exports/clip.mp4"',
        r'explorer /select,"C:\Users\Jane Doe\a.mp4"',
        ["open", "-R", PATH],
        ["xdg-open", "/exports"],
    ]
    for _, kwargs in run:
        assert "shell" not in kwargs
        assert kwargs["timeout"] == host_module.TIMEOUT_SECONDS


def test_windows_reveal_refuses_a_path_with_a_quote(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("nothing should run")

    monkeypatch.setattr(host_module.subprocess, "run", explode)
    with pytest.raises(HostError) as info:
        host_module.reveal('/exports/say "hi".mp4', "Windows")
    assert "folder" in str(info.value)


def test_windows_reveal_ignores_explorers_exit_code(monkeypatch):
    monkeypatch.setattr(host_module.subprocess, "run", lambda args, **kwargs: Broken())
    host_module.reveal(PATH, "Windows")  # explorer exits with 1 even after opening the folder


def test_reveal_errors_become_friendly_messages(monkeypatch):
    monkeypatch.setattr(host_module.subprocess, "run", lambda args, **kwargs: Broken())
    with pytest.raises(HostError) as info:
        host_module.reveal(PATH, "Darwin")
    assert "file manager" in str(info.value)

    def timeout(args, **kwargs):
        raise subprocess.TimeoutExpired(args, 15)

    monkeypatch.setattr(host_module.subprocess, "run", timeout)
    with pytest.raises(HostError) as info:
        host_module.reveal(PATH, "Linux")
    assert "didn't respond" in str(info.value)

    def missing(args, **kwargs):
        raise FileNotFoundError(2, "no such file", "xdg-open")

    monkeypatch.setattr(host_module.subprocess, "run", missing)
    with pytest.raises(HostError) as info:
        host_module.reveal(PATH, "Linux")
    assert "couldn't start" in str(info.value)


def test_reveal_is_refused_on_an_unknown_platform(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("nothing should run")

    monkeypatch.setattr(host_module.subprocess, "run", explode)
    with pytest.raises(HostUnsupported) as info:
        host_module.reveal(PATH, "FreeBSD")
    assert info.value.status == 501


def test_windows_copy_hands_the_path_to_powershell_in_the_environment(run):
    host_module.copy_file('/exports/a "b" & more.mp4', "Windows")
    args, kwargs = run[0]
    assert args == WINDOWS_COPY
    assert "shell" not in kwargs
    assert kwargs["env"][host_module.COPY_ENV] == '/exports/a "b" & more.mp4'
    assert kwargs["timeout"] == host_module.TIMEOUT_SECONDS


def test_macos_copy_quotes_the_path_into_the_applescript(run):
    host_module.copy_file(PATH, "Darwin")
    args, _ = run[0]
    assert args == ["osascript", "-e", 'set the clipboard to (POSIX file "/exports/clip.mp4")']


def test_copy_failures_and_unsupported_platforms(monkeypatch):
    monkeypatch.setattr(host_module.subprocess, "run", lambda args, **kwargs: Broken())
    with pytest.raises(HostError) as info:
        host_module.copy_file(PATH, "Darwin")
    assert "clipboard" in str(info.value)

    with pytest.raises(HostUnsupported) as info:
        host_module.copy_file(PATH, "Linux")
    assert info.value.status == 501


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
def api(studio):
    return LocalClient(main.app, base_url="http://localhost")


def add_record(svc, *, status="done", filename="clip.mp4", write=True, export_id=EXPORT_ID):
    manager = svc._export_manager()
    manager._ensure_loaded()
    os.makedirs(svc.exports_dir, exist_ok=True)
    path = os.path.join(svc.exports_dir, filename) if filename else None
    if write and path is not None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"file bytes")
    with manager._lock:
        manager._records[export_id] = {"id": export_id, "status": status, "created": "1", "filename": filename}
    return path


def test_host_capabilities_route(api, monkeypatch):
    monkeypatch.setattr(host_module, "capabilities", lambda: {"reveal": True, "copy_file": False})
    res = api.get("/api/studio/host")
    assert res.status_code == 200 and res.json() == {"reveal": True, "copy_file": False}


@pytest.mark.parametrize("action, host_name", [("reveal", "reveal"), ("copy", "copy_file")])
def test_export_actions_call_the_host_with_the_recorded_path(api, studio, monkeypatch, action, host_name):
    path = add_record(studio)
    calls = []
    monkeypatch.setattr(host_module, host_name, lambda value: calls.append(value))
    res = api.post(f"/api/studio/exports/{EXPORT_ID}/{action}")
    assert res.status_code == 204 and res.content == b""
    assert calls == [path]


def test_unknown_export_answers_404(api, studio):
    assert api.post(f"/api/studio/exports/{EXPORT_ID}/reveal").status_code == 404
    assert api.post(f"/api/studio/exports/{EXPORT_ID}/copy").status_code == 404
    assert api.post("/api/studio/exports/nope/reveal").status_code == 404


@pytest.mark.parametrize("status", ["queued", "rendering", "failed", "cancelled"])
def test_an_export_that_is_not_done_answers_404(api, studio, monkeypatch, status):
    add_record(studio, status=status)
    calls = []
    monkeypatch.setattr(host_module, "reveal", lambda value: calls.append(value))
    monkeypatch.setattr(host_module, "copy_file", lambda value: calls.append(value))
    assert api.post(f"/api/studio/exports/{EXPORT_ID}/reveal").status_code == 404
    assert api.post(f"/api/studio/exports/{EXPORT_ID}/copy").status_code == 404
    assert calls == []


def test_a_missing_file_answers_404(api, studio, monkeypatch):
    add_record(studio, write=False)
    calls = []
    monkeypatch.setattr(host_module, "copy_file", lambda value: calls.append(value))
    assert api.post(f"/api/studio/exports/{EXPORT_ID}/copy").status_code == 404
    assert calls == []


@pytest.mark.parametrize("kind", ["relative", "absolute"])
def test_a_record_cannot_point_outside_the_exports_folder(api, studio, monkeypatch, tmp_path, kind):
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"not yours")
    os.makedirs(studio.exports_dir, exist_ok=True)
    filename = str(outside) if kind == "absolute" else os.path.relpath(outside, studio.exports_dir)
    add_record(studio, filename=filename, write=False)
    calls = []
    monkeypatch.setattr(host_module, "reveal", lambda value: calls.append(value))
    monkeypatch.setattr(host_module, "copy_file", lambda value: calls.append(value))
    assert api.post(f"/api/studio/exports/{EXPORT_ID}/reveal").status_code == 404
    assert api.post(f"/api/studio/exports/{EXPORT_ID}/copy").status_code == 404
    assert calls == []


def test_the_path_helper_resolves_a_real_file_inside_the_folder(studio):
    path = add_record(studio)
    assert os.path.realpath(studio._export_manager().export_file_path(EXPORT_ID)) == os.path.realpath(path)


@pytest.mark.parametrize("action, host_name", [("reveal", "reveal"), ("copy", "copy_file")])
def test_unsupported_platform_answers_501(api, studio, monkeypatch, action, host_name):
    add_record(studio)

    def unsupported(value):
        raise HostUnsupported("Not on this computer.")

    monkeypatch.setattr(host_module, host_name, unsupported)
    res = api.post(f"/api/studio/exports/{EXPORT_ID}/{action}")
    assert res.status_code == 501
    assert res.json()["detail"] == "Not on this computer."


def test_a_host_failure_answers_500(api, studio, monkeypatch):
    add_record(studio)

    def broken(value):
        raise HostError("The clipboard is busy.")

    monkeypatch.setattr(host_module, "copy_file", broken)
    res = api.post(f"/api/studio/exports/{EXPORT_ID}/copy")
    assert res.status_code == 500
    assert res.json()["detail"] == "The clipboard is busy."
