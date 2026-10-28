"""Small file helpers shared by the service, the export queue and the preview worker. No Manim.

* ``tree_fingerprint``: a cheap hash of file names, sizes and mtimes (cache keys, reloads).
* ``png_size``: width and height from a PNG header.
* ``slugify``: a safe, readable file-name stem.
* ``prune_previews``: keep the preview cache under a file count.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
import unicodedata
from datetime import datetime, timezone
from typing import Optional

STUDIO_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(STUDIO_DIR, "templates")
KIT_DIR = os.path.join(STUDIO_DIR, "kit")
ASSETS_DIR = os.path.join(STUDIO_DIR, "assets")
FONTS_DIR = os.path.join(ASSETS_DIR, "fonts")
ICONS_DIR = os.path.join(ASSETS_DIR, "icons")

# What a warm worker loads once and can't re-import: the kit, the plain-data modules it
# reads, and the bundled fonts (registered with Pango once per process). A change here
# restarts the worker. Icons are read at render time, so they only change cache keys.
KIT_ROOTS = (
    KIT_DIR,
    os.path.join(STUDIO_DIR, "schema.py"),
    os.path.join(STUDIO_DIR, "themes.py"),
    os.path.join(STUDIO_DIR, "formats.py"),
    os.path.join(STUDIO_DIR, "numfmt.py"),
    FONTS_DIR,
)

# Temp files in the preview cache start with this (never served by name).
TEMP_MARK = ".~"


def _stat_into(digest, path: str) -> None:
    try:
        info = os.stat(path)
    except OSError:
        digest.update(b"?")
        return
    digest.update(f"{info.st_mtime_ns}:{info.st_size};".encode())


def tree_fingerprint(*roots: str) -> str:
    """Hash of every file's relative path, size and mtime under *roots* (files or folders).

    ``__pycache__`` folders, dot files and ``.pyc`` files are ignored, so importing a
    module doesn't change its fingerprint.
    """
    digest = hashlib.sha256()
    for root in roots:
        digest.update(os.path.basename(root).encode() + b"|")
        if os.path.isfile(root):
            _stat_into(digest, root)
            continue
        if not os.path.isdir(root):
            digest.update(b"-missing-")
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d != "__pycache__" and not d.startswith("."))
            rel = os.path.relpath(dirpath, root).replace("\\", "/")
            for name in sorted(filenames):
                if name.startswith(".") or name.endswith((".pyc", ".pyo")):
                    continue
                digest.update(f"{rel}/{name}=".encode())
                _stat_into(digest, os.path.join(dirpath, name))
    return digest.hexdigest()[:16]


def template_dir(template_id: str) -> str:
    return os.path.join(TEMPLATES_DIR, template_id)


def png_size(path: str) -> Optional[tuple]:
    """(width, height) of a PNG, or None if it isn't one."""
    try:
        with open(path, "rb") as f:
            head = f.read(24)
    except OSError:
        return None
    if len(head) < 24 or not head.startswith(b"\x89PNG\r\n\x1a\n") or head[12:16] != b"IHDR":
        return None
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


_SLUG_JUNK = re.compile(r"[^a-z0-9]+")


def slugify(text: Optional[str], fallback: str = "video", max_length: int = 40) -> str:
    """Lowercase ASCII words joined by dashes ("Happy New Year!" -> "happy-new-year")."""
    ascii_text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_JUNK.sub("-", ascii_text.lower()).strip("-")
    if len(slug) > max_length:
        slug = slug[:max_length].rsplit("-", 1)[0] or slug[:max_length]
    slug = slug.strip("-")
    if not slug:
        slug = _SLUG_JUNK.sub("-", fallback.lower()).strip("-") or "video"
    return slug


def utc_now() -> str:
    """ISO 8601 UTC with milliseconds, e.g. ``2026-10-28T15:59:00.123Z`` (sorts as text)."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def prune_previews(folder: str, keep: int, temp_age: float = 600.0) -> int:
    """Delete the oldest cached previews beyond *keep* PNGs (with their .json), and stale temp files.

    Returns how many previews were removed.
    """
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return 0
    now = time.time()
    pngs = []
    for entry in entries:
        name = entry.name
        try:
            mtime = entry.stat().st_mtime
        except OSError:
            continue
        if name.startswith(TEMP_MARK):
            if now - mtime > temp_age:
                _unlink(entry.path)
            continue
        if name.endswith(".png"):
            pngs.append((mtime, entry.path))
    if len(pngs) <= keep:
        return 0
    pngs.sort()
    removed = 0
    for _mtime, path in pngs[: len(pngs) - keep]:
        _unlink(os.path.splitext(path)[0] + ".json")
        if _unlink(path):
            removed += 1
    return removed


def _unlink(path: str) -> bool:
    try:
        os.unlink(path)
        return True
    except OSError:
        return False
