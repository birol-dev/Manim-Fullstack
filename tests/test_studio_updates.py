"""Update checks, downloads and installs: version rules, safety, and the routes.

Every check and download uses a fake HTTP opener, so nothing here touches the
network and a failed run is a state, never a dialog.
"""

import hashlib
import json
import logging
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

import pytest

import main
from studio import api as api_module
from studio import service as service_module
from studio import updates
from studio.preferences import PreferenceStore
from studio.registry import TemplateError
from studio.updates import (INSTALLER_NAME, MAX_INSTALLER_BYTES, UpdateBusy, UpdateError,
                            UpdateManager, is_newer, plain_notes, version_numbers)
from studio.version import APP_VERSION
from tests.conftest import LocalClient
from tests.studio_fakes import make_service

ROOT = Path(__file__).resolve().parents[1]
INSTALLER_URL = f"https://github.com/birol-dev/Manim-Fullstack/releases/download/v1.4.0/{INSTALLER_NAME}"
DIGEST_URL = INSTALLER_URL + ".sha256"


class Reply:
    """One response the fake opener returns; read() moves forward like a socket."""

    def __init__(self, body=b"", *, status=200, headers=None, url=None):
        self.body = body
        self.status = status
        self.headers = headers or {}
        self.url = url
        self.offset = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, amount=None):
        amount = len(self.body) - self.offset if amount is None else amount
        chunk = self.body[self.offset:self.offset + amount]
        self.offset += len(chunk)
        return chunk

    def geturl(self):
        return self.url


class FakeHTTP:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        item = self.replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def asset(name, url, size=3):
    return {"name": name, "browser_download_url": url, "size": size}


def release(tag="v1.4.0", *, prerelease=False, draft=False, body="## What's new\n\n- Faster exports\n",
            assets=None):
    if assets is None:
        assets = [asset(INSTALLER_NAME, INSTALLER_URL), asset(INSTALLER_NAME + ".sha256", DIGEST_URL)]
    return {"tag_name": tag, "name": tag, "prerelease": prerelease, "draft": draft,
            "body": body, "assets": assets}


def release_reply(**kwargs):
    return Reply(json.dumps(release(**kwargs)).encode("utf-8"))


def digest_reply(payload: bytes, *, digest=None):
    text = (digest or hashlib.sha256(payload).hexdigest()) + "  " + INSTALLER_NAME + "\n"
    return Reply(text.encode("utf-8"))


def installer_reply(payload: bytes, *, url=None, content_length=None):
    return Reply(payload, headers={"Content-Length": str(len(payload) if content_length is None else content_length)},
                 url=url)


def install_site(tmp_path):
    """A fake installed copy: both markers live in the folder the installer uses."""
    root = tmp_path / "Programs" / "ManimStudio"
    root.mkdir(parents=True, exist_ok=True)
    (root / updates.APP_EXE_NAME).write_bytes(b"app")
    (root / updates.UNINSTALLER_NAME).write_bytes(b"uninstaller")
    return root


def make_manager(tmp_path, *replies, **kwargs):
    spawned = []
    root = install_site(tmp_path)
    kwargs.setdefault("spawn", lambda command, **options: spawned.append((command, options)))
    kwargs.setdefault("running_exe", str(root / updates.APP_EXE_NAME))
    kwargs.setdefault("install_folder", str(root))
    kwargs.setdefault("signature_probe", lambda _path: None)
    kwargs.setdefault("shell_pid", 4242)
    http = FakeHTTP(*replies)
    manager = UpdateManager(str(tmp_path / "ws"), platform="windows", mode="desktop",
                            app_version="1.3.0", opener=http, data_dir=str(tmp_path), **kwargs)
    return manager, http, spawned


def ready_manager(tmp_path, payload=b"fake installer"):
    manager, http, spawned = make_manager(
        tmp_path, release_reply(), digest_reply(payload), installer_reply(payload))
    manager.check()
    assert manager.wait()["state"] == "available"
    manager.download()
    assert manager.wait()["state"] == "ready"
    return manager, http, spawned


# --------------------------------------------------------------------------- #
# Version rules and plain notes
# --------------------------------------------------------------------------- #


