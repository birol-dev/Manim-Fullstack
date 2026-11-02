"""Check for, download and start Manim Studio updates (Windows desktop only).

The check reads the project's newest GitHub release. It sends nothing about the
person: one GET with a User-Agent, a five second timeout, and no identifier of
any kind. Drafts and prereleases are skipped, a release counts only when it
carries both the installer and its SHA-256 file, and an older version is never
offered.

The digest comes from the same release, so it proves the download arrived intact
and nothing more; it does not prove who published it. When the running app is
signed, the downloaded installer must be signed by the same subject as well.

Everything here runs on a background thread and a failure is a quiet state, not
an error dialog. Tests inject the HTTP opener, the signature probe and the path
of the running executable, so nothing in the suite touches the network.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from . import preferences
from .errors import StudioError
from .setup_components import mode_name, platform_name
from .version import APP_VERSION

RELEASE_URL = "https://api.github.com/repos/birol-dev/Manim-Fullstack/releases/latest"
INSTALLER_NAME = "ManimStudioSetup.exe"
DIGEST_NAME = "ManimStudioSetup.exe.sha256"
HTTP_TIMEOUT = 5.0
DOWNLOAD_TIMEOUT = 120.0
CHECK_INTERVAL_SECONDS = 24 * 60 * 60
MAX_RELEASE_BYTES = 512 * 1024
MAX_DIGEST_BYTES = 4 * 1024
MAX_INSTALLER_BYTES = 1024 * 1024 * 1024
DOWNLOAD_CHUNK = 256 * 1024
MAX_NOTES_CHARS = 4000
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
APP_EXE_NAME = "Manim Studio.exe"
UNINSTALLER_NAME = "Uninstall.exe"
SOURCE_DETAIL = "You're running from source. Use git pull to update."
PORTABLE_DETAIL = "This copy can't update itself. Get the newest installer to update."

logger = logging.getLogger(__name__)

# The running app's signature, read without building a command string: the path
# travels in the environment, so a path with quotes or spaces can't become code.
SIGNATURE_COMMAND = (
    "$s = Get-AuthenticodeSignature -LiteralPath $env:MANIM_STUDIO_UPDATE_FILE; "
    "if ($s.Status -eq 'Valid' -and $s.SignerCertificate) { $s.SignerCertificate.Subject }"
)
SIGNATURE_ENV = "MANIM_STUDIO_UPDATE_FILE"
SIGNATURE_TIMEOUT = 30.0

_MARKDOWN_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_MARKDOWN_TAG = re.compile(r"<[^>]+>")
_BLANK_LINES = re.compile(r"\n{3,}")


class UpdateError(StudioError):
    """An update action cannot be done; the message is ready to show people."""

    status = 409


class UpdateBusy(UpdateError):
    """An export is using the renderer, so installing now would interrupt it."""


def version_numbers(value) -> tuple:
    """The numeric parts of a version, so ``v1.3`` and ``1.3.0`` compare as written."""
    parts = re.findall(r"\d+", str(value or ""))
    return tuple(int(part) for part in parts)


def is_newer(candidate, current) -> bool:
    """True when *candidate* is a later numeric version than *current*."""
    left, right = version_numbers(candidate), version_numbers(current)
    if not left:
        return False
    length = max(len(left), len(right))
    return left + (0,) * (length - len(left)) > right + (0,) * (length - len(right))


def plain_notes(body) -> str:
    """Release notes as plain text: no Markdown markers, no HTML, a bounded length."""
    text = str(body or "").replace("\r\n", "\n").replace("\r", "\n")
    text = _MARKDOWN_LINK.sub(lambda match: match.group(1), text)
    text = _MARKDOWN_TAG.sub("", text)
    lines = []
    in_fence = False
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            lines.append(line.rstrip())
            continue
        stripped = line.strip()
        if not stripped:
            lines.append("")
            continue
        stripped = re.sub(r"^#{1,6}\s*", "", stripped)
        stripped = re.sub(r"^[-*+]\s+", "• ", stripped)
        stripped = re.sub(r"^>\s?", "", stripped)
        stripped = stripped.replace("**", "").replace("__", "").replace("`", "")
        lines.append(stripped)
    text = _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()
    if len(text) > MAX_NOTES_CHARS:
        text = text[:MAX_NOTES_CHARS].rstrip() + "…"
    return text


def _allowed_redirect(url: str) -> bool:
    """Downloads may only pass through https github.com / *.githubusercontent.com."""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    if parts.scheme != "https":
        return False
    if parts.port not in (None, 443):
        return False
    host = (parts.hostname or "").lower()
    return host == "github.com" or host.endswith(".githubusercontent.com")


def _asset_url_allowed(url: str) -> bool:
    """A release asset URI must be https on github.com itself."""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    return (parts.scheme == "https" and (parts.hostname or "").lower() == "github.com"
            and parts.port in (None, 443))


class _GuardedRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse a redirect that leaves https or the two allowed GitHub hosts."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _allowed_redirect(newurl):
            raise urllib.error.HTTPError(newurl, 403, "Redirect refused", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def default_opener():
    """The real HTTP opener; redirects are checked at every hop."""
    return urllib.request.build_opener(_GuardedRedirect())


def default_install_folder() -> str:
    """Where the installer puts the app: %LOCALAPPDATA%\\Programs\\ManimStudio."""
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(base, "Programs", "ManimStudio")


def _same_folder(left: str, right: str) -> bool:
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(DOWNLOAD_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _digest_value(text: str) -> Optional[str]:
    """The lowercase hex digest from a ``sha256sum`` style file, or None."""
    match = re.match(r"\s*([0-9a-fA-F]{64})(?:\s|$)", text or "")
    return match.group(1).lower() if match else None


class UpdateManager:
    """The update state one workspace sees; safe to read while a thread works."""

    def __init__(self, workspace: str, *, platform: Optional[str] = None, mode: Optional[str] = None,
                 app_version: str = APP_VERSION, opener=None, spawn=None,
                 signature_probe=None, running_exe=None, install_folder=None, shell_pid=None,
                 data_dir=None, clock=None):
        self.workspace = os.path.abspath(workspace)
        self.data_dir = os.path.abspath(data_dir) if data_dir else os.path.dirname(self.workspace)
        self.platform = platform_name(platform or sys.platform)
        self.mode = mode or mode_name()
        self.app_version = app_version
        self.updates_dir = os.path.join(self.workspace, "studio", "updates")
        self.check_file = os.path.join(self.workspace, "studio", "update-check.json")
        self._open = (opener or default_opener()).open
        self._spawn = spawn or subprocess.Popen
        self._signature = signature_probe
        self._running_exe = running_exe
        self._install_folder = os.path.abspath(install_folder or default_install_folder())
        self._shell_pid = shell_pid
        self._clock = clock or time.time
        self._lock = threading.RLock()
        self._thread = None
        self._state = "idle"
        self._detail = None
        self._version = None
        self._notes = ""
        self._progress = None
        self._message = None
        self._release = None
        self._installer = None

    # -- state ----------------------------------------------------------------------
    def _app_root(self) -> Optional[str]:
        """The folder holding the running app's exe, or None when there is no app exe."""
        executable = self._running_executable()
        if not executable or not os.path.isfile(executable):
            return None
        return os.path.dirname(os.path.abspath(executable))

    def _installed(self) -> bool:
        """Only the copy the installer made into the default folder may update itself."""
        root = self._app_root()
        if root is None:
            return False
        return (os.path.isfile(os.path.join(root, APP_EXE_NAME))
                and os.path.isfile(os.path.join(root, UNINSTALLER_NAME))
                and _same_folder(root, self._install_folder))

    def supported(self) -> bool:
        """Updates run in the installed Windows app; a source checkout, another OS or a
        portable copy does not."""
        return self.platform == "windows" and self.mode == "desktop" and self._installed()

    def _unavailable_detail(self) -> str:
        """Why updates are not offered: no app exe means source, a loose copy means portable."""
        if self.platform != "windows" or self.mode != "desktop" or self._app_root() is None:
            return SOURCE_DETAIL
        return PORTABLE_DETAIL

    def unavailable(self) -> dict:
        return {"state": "unavailable", "version": None, "notes": "", "progress": None,
                "detail": self._unavailable_detail(), "message": None}

    def _reset(self, state: str, detail: Optional[str]) -> None:
        with self._lock:
            self._state = state
            self._detail = detail
            self._version = None
            self._notes = ""
            self._progress = None

    def status(self) -> dict:
        with self._lock:
            # The installer's result file is read once; the message stays in this
            # process so Settings can show it even if another view asked first.
            self._take_result()
            return {"state": self._state, "version": self._version, "notes": self._notes,
                    "progress": self._progress, "detail": self._detail, "message": self._message}

    def _set(self, state: str, *, detail=None, version=None, notes=None, progress=None):
        with self._lock:
            self._state = state
            self._detail = detail
            self._version = version
            self._notes = notes if notes is not None else ""
            self._progress = progress
            self._message = None

    def _take_result(self) -> None:
        """Show the installer's result once, then forget the file."""
        path = os.path.join(self.data_dir, "update-result.json")
        try:
            with open(path, encoding="utf-8") as source:
                raw = source.read(64 * 1024 + 1)
            os.remove(path)
        except (OSError, ValueError):
            return
        try:
            data = json.loads(raw)
        except ValueError:
            return
        if not isinstance(data, dict):
            return
        message = data.get("message")
        if data.get("ok") is False and isinstance(message, str) and message:
            self._state = "failed"
            self._detail = message
            self._message = message
            self._version = None
            self._notes = ""
            self._progress = None
        elif data.get("ok") is True:
            # The update worked; the new version starts with a clean slate.
            self._state = "idle"
            self._detail = None
            self._message = None
            self._version = None
            self._notes = ""
            self._progress = None

    # -- checking -------------------------------------------------------------------
    def _auto_allowed(self) -> bool:
        stored = preferences.PreferenceStore(self.workspace).read()
        return stored.get("update_check", True) is not False

    def _checked_recently(self) -> bool:
        try:
            with open(self.check_file, encoding="utf-8") as source:
                data = json.load(source)
            checked = float(data.get("checked"))
        except (OSError, ValueError, TypeError, AttributeError):
            return False
        return 0 <= self._clock() - checked < CHECK_INTERVAL_SECONDS

    def _note_check(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.check_file), exist_ok=True)
            with open(self.check_file, "w", encoding="utf-8") as target:
                json.dump({"checked": int(self._clock())}, target)
        except OSError:
            pass

    def auto_check(self) -> dict:
        """Check in a background thread when the preference allows it and a day has passed."""
        if not self.supported():
            self._reset("unavailable", self._unavailable_detail())
            return self.status()
        with self._lock:
            if self._state in ("downloading", "ready", "checking"):
                return self.status()
        if not self._auto_allowed() or self._checked_recently():
            return self.status()
        return self.check(manual=False)

    def check(self, manual: bool = True) -> dict:
        """Start a check; a manual one always runs, an automatic one respects the day."""
        if not self.supported():
            self._reset("unavailable", self._unavailable_detail())
            return self.status()
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self.status()
            self._state = "checking"
            self._detail = "Checking for updates…"
            self._progress = None
            self._message = None
            self._thread = threading.Thread(target=self._check_worker, name="studio-update-check",
                                            daemon=True)
            self._thread.start()
        return self.status()

    def wait(self, timeout: float = 10.0) -> dict:
        """Wait for the background work to finish (tests, and the manual route's thread)."""
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
        return self.status()

    def _check_worker(self) -> None:
        try:
            release = self._fetch_release()
            version = str(release.get("tag_name") or release.get("name") or "").strip()
            if not version_numbers(version):
                self._set("unavailable", detail="Couldn't check for updates. Try again later.")
                return
            if not is_newer(version, self.app_version):
                with self._lock:
                    self._state = "idle"
                    self._detail = "You're using the latest version."
                    self._version = None
                    self._notes = ""
                return
            assets = self._assets(release)
            if assets is None:
                self._set("unavailable", detail="The newest update isn't ready yet. Try again later.")
                return
            installer, digest = assets
            with self._lock:
                self._release = release
                self._installer = installer
                self._state = "available"
                self._version = version.lstrip("vV")
                self._notes = plain_notes(release.get("body"))
                self._detail = None
                self._progress = None
                self._message = None
            # Nothing is downloaded until the person asks.
        except urllib.error.HTTPError as error:
            self._set("unavailable", detail=self._quiet_detail(error))
        except (urllib.error.URLError, TimeoutError, OSError):
            self._set("unavailable", detail="Couldn't check for updates. Check your internet connection and try again.")
        except ValueError:
            self._set("unavailable", detail="Couldn't check for updates. Try again later.")
        except Exception:  # a background thread must never die with a traceback
            logger.exception("Update check failed")
            self._set("unavailable", detail="Couldn't check for updates. Try again later.")
        finally:
            self._note_check()

    @staticmethod
    def _quiet_detail(error) -> str:
        if error.code in (403, 429):
            return "Couldn't check for updates right now. Try again later."
        return "Couldn't check for updates. Try again later."

    def _read(self, url: str, limit: int) -> bytes:
        request = urllib.request.Request(url, headers={
            "User-Agent": f"ManimStudio/{self.app_version}",
            "Accept": "application/vnd.github+json",
        })
        with self._open(request, timeout=HTTP_TIMEOUT) as response:
            final = response.geturl() if hasattr(response, "geturl") else None
            if final and final != url and not _allowed_redirect(final):
                raise ValueError("A redirect left GitHub.")
            data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError("The answer was larger than expected.")
        return data

    def _fetch_release(self) -> dict:
        data = json.loads(self._read(RELEASE_URL, MAX_RELEASE_BYTES).decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("The release answer was not an object.")
        if data.get("draft") or data.get("prerelease"):
            return {"tag_name": self.app_version, "body": ""}
        return data

    @staticmethod
    def _assets(release: dict):
        """Both asset URLs, when the release has them and they are safe to use."""
        found = {}
        assets = release.get("assets")
        if not isinstance(assets, list):
            return None
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            name = asset.get("name")
            url = asset.get("browser_download_url")
            if name in (INSTALLER_NAME, DIGEST_NAME) and isinstance(url, str):
                found[name] = asset
        if set(found) != {INSTALLER_NAME, DIGEST_NAME}:
            return None
        for name in (INSTALLER_NAME, DIGEST_NAME):
            if not _asset_url_allowed(found[name]["browser_download_url"]):
                return None
        size = found[INSTALLER_NAME].get("size")
        if isinstance(size, (int, float)) and size > MAX_INSTALLER_BYTES:
            return None
        return (found[INSTALLER_NAME]["browser_download_url"], found[DIGEST_NAME]["browser_download_url"])

    # -- downloading ----------------------------------------------------------------
    def download(self) -> dict:
        """Fetch the installer in the background and verify its digest."""
        if not self.supported():
            return self.unavailable()
        with self._lock:
            if self._state == "ready" and self._installer and os.path.isfile(self._installer):
                return self.status()
            if self._thread is not None and self._thread.is_alive():
                return self.status()
            if self._state != "available" or not self._release:
                raise UpdateError("There's no update to download yet. Check for updates first.")
            self._state = "downloading"
            self._detail = "Downloading version %s…" % (self._version or "")
            self._progress = 0
            self._message = None
            self._thread = threading.Thread(target=self._download_worker, name="studio-update-download",
                                            daemon=True)
            self._thread.start()
        return self.status()

    def _remove_installers(self) -> None:
        try:
            for name in os.listdir(self.updates_dir):
                if name.lower().endswith((".exe", ".download")):
                    try:
                        os.remove(os.path.join(self.updates_dir, name))
                    except OSError:
                        pass
        except OSError:
            pass

    def _progress_report(self, fraction) -> None:
        if fraction is None:
            return
        percent = max(0, min(90, int(fraction * 90)))
        with self._lock:
            if percent > (self._progress or 0):
                self._progress = percent

    def _download_worker(self) -> None:
        temporary = None
        try:
            self._remove_installers()
            os.makedirs(self.updates_dir, exist_ok=True)
            installer_url, digest_url = self._assets(self._release) or (None, None)
            if not installer_url or not digest_url:
                raise UpdateError("The newest update isn't ready yet. Try again later.")
            digest_text = self._read(digest_url, MAX_DIGEST_BYTES).decode("utf-8", errors="replace")
            expected = _digest_value(digest_text)
            if expected is None:
                raise UpdateError("The update's checksum file was not usable, so nothing was installed.")
            temporary = os.path.join(self.updates_dir, f".{INSTALLER_NAME}.{os.urandom(8).hex()}.download")
            self._download_file(installer_url, temporary)
            with self._lock:
                self._detail = "Checking the download…"
                self._progress = 95
            if sha256_file(temporary) != expected:
                raise UpdateError("The update file was damaged, so it was not used. Try again.")
            required = self._required_signer()
            if required:
                subject = self._signature_subject(temporary)
                if not subject or subject != required:
                    raise UpdateError("The update file is not signed by the same publisher as this copy, "
                                      "so it was not used.")
            final = os.path.join(self.updates_dir, INSTALLER_NAME)
            os.replace(temporary, final)
            temporary = None
            with self._lock:
                self._installer = final
                self._state = "ready"
                self._progress = 100
                self._detail = "Ready to install."
        except UpdateError as error:
            self._fail(str(error))
        except urllib.error.HTTPError:
            self._fail("The update couldn't be downloaded. Check your internet connection and try again.")
        except (urllib.error.URLError, TimeoutError, OSError):
            self._fail("The update couldn't be downloaded. Check your internet connection and try again.")
        except ValueError:
            self._fail("The update couldn't be verified, so it was not used. Try again.")
        except Exception:  # a background thread must never die with a traceback
            logger.exception("Update download failed")
            self._fail("The update couldn't be downloaded. Try again.")
        finally:
            if temporary:
                try:
                    os.remove(temporary)
                except OSError:
                    pass

    def _fail(self, message: str) -> None:
        with self._lock:
            self._state = "failed"
            self._detail = message
            self._progress = None
            self._installer = None
        self._remove_installers()

    def _download_file(self, url: str, path: str) -> None:
        request = urllib.request.Request(url, headers={"User-Agent": f"ManimStudio/{self.app_version}"})
        with self._open(request, timeout=DOWNLOAD_TIMEOUT) as response:
            final = response.geturl() if hasattr(response, "geturl") else None
            if final and final != url and not _allowed_redirect(final):
                raise UpdateError("The update came from an address that is not allowed, so it was not used.")
            headers = getattr(response, "headers", {}) or {}
            try:
                total = int(headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                total = 0
            if total > MAX_INSTALLER_BYTES:
                raise UpdateError("The update file is larger than expected, so it was not used.")
            done = 0
            with open(path, "wb") as target:
                while True:
                    chunk = response.read(DOWNLOAD_CHUNK)
                    if not chunk:
                        break
                    done += len(chunk)
                    if done > MAX_INSTALLER_BYTES:
                        raise UpdateError("The update file is larger than expected, so it was not used.")
                    target.write(chunk)
                    if total:
                        self._progress_report(done / total)
            if total and done != total:
                raise UpdateError("The download ended early, so nothing was installed.")

    # -- signatures -----------------------------------------------------------------
    def _running_executable(self) -> Optional[str]:
        if self._running_exe is not None:
            return self._running_exe
        override = os.environ.get("MANIM_STUDIO_APP_EXE")
        if override and os.path.isfile(override):
            return override
        candidate = os.path.join(os.path.dirname(os.path.dirname(sys.executable)), "Manim Studio.exe")
        return candidate if os.path.isfile(candidate) else None

    def _required_signer(self) -> Optional[str]:
        """The running app's signer subject, when this copy is validly signed."""
        if self._running_executable is None:
            return None
        return self._signature_subject(self._running_executable())

    def _signature_subject(self, path: str) -> Optional[str]:
        if self._signature is not None:
            return self._signature(path)
        if not path or not os.path.isfile(path):
            return None
        environment = {**os.environ, SIGNATURE_ENV: os.path.abspath(path)}
        try:
            completed = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", SIGNATURE_COMMAND],
                capture_output=True, text=True, timeout=SIGNATURE_TIMEOUT, env=environment,
                creationflags=CREATE_NO_WINDOW)
        except (OSError, subprocess.TimeoutExpired):
            return None
        subject = (completed.stdout or "").strip()
        return subject or None

    # -- installing -----------------------------------------------------------------
    def install(self, active_export: bool = False) -> dict:
        """Start the verified installer and let the app close so it can replace the files."""
        if not self.supported():
            return self.unavailable()
        if active_export:
            raise UpdateBusy("An export is still running. It can finish first.")
        with self._lock:
            installer = self._installer
            if self._state != "ready" or not installer or not os.path.isfile(installer):
                raise UpdateError("There's no update ready to install. Check for updates first.")
            pid = self._shell_pid if self._shell_pid is not None else os.getppid()
        command = [installer, "/S", "/update", "/relaunch", f"/waitpid:{pid}",
                   f"/resultdir:{self.data_dir}"]
        try:
            self._spawn(command, close_fds=True, creationflags=CREATE_BREAKAWAY_FROM_JOB | CREATE_NO_WINDOW)
        except OSError:
            raise UpdateError("The update could not start. Close Manim Studio and try again.") from None
        with self._lock:
            self._detail = "Manim Studio is closing to install the update."
        return self.status()


def update_status(manager: UpdateManager) -> dict:
    """Read the state, starting the once-a-day check when it is due."""
    manager.auto_check()
    return manager.status()
