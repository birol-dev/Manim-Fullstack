"""Small file helpers shared by the service, the export queue and the preview worker. No Manim.

* ``tree_fingerprint``: a portable hash of file names and contents (cache keys, reloads).
* ``png_size``: width and height from a PNG header.
* ``slugify``: a safe, readable file-name stem.
* ``prune_previews``: keep the preview cache under a file count.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import unicodedata
from datetime import datetime, timezone
from typing import Optional

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp")


class ImageCropStore:
    """Immutable per-image crop recipes, outside the public assets folder.

    Content hashes discard stale recipes after an asset is replaced. Missing or
    damaged metadata is optional: the image itself remains usable. No crop recipe
    changes a template parameter or an MCP image response.
    """

    def __init__(self, workspace: str, assets: str):
        from workspace_paths import safe_join
        self.assets = assets
        self.directory = safe_join(workspace, "studio", "image-crops")

    def image_path(self, name: str) -> str:
        from workspace_paths import safe_basename, safe_join
        if not isinstance(name, str):
            raise ValueError("Use an image file name from this workspace.")
        name = safe_basename(name)
        if not name.lower().endswith(IMAGE_SUFFIXES) or name.startswith("."):
            raise ValueError("Use an image file name from this workspace.")
        return safe_join(self.assets, name)

    def record_path(self, name: str) -> str:
        from workspace_paths import fold_filename, safe_join
        self.image_path(name)
        key = hashlib.sha256(fold_filename(name).encode("utf-8")).hexdigest()
        return safe_join(self.directory, key + ".json")

    @staticmethod
    def recipe(data: dict) -> dict:
        if not isinstance(data, dict) or set(data) != {"source", "position", "ratio", "shape"}:
            raise ValueError("A crop needs a source image, position, ratio and shape.")
        position = data.get("position")
        if not isinstance(position, dict) or set(position) != {"x", "y", "zoom"}:
            raise ValueError("Use a photo position with x, y and zoom.")
        for value, low, high in [(position["x"], -1, 1), (position["y"], -1, 1),
                                 (position["zoom"], 1, 4), (data["ratio"], .0001, 10000)]:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError("Use a valid crop position, 1 to 4 times zoom and a positive ratio.")
        shape = data["shape"]
        if not isinstance(shape, str) or (shape not in ("circle", "free") and not re.fullmatch(r"[1-9][0-9]{0,3}:[1-9][0-9]{0,3}", shape)):
            raise ValueError("Use a circle, free crop, or a positive aspect ratio.")
        fixed = 1 if shape == "circle" else float(shape.split(":")[0]) / float(shape.split(":")[1]) if ":" in shape else None
        if fixed is not None and not math.isclose(data["ratio"], fixed, rel_tol=1e-9):
            raise ValueError("The crop ratio must match the photo slot.")
        return {"source": data["source"], "position": dict(position), "ratio": data["ratio"], "shape": shape}

    @staticmethod
    def _digest(path: str) -> str:
        with open(path, "rb") as image:
            return hashlib.file_digest(image, "sha256").hexdigest()

    def read(self, name: str) -> Optional[dict]:
        """Return a current recipe, or None if its record/source is missing or unusable.

        The derived image is independent: explicit deletion of its original must
        leave it usable, with Adjust starting afresh from that derived image.
        """
        from workspace_paths import fold_filename
        try:
            path = self.record_path(name)
            if os.path.islink(path):
                return None
            with open(path, "r", encoding="utf-8") as record:
                data = json.loads(record.read(16385))
            if not isinstance(data, dict) or set(data) != {"version", "name", "crop", "source_hash", "image_hash"}:
                return None
            if type(data["version"]) is not int or data["version"] != 1 or not isinstance(data["name"], str) or fold_filename(data["name"]) != fold_filename(name):
                return None
            crop = self.recipe(data["crop"])
            source = self.image_path(crop["source"])
            if fold_filename(crop["source"]) == fold_filename(name):
                return None
            if self._digest(source) != data["source_hash"] or self._digest(self.image_path(name)) != data["image_hash"]:
                return None
            return crop
        except (OSError, ValueError, TypeError, KeyError, RecursionError):
            return None

    def write(self, name: str, data: dict) -> dict:
        import file_ops
        from workspace_paths import fold_filename
        crop = self.recipe(data)
        path, source = self.image_path(name), self.image_path(crop["source"])
        if fold_filename(name) == fold_filename(crop["source"]):
            raise ValueError("A crop must be stored as a new image.")
        record = self.record_path(name)
        # Shared with asset deletion/overwrite: a recipe cannot be committed
        # after its source disappears, and a delete cannot race this write.
        with file_ops.locked(path, source):
            if not os.path.isfile(path) or not os.path.isfile(source):
                raise FileNotFoundError("The crop or its original image is missing.")
            if self.read(crop["source"]) is not None:
                raise ValueError("Adjust the original image rather than a previous crop.")
            if self.referring_crops(name):
                raise ValueError("This image is an original used by another crop. Upload a new crop first.")
            existing = self.read(name)
            if existing is not None:
                if existing == crop:
                    return existing
                raise FileExistsError("This image already has a different crop recipe. Upload a new crop first.")
            data = {"version": 1, "name": name, "crop": crop,
                    "source_hash": self._digest(source), "image_hash": self._digest(path)}
            os.makedirs(self.directory, exist_ok=True)
            file_ops.atomic_write(record, json.dumps(data, allow_nan=False).encode("utf-8"))
        return crop

    def referring_crops(self, source_name: str) -> list[str]:
        """Live crops that need this original. Bad records cannot pin arbitrary paths."""
        from workspace_paths import fold_filename, safe_join
        self.image_path(source_name)
        try:
            records = list(os.scandir(self.directory))
        except FileNotFoundError:
            return []
        found = []
        for entry in records:
            if not re.fullmatch(r"[0-9a-f]{64}\.json", entry.name) or entry.is_symlink():
                continue
            try:
                with open(safe_join(self.directory, entry.name), "r", encoding="utf-8") as record:
                    data = json.loads(record.read(16385))
                name = data.get("name") if isinstance(data, dict) else None
                if not isinstance(name, str) or self.record_path(name) != entry.path:
                    continue
                raw_crop = data.get("crop")
                raw_source = raw_crop.get("source") if isinstance(raw_crop, dict) else None
                if not isinstance(raw_source, str) or fold_filename(raw_source) != fold_filename(source_name):
                    continue
                crop = self.read(name)
                if crop and fold_filename(crop["source"]) == fold_filename(source_name):
                    found.append(name)
            except (OSError, ValueError, TypeError, RecursionError):
                continue
        return found

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


def visual_source(data: bytes) -> bytes:
    """Remove explicitly marked audio-only additions, preserving legacy bake hashes.

    These markers may contain imports, cue calls and sound setup only. Visual
    layout/timing changes MUST remain unmarked. Runtime reloads hash full source.
    """
    result, audio = [], False
    for line in data.replace(b"\r\n", b"\n").splitlines(keepends=True):
        if line.strip() == b"# studio-audio-begin":
            audio = True
        elif line.strip() == b"# studio-audio-end":
            audio = False
        elif not audio and not line.rstrip().endswith(b"# studio-audio"):
            result.append(line)
    if audio:
        raise ValueError("Unclosed studio-audio source block")
    return b"".join(result)


def _stat_into(digest, path: str, visual_only=False) -> None:
    try:
        with open(path, "rb") as source:
            if path.endswith((".py", ".svg", ".json", ".txt", ".md")):
                # Git may check source out as LF or CRLF; neither changes the render.
                data = source.read().replace(b"\r\n", b"\n")
                digest.update(visual_source(data) if visual_only and path.endswith(".py") else data)
                digest.update(b";")
                return
            for chunk in iter(lambda: source.read(128 * 1024), b""):
                digest.update(chunk)
    except OSError:
        digest.update(b"?")
        return
    digest.update(b";")


def tree_fingerprint(*roots: str, visual_only=False) -> str:
    """Hash of every file's relative path and contents under *roots* (files or folders).

    ``__pycache__`` folders, dot files and ``.pyc`` files are ignored, so importing a
    module doesn't change its fingerprint.
    """
    digest = hashlib.sha256()
    for root in roots:
        digest.update(os.path.basename(root).encode() + b"|")
        if os.path.isfile(root):
            _stat_into(digest, root, visual_only)
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
                _stat_into(digest, os.path.join(dirpath, name), visual_only)
    return digest.hexdigest()[:16]


def template_dir(template_id: str) -> str:
    return os.path.join(TEMPLATES_DIR, template_id)


def visual_tree_fingerprint(*roots: str) -> str:
    return tree_fingerprint(*roots, visual_only=True)


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
        if name.endswith((".png", ".mp4")):
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