def test_numeric_versions_compare_and_never_go_backwards():
    assert is_newer("1.3.1", "1.3.0")
    assert is_newer("v2.0.0", "1.9.9")
    assert is_newer("1.10", "1.9.9")
    assert not is_newer("1.3", "1.3.0")
    assert not is_newer("1.2.9", "1.3.0")
    assert not is_newer("", "1.3.0")
    assert version_numbers("v1.3.0") == (1, 3, 0)


def test_notes_are_plain_text():
    notes = plain_notes("## New\n\n- **Faster** exports\n- [Read more](https://example.invalid)\n\n```\ncode\n```")
    assert "##" not in notes and "**" not in notes and "](" not in notes
    assert "Faster exports" in notes and "Read more" in notes


# --------------------------------------------------------------------------- #
# Checking
# --------------------------------------------------------------------------- #


def test_a_newer_release_with_both_assets_is_offered(tmp_path):
    manager, http, _ = make_manager(tmp_path, release_reply())
    assert manager.check()["state"] == "checking"
    status = manager.wait()
    assert status["state"] == "available"
    assert status["version"] == "1.4.0"
    assert "Faster exports" in status["notes"]
    assert status["progress"] is None
    assert http.requests[0].get_header("User-agent") == f"ManimStudio/{APP_VERSION}"


def test_the_default_opener_reaches_the_network(tmp_path, monkeypatch):
    """Without an injected opener the real urllib opener's open() does the request."""
    reply = release_reply()
    calls = []

    def record(opener, request, data=None, timeout=None, *args, **kwargs):
        calls.append((request, timeout))
        return reply

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", record)
    root = install_site(tmp_path)
    manager = UpdateManager(str(tmp_path / "ws"), platform="windows", mode="desktop",
                            app_version="1.3.0", data_dir=str(tmp_path),
                            running_exe=str(root / updates.APP_EXE_NAME),
                            install_folder=str(root), signature_probe=lambda _path: None)
    manager.check()
    status = manager.wait()
    assert status["state"] == "available" and status["version"] == "1.4.0"
    assert calls and calls[0][1] == updates.HTTP_TIMEOUT
    assert urllib.parse.urlsplit(calls[0][0].full_url).netloc == "api.github.com"


def test_a_programming_error_is_logged_but_stays_quiet(tmp_path, caplog):
    class BrokenHTTP:
        def open(self, request, timeout=None):
            raise TypeError("'OpenerDirector' object is not callable")

    root = install_site(tmp_path)
    manager = UpdateManager(str(tmp_path / "ws"), platform="windows", mode="desktop",
                            app_version="1.3.0", data_dir=str(tmp_path),
                            opener=BrokenHTTP(), running_exe=str(root / updates.APP_EXE_NAME),
                            install_folder=str(root), signature_probe=lambda _path: None)
    with caplog.at_level(logging.ERROR, logger=updates.__name__):
        manager.check()
        status = manager.wait()
    assert status["state"] == "unavailable"
    assert status["detail"] == "Couldn't check for updates. Try again later."
    assert any(record.exc_info for record in caplog.records)


def test_prereleases_and_drafts_are_skipped(tmp_path):
    for payload in (release_reply(prerelease=True, tag="v9.9.9"), release_reply(draft=True, tag="v9.9.9")):
        manager, _, _ = make_manager(tmp_path, payload)
        manager.check()
        status = manager.wait()
        assert status["state"] == "idle"
        assert status["version"] is None


def test_an_older_release_is_never_offered(tmp_path):
    manager, _, _ = make_manager(tmp_path, release_reply(tag="v1.2.9"))
    manager.check()
    status = manager.wait()
    assert status["state"] == "idle" and status["version"] is None


def test_a_release_without_both_assets_is_not_offered(tmp_path):
    only_installer = [asset(INSTALLER_NAME, INSTALLER_URL)]
    manager, _, _ = make_manager(tmp_path, release_reply(assets=only_installer))
    manager.check()
    status = manager.wait()
    assert status["state"] == "unavailable" and status["version"] is None


