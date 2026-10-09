"""Path safety helpers for workspace, asset, and media file operations."""

from __future__ import annotations

import os
import unicodedata
from pathlib import Path
from typing import Optional


class UnsafePathError(ValueError):
    """Raised when a user-supplied path is empty, absolute, or escapes a root."""


def is_within_directory(path: str, directory: str) -> bool:
    """Return True if *path* resolves inside *directory* (not a sibling prefix)."""
    try:
        resolved_path = Path(path).resolve()
        resolved_dir = Path(directory).resolve()
        return resolved_path.is_relative_to(resolved_dir)
    except (OSError, RuntimeError, ValueError):
        return False


def safe_join(directory: str, *parts: str) -> str:
    """Join *parts* onto *directory* and reject results that escape it."""
    candidate = os.path.abspath(os.path.join(directory, *parts))
    if not is_within_directory(candidate, directory):
        raise UnsafePathError("Path escapes the allowed directory.")
    return candidate


WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(10)),
    *(f"LPT{i}" for i in range(10)),
    "CONIN$",
    "CONOUT$",
}

# Characters Windows forbids in file names. Linux accepts them, but a workspace
# should survive being copied to any OS (and ":" means a drive on Windows).
RESERVED_FILENAME_CHARS = frozenset('<>:"|?*')

MAX_FILENAME_BYTES = 255  # common filesystem limit for one path segment
MAX_FILENAME_STEM_CHARS = 100

# Scratch copies of unsaved code are named like this. A user script with the
# same prefix would be hidden from the file list and swept at startup.
TEMP_SCRIPT_PREFIX = "_temp_run_"


def _has_control_or_format_char(name: str) -> bool:
    """Control characters (newline, tab, DEL, ...) and invisible format characters
    such as U+202E (right-to-left override, used to disguise extensions)."""
    return any(unicodedata.category(ch) in ("Cc", "Cf") for ch in name)


def safe_basename(
    filename: Optional[str], *, required_suffix: Optional[str] = None
) -> str:
    """Return a single, portable path segment or raise :class:`UnsafePathError`.

    Use this to *refer to* a file (read, delete, the source of a rename). Names
    for files that are about to be created go through :func:`validate_new_filename`,
    which adds the creation-only rules on top.
    """
    if filename is None or not str(filename).strip():
        raise UnsafePathError("Filename is required.")

    filename_str = str(filename)
    if filename_str.endswith(".") or filename_str.endswith(" ") or filename_str.startswith(" "):
        raise UnsafePathError("Filename cannot start or end with a dot or space.")

    raw = filename_str.replace("\\", "/")
    if raw.startswith("/") or (len(raw) >= 2 and raw[1] == ":"):
        raise UnsafePathError("Absolute paths are not allowed.")

    name = os.path.basename(raw)
    if not name or name in {".", ".."} or name != raw:
        raise UnsafePathError("Filename cannot contain folders or path separators.")
    if "\x00" in name or _has_control_or_format_char(name):
        raise UnsafePathError("Filename cannot contain control or invisible characters.")

    bad = sorted({ch for ch in name if ch in RESERVED_FILENAME_CHARS})
    if bad:
        raise UnsafePathError(f"Filename cannot contain {' '.join(bad)}.")

    if len(name.encode("utf-8")) > MAX_FILENAME_BYTES:
        raise UnsafePathError(f"Filename is too long (max {MAX_FILENAME_BYTES} bytes).")
    if required_suffix and name.endswith(required_suffix):
        stem = name[: -len(required_suffix)]
    else:
        stem = os.path.splitext(name)[0]
    if len(stem) > MAX_FILENAME_STEM_CHARS:
        raise UnsafePathError(f"Filename is too long (max {MAX_FILENAME_STEM_CHARS} characters before the extension).")
    if not stem.strip("."):
        raise UnsafePathError("Filename needs a name before the extension.")

    # Windows reserves device names with any extension (CON.py, con.tar.py, COM1.mp4).
    if name.split(".", 1)[0].rstrip(" ").upper() in WINDOWS_RESERVED_NAMES:
        raise UnsafePathError(f"Filename '{name}' is a reserved device name.")

    if required_suffix and not name.endswith(required_suffix):
        raise UnsafePathError(f"File must end with {required_suffix}.")
    return name


def validate_new_filename(
    filename: Optional[str],
    *,
    required_suffix: Optional[str] = None,
    forbid_temp_prefix: bool = False,
) -> str:
    """Validate the name of a file that is about to be created (save, rename target,
    upload, render). Adds rules that only matter for new names, so files that
    already exist with a legacy name can still be opened, renamed, or deleted."""
    name = safe_basename(filename, required_suffix=required_suffix)
    if name.startswith("-"):
        raise UnsafePathError("Filename cannot start with a dash.")
    if name.startswith("."):
        raise UnsafePathError("Filename cannot start with a dot.")
    if forbid_temp_prefix and name.lower().startswith(TEMP_SCRIPT_PREFIX):
        raise UnsafePathError(f"Filenames starting with '{TEMP_SCRIPT_PREFIX}' are reserved for scratch renders.")
    return name


def find_case_insensitive_match(directory: str, name: str) -> Optional[str]:
    """Name of an existing entry in *directory* that equals *name* ignoring case
    but is spelled differently, or None. Prevents Example.py next to example.py,
    which collide on Windows and macOS."""
    folded = name.casefold()
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.name != name and entry.name.casefold() == folded:
                    return entry.name
    except OSError:
        return None
    return None
