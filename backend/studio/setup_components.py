"""What the app needs to make videos, and the optional tools it can fetch by itself.

Two parts ship with the app and are only reported here: WebView2 (Windows desktop)
and the Manim renderer. ffmpeg and LaTeX are optional and can be installed without
admin rights into ``<workspace>/studio/tools`` on Windows, from one pinned release
each (URL and SHA-256 below); elsewhere the status names the exact system command.
A download is verified before it is unpacked, unpacked into a new folder that is
then renamed into place, and a failure cleans up after itself.

Detection never runs a subprocess and is cached for a few seconds, so the setup
screen stays quick. The tools folders are put on PATH for render subprocesses.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import os
import shutil
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from typing import Optional

from . import host
from .errors import StudioError

CACHE_SECONDS = 5.0
DOWNLOAD_CHUNK = 256 * 1024
WEBVIEW2_IDS = (
    r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
    r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
)

# One pinned release per tool, each with the digest of the file at that URL.
# ffmpeg: https://www.gyan.dev/ffmpeg/builds/ (release essentials, x64).
# LaTeX: TinyTeX, the zip edition that carries the Windows binaries.
PINS = {
    "ffmpeg": {
        "url": "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-8.1.2-essentials_build.zip",
        "sha256": "db580001caa24ac104c8cb856cd113a87b0a443f7bdf47d8c12b1d740584a2ec",
        "root": "ffmpeg-8.1.2-essentials_build",
    },
    "latex": {
        "url": "https://github.com/rstudio/tinytex-releases/releases/download/v2026.10/TinyTeX-v2026.10.zip",
        "sha256": "dc1d6e63b21af62130ede1dcc4113bffdc184544690a23e3f489d75340f4ff61",
        "root": "TinyTeX",
    },
}

LABELS = {"webview2": "App window", "renderer": "Video renderer", "ffmpeg": "Sound tools",
          "latex": "Math support"}
PURPOSES = {
    "webview2": "Shows the app window on Windows.",
    "renderer": "Draws every video.",
    "ffmpeg": "Only needed by code scenes that add sound; templates do not use it.",
    "latex": "Only needed by math scenes in Author mode.",
}
APT = {"ffmpeg": "sudo apt install ffmpeg",
       "latex": "sudo apt install texlive-latex-recommended texlive-latex-extra dvisvgm"}
BREW = {"ffmpeg": "brew install ffmpeg", "latex": "brew install --cask basictex"}


class ComponentsError(StudioError):
    """A setup action could not be done; the message is ready to show people."""

    status = 409


class UnknownComponent(ComponentsError):
    status = 404


class InstallFailed(ComponentsError):
    """The download or its contents were not usable."""


def platform_name(value: Optional[str] = None) -> str:
    """``windows``, ``macos`` or ``linux`` (the names the setup API speaks)."""
    raw = (value or sys.platform).lower()
    if raw.startswith("win"):
        return "windows"
    if raw.startswith(("darwin", "mac")):
        return "macos"
    return "linux"


def mode_name(env=None) -> str:
    """The desktop launcher sets both variables; a source checkout sets neither."""
    env = os.environ if env is None else env
    return "desktop" if env.get("MANIM_API_TOKEN") and env.get("MANIM_WORKSPACE") else "source"


def tools_bin_dirs(tools_dir: str) -> list:
    """Folders in the tools directory that hold executables, if they exist."""
    candidates = (
        os.path.join(tools_dir, "ffmpeg", "bin"),
        os.path.join(tools_dir, "latex", "bin", "windows"),
        os.path.join(tools_dir, "latex", "bin", "win32"),
        os.path.join(tools_dir, "latex", "bin", "x86_64-linux"),
        os.path.join(tools_dir, "latex", "bin", "universal-darwin"),
    )
    return [path for path in candidates if os.path.isdir(path)]


def add_tools_to_path(tools_dir: str, environ=None) -> list:
    """Put the tools folders first on PATH so render subprocesses find them."""
    env = os.environ if environ is None else environ
    found = tools_bin_dirs(tools_dir)
    if not found:
        return []
    parts = [part for part in env.get("PATH", "").split(os.pathsep) if part]
    added = [path for path in found if path not in parts]
    if added:
        env["PATH"] = os.pathsep.join(added + parts)
    return added


def _manim_version() -> Optional[str]:
    """The installed Manim version, without importing it."""
    try:
        if importlib.util.find_spec("manim") is None:
            return None
    except (ImportError, ValueError):
        return None
    try:
        return importlib.metadata.version("manim")
    except importlib.metadata.PackageNotFoundError:
        return "installed"


def _webview2_version() -> Optional[str]:
    """The Evergreen WebView2 runtime version from the registry, if present."""
    if platform_name() != "windows":
        return None
    try:
        import winreg
    except ImportError:
        return None
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for path in WEBVIEW2_IDS:
            try:
                with winreg.OpenKey(root, path) as key:
                    value, _kind = winreg.QueryValueEx(key, "pv")
            except OSError:
                continue
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def reveal_folder(path: str, platform: Optional[str] = None) -> None:
    """Show *path* in the system's file manager."""
    name = platform_name(platform)
    if name == "windows":
        args = ["explorer", path]
    elif name == "macos":
        args = ["open", path]
    else:
        args = ["xdg-open", path]
    result = host._execute(args)
    if name != "windows" and result.returncode:
        raise ComponentsError("The folder could not be opened. Open it from the File menu instead.")


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(DOWNLOAD_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, path: str, progress) -> None:
    """Save *url* to *path*, reporting 0..1 progress while the size is known."""
    request = urllib.request.Request(url, headers={"User-Agent": "ManimStudio-Setup"})
    with urllib.request.urlopen(request, timeout=120) as response, open(path, "wb") as target:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = response.read(DOWNLOAD_CHUNK)
            if not chunk:
                break
            target.write(chunk)
            done += len(chunk)
            if total:
                progress(min(done / total, 1.0))
        if total and done != total:
            raise OSError("The download ended early.")