@pytest.mark.parametrize("url", [
    "http://github.com/birol-dev/x/ManimStudioSetup.exe",
    "https://evil.example/ManimStudioSetup.exe",
    "https://api.github.com/repos/x/ManimStudioSetup.exe",
])
def test_an_asset_url_outside_https_github_is_refused(tmp_path, url):
    assets = [asset(INSTALLER_NAME, url), asset(INSTALLER_NAME + ".sha256", DIGEST_URL)]
    manager, http, _ = make_manager(tmp_path, release_reply(assets=assets))
    manager.check()
    status = manager.wait()
    assert status["state"] == "unavailable" and status["version"] is None
    assert len(http.requests) == 1  # nothing else was fetched


def test_offline_is_a_quiet_state_not_an_error(tmp_path):
    manager, _, _ = make_manager(tmp_path, urllib.error.URLError("offline"))
    manager.check()
    status = manager.wait()
    assert status["state"] == "unavailable"
    assert "internet connection" in status["detail"]


def test_rate_limited_is_a_quiet_state(tmp_path):
    error = urllib.error.HTTPError(updates.RELEASE_URL, 403, "rate limited", {}, None)
    manager, _, _ = make_manager(tmp_path, error)
    manager.check()
    status = manager.wait()
    assert status["state"] == "unavailable"
    assert "Try again later" in status["detail"]


def test_source_mode_and_other_platforms_say_how_to_update(tmp_path):
    for kwargs in ({"platform": "linux"}, {"platform": "macos"}, {"platform": "windows", "mode": "source"}):
        http = FakeHTTP()
        manager = UpdateManager(str(tmp_path / "ws"), opener=http, data_dir=str(tmp_path), **kwargs)
        status = manager.auto_check()
        assert status["state"] == "unavailable"
        assert status["detail"] == "You're running from source. Use git pull to update."
        assert http.requests == []


def test_updates_need_the_installed_copy(tmp_path):
    site = install_site(tmp_path)
    workspace, data = str(tmp_path / "ws"), str(tmp_path)

    def manager_for(root):
        http = FakeHTTP()
        manager = UpdateManager(workspace, platform="windows", mode="desktop", app_version="1.3.0",
                                data_dir=data, running_exe=str(root / updates.APP_EXE_NAME),
                                install_folder=str(site), opener=http,
                                spawn=lambda *args, **options: None,
                                signature_probe=lambda _path: None)
        return manager, http

    # No Manim Studio.exe: a source checkout.
    source, source_http = manager_for(tmp_path / "source")
    assert source.auto_check()["detail"] == updates.SOURCE_DETAIL
    assert source_http.requests == []

    # The portable folder has the app exe but no Uninstall.exe.
    portable = tmp_path / "portable"
    portable.mkdir()
    (portable / updates.APP_EXE_NAME).write_bytes(b"app")
    portable_manager, portable_http = manager_for(portable)
    for status in (portable_manager.auto_check(), portable_manager.check(),
                   portable_manager.download(), portable_manager.install()):
        assert status["state"] == "unavailable"
        assert status["detail"] == "This copy can't update itself. Get the newest installer to update."
    assert portable_http.requests == []

    # An installed copy somewhere else (the test installer's /dir:) cannot update itself either.
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / updates.APP_EXE_NAME).write_bytes(b"app")
    (elsewhere / updates.UNINSTALLER_NAME).write_bytes(b"uninstaller")
    moved, _ = manager_for(elsewhere)
    assert moved.auto_check()["detail"] == updates.PORTABLE_DETAIL


# --------------------------------------------------------------------------- #
# Once a day, and the preference
# --------------------------------------------------------------------------- #


def test_automatic_check_runs_at_most_once_a_day(tmp_path):
    manager, http, _ = make_manager(tmp_path, release_reply())
    manager.auto_check()
    manager.wait()
    assert len(http.requests) == 1
    # The next launch of the app reads the saved time and stays quiet.
    again, second_http, _ = make_manager(tmp_path, release_reply())
    again.auto_check()
    assert second_http.requests == []


def test_the_update_check_preference_defaults_on_and_validates(tmp_path):
    store = PreferenceStore(str(tmp_path / "ws"))
    assert store.read().get("update_check", True) is True
    assert store.update({"update_check": False}) == {"update_check": False}
    assert store.read()["update_check"] is False
    with pytest.raises(TemplateError):
        store.update({"update_check": "no"})


