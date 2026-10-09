"""Path safety helpers for workspace, asset, and media file operations."""

from __future__ import annotations

import os
import re
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

SCRIPT_SUFFIX = ".py"

# Characters that count as a space for the "starts / ends with a space" and
# "space before .py" rules: exactly what str.isspace() accepts, which covers all
# of Unicode category Zs (NBSP U+00A0, U+1680, U+2000-U+200A, U+202F, U+205F,
# U+3000) plus ASCII whitespace, U+0085 and U+2028/U+2029. Spelled out so the
# frontend (WHITESPACE in frontend/src/lib/format.ts) can use the same list.
WHITESPACE_CHARS = (
    "\t\n\x0b\x0c\r\x1c\x1d\x1e\x1f \x85\xa0\u1680"
    + "".join(chr(code) for code in range(0x2000, 0x200B))
    + "\u2028\u2029\u202f\u205f\u3000"
)


def _ends_with_space_or_dot(name: str) -> bool:
    return bool(name) and (name[-1] == "." or name[-1] in WHITESPACE_CHARS)

# COM1 / LPT1 written with any Unicode digit (COM¹, LPT², ＣＯＭ１, COM١) after NFKC.
_DEVICE_WITH_DIGIT = re.compile(r"(?:COM|LPT)\d")


def _is_reserved_device_name(name: str, *, nfkc: bool = False) -> bool:
    """Windows reserves device names with any extension (CON.py, con.tar.py, COM1.mp4).

    With *nfkc* the check runs on the NFKC form, so superscript and fullwidth
    digits/letters count too (COM¹.py, ＣＯＭ１.py, COM١.py). That stricter form is
    only applied to new names, so existing files named like that stay reachable.
    """
    if nfkc:
        name = unicodedata.normalize("NFKC", name)
    base = name.split(".", 1)[0].rstrip(WHITESPACE_CHARS if nfkc else " ").upper()
    return base in WINDOWS_RESERVED_NAMES or bool(_DEVICE_WITH_DIGIT.fullmatch(base))


def fold_filename(name: str) -> str:
    """Key for "same name" checks: NFC, then lower case. Mirrored by foldFilename() in
    frontend/src/lib/format.ts, so both sides agree which names collide."""
    return unicodedata.normalize("NFC", name).lower()


def nfc_filename(name: Optional[str]) -> Optional[str]:
    """*name* in Unicode NFC (None stays None). New names are stored in this form."""
    return None if name is None else unicodedata.normalize("NFC", str(name))


def to_script_name(raw: str) -> str:
    """The script name the user meant: NFC, with exactly one lowercase ``.py``.

    ``Foo.PY`` -> ``Foo.py``; ``intro`` -> ``intro.py``. Nothing is trimmed, and a
    name ending with a dot or space ("x.py.", "x.py ") is returned unchanged so that
    :func:`validate_new_filename` refuses it instead of it turning into "x.py..py".
    Mirrors toScriptName() in the frontend (which additionally trims what was typed).
    """
    name = unicodedata.normalize("NFC", str(raw))
    if _ends_with_space_or_dot(name):
        return name
    if name.lower().endswith(SCRIPT_SUFFIX):
        return name[: -len(SCRIPT_SUFFIX)] + SCRIPT_SUFFIX
    return name + SCRIPT_SUFFIX


def _has_control_or_format_char(name: str) -> bool:
    """Control characters (newline, tab, DEL, ...), invisible format characters
    such as U+202E (right-to-left override, used to disguise extensions), and the
    line / paragraph separators U+2028 and U+2029."""
    return any(unicodedata.category(ch) in ("Cc", "Cf", "Zl", "Zp") for ch in name)


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

    if _is_reserved_device_name(name):
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
    if name[0] in WHITESPACE_CHARS or name[-1] in WHITESPACE_CHARS:
        # Any Unicode space (NBSP, U+3000, ...), not only " ". Only for new names,
        # so an existing file named like that can still be opened and renamed.
        raise UnsafePathError("Filename cannot start or end with a dot or space.")
    if name != unicodedata.normalize("NFC", name):
        raise UnsafePathError("Filename must use the standard Unicode form (NFC).")
    if _is_reserved_device_name(name, nfkc=True):
        raise UnsafePathError(f"Filename '{name}' is a reserved device name.")
    stem = name[: -len(required_suffix)] if required_suffix else os.path.splitext(name)[0]
    if stem != stem.rstrip("." + WHITESPACE_CHARS):
        raise UnsafePathError("Filename cannot end with a dot or space before the extension.")
    if name.startswith("-"):
        raise UnsafePathError("Filename cannot start with a dash.")
    if name.startswith("."):
        raise UnsafePathError("Filename cannot start with a dot.")
    if forbid_temp_prefix and name.lower().startswith(TEMP_SCRIPT_PREFIX):
        raise UnsafePathError(f"Filenames starting with '{TEMP_SCRIPT_PREFIX}' are reserved for scratch renders.")
    return name


def find_case_insensitive_match(directory: str, name: str) -> Optional[str]:
    """Name of an existing entry in *directory* that equals *name* ignoring case and
    Unicode normalization (NFC vs NFD) but is spelled differently, or None. Prevents
    Example.py next to example.py, or two lookalike "café.py" files, which collide on
    Windows and macOS."""
    folded = fold_filename(name)
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.name != name and fold_filename(entry.name) == folded:
                    return entry.name
    except OSError:
        return None
    return None
