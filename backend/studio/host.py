"""Things the computer can do with a finished export: show it in the file manager, copy the file.

Only paths the studio resolved itself (``ExportManager.export_file_path``) reach these
helpers; nothing here takes a path from a client. Every action runs as a fixed argv
list with a timeout, and failures come back as ``HostError`` with a message for people.
"""

from __future__ import annotations

import os
import platform
import subprocess
from typing import Optional

from .errors import StudioError

TIMEOUT_SECONDS = 15.0
# Windows PowerShell joins everything after -Command into one command string, so a path
# placed there would become script text. It travels in the environment instead.
COPY_ENV = "MANIM_STUDIO_CLIPBOARD_FILE"
WINDOWS_COPY_COMMAND = "Set-Clipboard -LiteralPath $env:" + COPY_ENV
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class HostError(StudioError):
    """The system would not do the action; the message is ready to show people."""

    status = 500


class HostUnsupported(HostError):
    """This platform has no way to do the action."""

    status = 501


def platform_name(system: Optional[str] = None) -> str:
    return system or platform.system()


def capabilities(system: Optional[str] = None) -> dict:
    """Which finished-file actions this platform supports."""
    name = platform_name(system)
    return {"reveal": name in ("Windows", "Darwin", "Linux"), "copy_file": name in ("Windows", "Darwin")}


def reveal_args(path: str, system: Optional[str] = None):
    """The argv that shows *path* selected in its folder; Windows needs one command line string."""
    name = platform_name(system)
    if name == "Windows":
        # subprocess quotes a list argument that contains spaces ("/select,C:\Jane Doe\a.mp4"),
        # and Explorer then opens the default folder. The switch and the path are one argument
        # to Explorer, so the command line is built here with only the path quoted.
        if '"' in path:
            raise HostError("That file name can't be shown in its folder. Download the file instead.")
        return f'explorer /select,"{path}"'
    if name == "Darwin":
        return ["open", "-R", path]
    return ["xdg-open", os.path.dirname(path) or "."]


def copy_args(path: str, system: Optional[str] = None) -> list:
    """The argv that puts the file itself on the clipboard; raises when the platform can't."""
    name = platform_name(system)
    if name == "Windows":
        return ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                "-Command", WINDOWS_COPY_COMMAND]
    if name == "Darwin":
        literal = (path.replace("\\", "\\\\").replace('"', '\\"')
                   .replace("\n", "\\n").replace("\r", "\\r"))
        return ["osascript", "-e", f'set the clipboard to (POSIX file "{literal}")']
    raise HostUnsupported("Copying a file itself to the clipboard works on Windows and macOS only. "
                          "Download the file instead.")


def _execute(args, env: Optional[dict] = None):
    options = {"capture_output": True, "text": True, "timeout": TIMEOUT_SECONDS}
    if env is not None:
        options["env"] = {**os.environ, **env}
    if os.name == "nt" and _NO_WINDOW:
        options["creationflags"] = _NO_WINDOW
    try:
        return subprocess.run(args, **options)
    except subprocess.TimeoutExpired:
        raise HostError("The system didn't respond in time. Try again.") from None
    except OSError as exc:
        raise HostError(f"The system couldn't start that action ({exc.strerror or exc}).") from None


def reveal(path: str, system: Optional[str] = None) -> None:
    """Show *path* selected in the system's file manager."""
    name = platform_name(system)
    if not capabilities(name)["reveal"]:
        raise HostUnsupported("Showing a file in its folder isn't available on this system. "
                              "Download the file instead.")
    result = _execute(reveal_args(path, name))
    # explorer.exe returns 1 even when it opened the folder, so its exit code means nothing.
    if name != "Windows" and result.returncode:
        raise HostError("The file manager didn't open. Try again.")


def copy_file(path: str, system: Optional[str] = None) -> None:
    """Put the file at *path* (not its name) on the clipboard."""
    name = platform_name(system)
    args = copy_args(path, name)
    result = _execute(args, {COPY_ENV: path} if name == "Windows" else None)
    if result.returncode:
        raise HostError("Couldn't copy the file to the clipboard. Download it instead.")