def test_automatic_check_respects_the_preference(tmp_path):
    PreferenceStore(str(tmp_path / "ws")).update({"update_check": False})
    manager, http, _ = make_manager(tmp_path, release_reply())
    manager.auto_check()
    assert http.requests == []
    # A manual check still runs.
    manager.check()
    manager.wait()
    assert len(http.requests) == 1


# --------------------------------------------------------------------------- #
# Downloading
# --------------------------------------------------------------------------- #


def test_a_verified_download_lands_in_the_updates_folder(tmp_path):
    payload = b"a real-ish installer"
    manager, _, _ = ready_manager(tmp_path, payload)
    installer = tmp_path / "ws/studio/updates" / INSTALLER_NAME
    assert installer.read_bytes() == payload
    assert manager.status()["progress"] == 100
    assert manager.status()["state"] == "ready"


def test_a_digest_mismatch_deletes_the_file(tmp_path):
    payload = b"damaged"
    manager, _, _ = make_manager(tmp_path, release_reply(), digest_reply(payload, digest="0" * 64),
                                 installer_reply(payload))
    manager.check()
    manager.wait()
    manager.download()
    status = manager.wait()
    assert status["state"] == "failed"
    assert "damaged" in status["detail"]
    folder = tmp_path / "ws/studio/updates"
    assert not folder.exists() or list(folder.iterdir()) == []


def test_a_download_that_leaves_github_is_refused(tmp_path):
    payload = b"installer"
    manager, _, _ = make_manager(
        tmp_path, release_reply(), digest_reply(payload),
        installer_reply(payload, url="https://evil.example/ManimStudioSetup.exe"))
    manager.check()
    manager.wait()
    manager.download()
    status = manager.wait()
    assert status["state"] == "failed"
    folder = tmp_path / "ws/studio/updates"
    assert not folder.exists() or list(folder.iterdir()) == []


def test_an_installer_over_a_gigabyte_is_refused_before_downloading(tmp_path):
    manager, _, _ = make_manager(
        tmp_path, release_reply(), digest_reply(b"x"),
        installer_reply(b"x", content_length=MAX_INSTALLER_BYTES + 1))
    manager.check()
    manager.wait()
    manager.download()
    status = manager.wait()
    assert status["state"] == "failed"
    assert "larger than expected" in status["detail"]


def test_only_one_installer_is_kept(tmp_path):
    payload = b"installer"
    folder = tmp_path / "ws/studio/updates"
    folder.mkdir(parents=True)
    (folder / "ManimStudioSetup-old.exe").write_bytes(b"old")
    (folder / ".stale.download").write_bytes(b"partial")
    ready_manager(tmp_path, payload)
    assert sorted(item.name for item in folder.iterdir()) == [INSTALLER_NAME]


def test_a_download_requires_a_check_first(tmp_path):
    manager, _, _ = make_manager(tmp_path)
    with pytest.raises(UpdateError) as info:
        manager.download()
    assert "Check for updates first" in str(info.value)


# --------------------------------------------------------------------------- #
# Signatures
# --------------------------------------------------------------------------- #


def test_a_signed_copy_requires_the_same_publisher(tmp_path):
    payload = b"installer"
    running = str(install_site(tmp_path) / updates.APP_EXE_NAME)

    def probe(path):
        return "CN=Manim Studio" if path == running else "CN=Someone Else"

    manager, _, _ = make_manager(tmp_path, release_reply(), digest_reply(payload),
                                 installer_reply(payload), running_exe=running, signature_probe=probe)
    manager.check()
    manager.wait()
    manager.download()
    status = manager.wait()
    assert status["state"] == "failed"
    assert "not signed by the same publisher" in status["detail"]


def test_an_unsigned_copy_needs_no_signature(tmp_path):
    payload = b"installer"
    manager, _, _ = make_manager(tmp_path, release_reply(), digest_reply(payload),
                                 installer_reply(payload), signature_probe=lambda _path: None)
    manager.check()
    manager.wait()
    manager.download()
    assert manager.wait()["state"] == "ready"


# --------------------------------------------------------------------------- #
# Installing
# --------------------------------------------------------------------------- #


