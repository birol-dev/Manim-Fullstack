"""Path safety helpers for workspace, asset, and media file operations."""

from __future__ import annotations

import os
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
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}


def safe_basename(
    filename: Optional[str], *, required_suffix: Optional[str] = None
) -> str:
    """Return a single path segment, rejecting separators, parent references, and device names."""
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
        raise UnsafePathError("Invalid filename.")
    if "\x00" in name:
        raise UnsafePathError("Invalid filename.")

    # Disallow Windows reserved device names (e.g. CON, NUL, AUX, COM1)
    stem = Path(name).stem.upper()
    if stem in WINDOWS_RESERVED_NAMES:
        raise UnsafePathError(f"Filename '{name}' is a reserved device name.")

    if required_suffix and not name.endswith(required_suffix):
        raise UnsafePathError(f"File must end with {required_suffix}.")
    return name