def safe_extract(archive: str, destination: str) -> None:
    """Unpack a zip, refusing entries that would escape *destination* (zip-slip)."""
    root = os.path.realpath(destination)
    try:
        with zipfile.ZipFile(archive) as bundle:
            for info in bundle.infolist():
                target = os.path.realpath(os.path.join(root, info.filename))
                if target != root and not target.startswith(root + os.sep):
                    raise InstallFailed("The download contains unsafe paths. Nothing was installed.")
                if info.is_dir():
                    os.makedirs(target, exist_ok=True)
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with bundle.open(info) as source, open(target, "wb") as handle:
                    shutil.copyfileobj(source, handle)
    except zipfile.BadZipFile:
        raise InstallFailed("The download was not a usable archive. Nothing was installed.") from None


class ComponentManager:
    """Detects what is available and installs the optional tools when asked."""

    def __init__(self, workspace: str, *, platform: Optional[str] = None, mode: Optional[str] = None,
                 env=None, environ=None, which=None, pins=None, downloader=None,
                 manim_probe=None, webview2_probe=None):
        self.workspace = os.path.abspath(workspace)
        self.tools_dir = os.path.join(self.workspace, "studio", "tools")
        self.platform = platform_name(platform or sys.platform)
        self.mode = mode or mode_name(env)
        self.environ = os.environ if environ is None else environ
        self.which = which or shutil.which
        self.pins = PINS if pins is None else pins
        self._download = downloader or _download
        self._manim = manim_probe or _manim_version
        self._webview2 = webview2_probe or _webview2_version
        self._lock = threading.RLock()
        self._installs: dict = {}
        self._cache = (0.0, None)

    # -- detection ------------------------------------------------------------------
    def _ffmpeg(self) -> Optional[str]:
        found = self.which("ffmpeg")
        if found:
            return found
        for name in ("ffmpeg.exe", "ffmpeg"):
            for folder in (os.path.join(self.tools_dir, "ffmpeg", "bin"), os.path.join(self.tools_dir, "ffmpeg")):
                candidate = os.path.join(folder, name)
                if os.path.isfile(candidate):
                    return candidate
        return None

    def _latex(self) -> Optional[str]:
        found = self.which("latex")
        if found:
            return found
        for folder in (("latex", "bin", "windows"), ("latex", "bin", "win32"),
                       ("latex", "bin", "x86_64-linux"), ("latex", "bin", "universal-darwin")):
            for name in ("latex.exe", "latex"):
                candidate = os.path.join(self.tools_dir, *folder, name)
                if os.path.isfile(candidate):
                    return candidate
        return None

    def _state(self, component_id: str):
        with self._lock:
            return dict(self._installs[component_id]) if component_id in self._installs else None

    def _can_install(self, component_id: str) -> bool:
        return (component_id in PINS and self.platform == "windows" and bool(self.pins.get(component_id))
                and (self._state(component_id) or {}).get("status") != "installing")

    def _entry(self, component_id: str) -> dict:
        state = self._state(component_id)
        installing = state is not None and state["status"] == "installing"
        failed = state is not None and state["status"] == "failed"
        if component_id == "webview2":
            installed = self._webview2() if self.platform == "windows" else None
            status = "ready" if installed else ("missing" if self.platform == "windows" else "optional")
            detail = (f"Version {installed} is ready." if installed else
                      "Microsoft Edge WebView2 is not installed. Run the Manim Studio installer again.")
            required = self.mode == "desktop"
        elif component_id == "renderer":
            installed = self._manim()
            status = "ready" if installed else "missing"
            detail = (f"Manim {installed} is ready." if installed else
                      "Manim is not installed. Run the Manim Studio installer again.")
            required = True
        else:
            installed = self._ffmpeg() if component_id == "ffmpeg" else self._latex()
            status, detail, required = "ready", "Ready.", False
            if not installed:
                status = "optional"
                if self.platform != "windows":
                    command = BREW[component_id] if self.platform == "macos" else APT[component_id]
                    detail = f"Not installed. To add it, run: {command}"
                elif self.pins.get(component_id):
                    detail = "Not installed. It can be added here without an administrator."
                else:
                    detail = f"Not installed. {PURPOSES[component_id]}"

        if installing:
            return {"id": component_id, "label": LABELS[component_id], "purpose": PURPOSES[component_id],
                    "status": "installing", "required": required, "can_install": False,
                    "detail": state.get("detail") or "Installing...", "progress": state.get("progress")}
        if failed:
            return {"id": component_id, "label": LABELS[component_id], "purpose": PURPOSES[component_id],
                    "status": "failed", "required": required, "can_install": self._can_install(component_id),
                    "detail": state.get("detail") or "The add-on could not be installed.", "progress": None}
        can_install = component_id in PINS and status != "ready" and self._can_install(component_id)
        return {"id": component_id, "label": LABELS[component_id], "purpose": PURPOSES[component_id],
                "status": status, "required": required, "can_install": can_install,
                "detail": detail, "progress": None}

    def _detect(self) -> list:
        ids = ["renderer", "ffmpeg", "latex"]
        if self.platform == "windows":
            ids.insert(0, "webview2")
        return [self._entry(component_id) for component_id in ids]

    def components(self) -> list:
        """The components in display order; detection is cached for a few seconds."""
        with self._lock:
            installing = any(state["status"] == "installing" for state in self._installs.values())
            stamp, cached = self._cache
            if cached is not None and not installing and time.monotonic() - stamp < CACHE_SECONDS:
                return [dict(item) for item in cached]
            items = self._detect()
            if not installing:
                self._cache = (time.monotonic(), items)
            return [dict(item) for item in items]

    def invalidate(self) -> None:
        with self._lock:
            self._cache = (0.0, None)

    # -- installing ------------------------------------------------------------------
    def install(self, component_id: str) -> dict:
        """Start one background install and return the component's current status (202)."""
        if component_id not in LABELS:
            raise UnknownComponent("That add-on is not part of this app.")
        if component_id in ("webview2", "renderer"):
            raise ComponentsError("The app installer adds this; there is nothing to download.")
        if self.platform != "windows":
            command = BREW[component_id] if self.platform == "macos" else APT[component_id]
            raise ComponentsError(f"This add-on is installed with the system: {command}")
        pin = self.pins.get(component_id)
        if not pin:
            raise ComponentsError("This add-on cannot be installed from the app right now.")
        with self._lock:
            state = self._installs.get(component_id)
            if state is not None and state["status"] == "installing":
                return self._entry(component_id)
            state = {"status": "installing", "progress": 0, "detail": "Starting the download..."}
            self._installs[component_id] = state
            self._cache = (0.0, None)
        threading.Thread(target=self._install_worker, args=(component_id, pin, state),
                         name=f"studio-install-{component_id}", daemon=True).start()
        return self._entry(component_id)

    def _progress(self, state: dict, fraction: Optional[float]) -> None:
        if fraction is not None:
            with self._lock:
                state["progress"] = max(0, min(90, int(fraction * 90)))

    def _install_worker(self, component_id: str, pin: dict, state: dict) -> None:
        work_dir = None
        try:
            os.makedirs(self.tools_dir, exist_ok=True)
            work_dir = tempfile.mkdtemp(prefix=f".{component_id}-", dir=self.tools_dir)
            archive = os.path.join(work_dir, "download.zip")
            self._download(pin["url"], archive, lambda fraction: self._progress(state, fraction))
            with self._lock:
                state["detail"] = "Checking the download..."
                state["progress"] = 90
            if sha256_file(archive).lower() != str(pin["sha256"]).lower():
                raise InstallFailed("The download was incomplete or damaged. Nothing was installed.")
            with self._lock:
                state["detail"] = "Unpacking..."
                state["progress"] = 95
            unpacked = os.path.join(work_dir, "unpacked")
            safe_extract(archive, unpacked)
            root = os.path.join(unpacked, pin.get("root") or "")
            if not os.path.isdir(root):
                raise InstallFailed("The download did not contain the expected folder. Nothing was installed.")
            target = os.path.join(self.tools_dir, component_id)
            if os.path.exists(target):
                raise InstallFailed("That add-on is already in the tools folder.")
            os.replace(root, target)
            add_tools_to_path(self.tools_dir, self.environ)
            with self._lock:
                state.update({"status": "ready", "progress": None, "detail": "Ready."})
        except InstallFailed as exc:
            with self._lock:
                state.update({"status": "failed", "progress": None, "detail": str(exc)})
        except Exception:
            with self._lock:
                state.update({"status": "failed", "progress": None,
                              "detail": "The add-on could not be installed. Check the connection and try again."})
        finally:
            if work_dir:
                shutil.rmtree(work_dir, ignore_errors=True)
            with self._lock:
                self._cache = (0.0, None)