def test_install_refuses_while_an_export_is_running(tmp_path):
    manager, _, spawned = ready_manager(tmp_path)
    with pytest.raises(UpdateBusy) as info:
        manager.install(active_export=True)
    assert str(info.value) == "An export is still running. It can finish first."
    assert spawned == []


def test_install_starts_the_breakaway_installer_and_waits_for_the_shell(tmp_path):
    manager, _, spawned = ready_manager(tmp_path)
    status = manager.install()
    assert len(spawned) == 1
    command, options = spawned[0]
    installer = str(tmp_path / "ws/studio/updates" / INSTALLER_NAME)
    assert command == [installer, "/S", "/update", "/relaunch", "/waitpid:4242",
                       f"/resultdir:{tmp_path}"]
    assert options["creationflags"] & updates.CREATE_BREAKAWAY_FROM_JOB
    assert status["state"] == "ready"
    assert "closing" in status["detail"]


def test_install_needs_a_verified_download(tmp_path):
    manager, _, spawned = make_manager(tmp_path)
    with pytest.raises(UpdateError) as info:
        manager.install()
    assert "Check for updates first" in str(info.value)
    assert spawned == []


def test_a_failed_update_result_is_shown_once(tmp_path):
    path = tmp_path / "update-result.json"
    path.write_text(json.dumps({"ok": False, "version": "1.4.0",
                                "message": "Manim Studio was still open after a minute."}),
                    encoding="utf-8")
    manager, _, _ = make_manager(tmp_path)
    first = manager.status()
    assert first["state"] == "failed"
    assert first["message"] == "Manim Studio was still open after a minute."
    assert not path.exists()  # the file is read once
    # The message stays for the UI until the next check, so a startup fetch cannot steal it.
    assert manager.status()["message"] == "Manim Studio was still open after a minute."
    manager.check()
    assert manager.wait()["message"] is None


# --------------------------------------------------------------------------- #
# The one version
# --------------------------------------------------------------------------- #


def test_frontend_and_installer_use_the_same_version():
    assert json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))["version"] == APP_VERSION
    sys.path.insert(0, str(ROOT / "desktop/scripts"))
    try:
        import build_installer
    finally:
        sys.path.remove(str(ROOT / "desktop/scripts"))
    assert build_installer.project_version() == APP_VERSION


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #


class RecordingManager:
    def __init__(self, state="idle"):
        self.calls = []
        self.state = state

    def status(self):
        return {"state": self.state, "version": None, "notes": "", "progress": None,
                "detail": None, "message": None}

    def auto_check(self):
        self.calls.append("auto")

    def check(self, manual=True):
        self.calls.append(("check", manual))
        return self.status()

    def download(self):
        self.calls.append("download")
        return self.status()

    def install(self, active_export=False):
        self.calls.append(("install", active_export))
        return self.status()


@pytest.fixture
def studio(tmp_path, monkeypatch):
    svc, _ = make_service(tmp_path)
    monkeypatch.setattr(service_module, "service", svc)
    yield svc
    svc.shutdown_sync()


@pytest.fixture
def api(studio, monkeypatch):
    manager = RecordingManager()
    monkeypatch.setattr(api_module, "get_update_manager", lambda: manager)
    return LocalClient(main.app, base_url="http://localhost"), manager


def test_setup_status_carries_the_one_version(api):
    client, _ = api
    assert client.get("/api/studio/setup/status").json()["version"] == APP_VERSION


def test_update_routes_report_and_start_work(api):
    client, manager = api
    assert client.get("/api/studio/setup/update").json()["state"] == "idle"
    assert manager.calls == ["auto"]
    assert client.post("/api/studio/setup/update/check").json()["state"] == "idle"
    assert client.post("/api/studio/setup/update/download").json()["state"] == "idle"
    assert client.post("/api/studio/setup/update/install").json()["state"] == "idle"
    assert manager.calls[-3:] == [("check", True), "download", ("install", False)]


def test_update_routes_answer_409_in_plain_words(api, monkeypatch):
    client, manager = api

    def refuse(active_export=False):
        raise UpdateBusy("An export is still running. It can finish first.")

    monkeypatch.setattr(manager, "install", refuse)
    response = client.post("/api/studio/setup/update/install")
    assert response.status_code == 409
    assert response.json()["detail"] == "An export is still running. It can finish first."
