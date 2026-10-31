"""Portable project files: one ``.manimstudio`` zip holding a project and its assets.

    <title>.manimstudio
        project.json          format version, app version, template, title, params, settings, crops
        assets/<name>         every image, logo and sound the project names (and crop sources)

The zip contains nothing about the computer it was made on: no project id, no
timestamps, no folder paths. Asset references are found by walking the template's
real params schema and the render settings, not by guessing from field names.
``crops`` is optional: a cropped photo's recipe, so the crop opens on another computer.

Opening one treats the bytes as untrusted. Names, entry count, entry sizes and
compression ratios are checked before anything is extracted, and every read is
bounded. A reader never writes to disk; the service hands each asset to the same
validator an upload uses.
"""

from __future__ import annotations

import base64
import binascii
import io
import json
import os
import re
import stat
import unicodedata
import zipfile
from dataclasses import dataclass
from typing import Optional

from . import registry
from .errors import StudioError
from .schema import RenderSettings
from .storage import slugify
from .version import APP_VERSION

FORMAT_VERSION = 1
PROJECT_ENTRY = "project.json"
ASSETS_PREFIX = "assets/"
MAX_ENTRIES = 200
MAX_ENTRY_BYTES = 50 * 1024 * 1024
MAX_TOTAL_BYTES = 400 * 1024 * 1024
MAX_PROJECT_BYTES = 256 * 1024
MAX_FILE_BYTES = 200 * 1024 * 1024
MAX_RATIO = 200
RATIO_FLOOR = 1024 * 1024
MAX_DEPTH = 16
MAX_TITLE = 120
MAX_ASSET_NAME = 200

_DAMAGED = "This file is damaged and can't be opened. Save it again from Manim Studio."
_UNSAFE = "This file isn't safe to open. Save it again from Manim Studio."
_UNEXPECTED = "This file contains something Manim Studio didn't put there."
_NO_DESIGN = ("This video uses a design this app doesn't have yet. "
              "Update the app, then open it again.")
_NEWER = ("This file was made by a newer version of Manim Studio. "
          "Update the app, then open it again.")


class PortableError(StudioError):
    """A portable file that cannot be opened; the message is ready to show people."""

    status = 422


class PortableTooLarge(PortableError):
    status = 413


@dataclass(frozen=True)
class AssetRef:
    """One place a project names an asset: where it is, and whether the name is usable."""

    kind: str  # "image" or "audio"
    name: str
    section: str  # "params" or "settings"
    path: tuple

    @property
    def safe_name(self) -> Optional[str]:
        return asset_name(self.name)


# -- names and titles ----------------------------------------------------------------------

def asset_name(value) -> Optional[str]:
    """The name of a single asset file, or None for anything that could be a path."""
    if not isinstance(value, str) or not value or len(value) > MAX_ASSET_NAME:
        return None
    if value in (".", "..") or value.startswith(".") or "/" in value or "\\" in value:
        return None
    if re.match(r"^[A-Za-z]:", value) or "\x00" in value:
        return None
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        return None
    return value


def safe_title(value, fallback: str = "Untitled video") -> str:
    if not isinstance(value, str):
        return fallback
    title = value.strip()[:MAX_TITLE]
    return title or fallback


def unique_title(title: str, existing) -> str:
    """*title*, or ``"<title> (copy)"`` when a video already has that name (and on up)."""
    titles = {str(item).strip().casefold() for item in existing if isinstance(item, str)}
    candidate = safe_title(title)
    for _attempt in range(20):
        if candidate.casefold() not in titles:
            return candidate
        stem = candidate[: MAX_TITLE - len(" (copy)")].rstrip()
        candidate = f"{stem or 'Untitled video'} (copy)"
    return candidate


def file_name(title) -> str:
    """A portable file name that is safe on every computer."""
    return slugify(title, fallback="video") + ".manimstudio"


# -- finding the assets a project names ----------------------------------------------------

def _resolve(node: dict, definitions: dict, depth: int = 0) -> dict:
    """Follow ``$ref`` and the object arm of ``anyOf`` (Pydantic's Optional models)."""
    for _step in range(8):
        if depth > MAX_DEPTH or not isinstance(node, dict):
            return {}
        ref = node.get("$ref")
        if isinstance(ref, str):
            key = ref.rsplit("/", 1)[-1]
            node = definitions.get(key) or {}
            depth += 1
            continue
        arms = [item for item in (node.get("anyOf") or []) + (node.get("oneOf") or [])
                if isinstance(item, dict)]
        objects = []
        for arm in arms:
            resolved = _resolve(arm, definitions, depth + 1)
            if resolved.get("type") == "object" or "properties" in resolved:
                objects.append(resolved)
        if objects and not node.get("properties"):
            node = objects[0]
            depth += 1
            continue
        break
    return node if isinstance(node, dict) else {}


def _walk(schema: dict, value, path: tuple, definitions: dict, section: str,
          found: list, depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        return
    node = _resolve(schema, definitions, depth)
    if node.get("x-widget") == "image":
        if isinstance(value, str) and value:
            found.append(AssetRef("image", value, section, path))
        return
    if isinstance(value, dict):
        properties = node.get("properties") or {}
        for key, child in value.items():
            if key in properties:
                _walk(properties[key], child, (*path, key), definitions, section, found, depth + 1)
    elif isinstance(value, list):
        items = node.get("items") or {}
        for index, child in enumerate(value):
            _walk(items, child, (*path, index), definitions, section, found, depth + 1)


def _nested(value, *keys):
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def project_refs(template_id: str, params, settings) -> list:
    """Every image, logo and sound the params and settings name, in document order."""
    spec = registry.get_template(template_id)
    found: list = []
    params = params if isinstance(params, dict) else {}
    settings = settings if isinstance(settings, dict) else {}

    schema = spec.params_model.model_json_schema()
    _walk(schema, params, (), schema.get("$defs") or {}, "params", found)

    render_schema = RenderSettings.model_json_schema()
    _walk(render_schema, settings, (), render_schema.get("$defs") or {}, "settings", found)

    logo = _nested(settings, "brand", "logo")
    if isinstance(logo, str) and logo:
        found.append(AssetRef("image", logo, "settings", ("brand", "logo")))
    music = _nested(settings, "sound", "music", "asset")
    if isinstance(music, str) and music:
        found.append(AssetRef("audio", music, "settings", ("sound", "music", "asset")))
    return found


def asset_names(refs) -> list:
    """The usable, distinct asset names the refs mention, in a stable order."""
    names = []
    for ref in refs:
        name = ref.safe_name
        if name and name not in names:
            names.append(name)
    return names


def _set_path(document, path: tuple, value) -> None:
    if not path or not isinstance(document, (dict, list)):
        return
    target = document
    for key in path[:-1]:
        if isinstance(target, dict):
            if key not in target:
                return
            target = target[key]
        elif isinstance(target, list) and isinstance(key, int) and 0 <= key < len(target):
            target = target[key]
        else:
            return
    last = path[-1]
    if isinstance(target, dict):
        if last in target:
            target[last] = value
    elif isinstance(target, list) and isinstance(last, int) and 0 <= last < len(target):
        target[last] = value


def apply_asset_names(params: dict, settings: dict, refs, replacements: dict) -> None:
    """Rewrite every reference to the name the asset was stored under (None = default)."""
    for ref in refs:
        document = params if ref.section == "params" else settings
        _set_path(document, ref.path, replacements.get((ref.kind, ref.name)))


# -- saving --------------------------------------------------------------------------------

def project_document(project: dict, title: str) -> dict:
    """The exact JSON a portable file carries: nothing about this computer."""
    params = project.get("params")
    settings = project.get("settings")
    return {
        "format": FORMAT_VERSION,
        "app_version": APP_VERSION,
        "template": project.get("template"),
        "title": title,
        "params": params if isinstance(params, dict) else {},
        "settings": settings if isinstance(settings, dict) else {},
    }


def _asset_path(assets_dir: str, name: str) -> Optional[str]:
    name = asset_name(name)
    if name is None:
        return None
    root = os.path.realpath(assets_dir)
    path = os.path.realpath(os.path.join(root, name))
    try:
        if os.path.commonpath([root, path]) != root:
            return None
    except ValueError:
        return None
    return path if os.path.isfile(path) and not os.path.islink(os.path.join(root, name)) else None


def missing_assets(refs, assets_dir: str) -> list:
    """Names the project names that are not readable files in the workspace's assets."""
    missing = []
    for name in asset_names(refs):
        if _asset_path(assets_dir, name) is None and name not in missing:
            missing.append(name)
    return missing


def crop_recipes(refs, assets_dir: str, store) -> dict:
    """Crop recipes for the images the file can carry, by the name the project uses.

    A recipe's source picture must travel too, or the store on the other computer
    refuses the recipe: only recipes whose source is also a readable asset count.
    """
    recipes = {}
    for name in asset_names(ref for ref in refs if ref.kind == "image"):
        if _asset_path(assets_dir, name) is None:
            continue
        recipe = store.read(name)
        if not isinstance(recipe, dict) or _asset_path(assets_dir, recipe.get("source")) is None:
            continue
        recipes[name] = recipe
    return recipes


def write_file(path: str, document: dict, assets_dir: str, refs) -> list:
    """Write the zip; returns the asset names that are missing from *assets_dir*."""
    names = asset_names(refs)
    crops = document.get("crops")
    if isinstance(crops, dict):
        for recipe in crops.values():
            source = asset_name(recipe.get("source")) if isinstance(recipe, dict) else None
            if source and source not in names:
                names.append(source)
    missing = []
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(PROJECT_ENTRY, json.dumps(document, ensure_ascii=False, indent=1).encode("utf-8"))
        for name in names:
            source = _asset_path(assets_dir, name)
            if source is None:
                missing.append(name)
                continue
            archive.write(source, ASSETS_PREFIX + name)
    return missing


def missing_note(names) -> Optional[str]:
    """One plain sentence for assets the save had to leave out."""
    if not names:
        return None
    listed = ", ".join(names)
    if len(names) == 1:
        return f"Saved, but this file wasn't on this computer: {listed}. The design's default shows there."
    return (f"Saved, but these files weren't on this computer: {listed}. "
            "The design's default shows in their places.")


def problem_note(names) -> Optional[str]:
    """One plain sentence for assets an opened project had to replace."""
    if not names:
        return None
    listed = ", ".join(names)
    if len(names) == 1:
        return f"One file couldn't be used, so the design's default is in its place: {listed}."
    return f"Some files couldn't be used, so the design's default is in their places: {listed}."


def crop_note(names) -> Optional[str]:
    """One plain sentence for photos whose crop this computer already had."""
    if not names:
        return None
    listed = ", ".join(names)
    if len(names) == 1:
        return f"{listed} already has a different crop on this computer, so the crop already here was kept."
    return (f"These photos already have different crops on this computer, "
            f"so the crops already here were kept: {listed}.")


# -- opening -------------------------------------------------------------------------------

def decode_upload(value) -> bytes:
    """The bytes of a base64 (or data-URL) portable file, within the 200 MB limit."""
    if not isinstance(value, str) or not value.strip():
        raise PortableError("Choose a Manim Studio file that ends in .manimstudio.")
    text = value.strip()
    if text.startswith("data:") and "," in text:
        text = text.split(",", 1)[1]
    if len(text) > MAX_FILE_BYTES * 4 // 3 + 8:
        raise PortableTooLarge("This file is larger than 200 MB and can't be opened.")
    try:
        data = base64.b64decode(text, validate=True)
    except (ValueError, binascii.Error):
        raise PortableError("That file couldn't be read. Choose it again.") from None
    if len(data) > MAX_FILE_BYTES:
        raise PortableTooLarge("This file is larger than 200 MB and can't be opened.")
    return data


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK(info.external_attr >> 16)


class ProjectArchive:
    """A checked, read-only view of a portable file. Every read is bounded."""

    def __init__(self, data: bytes):
        if not isinstance(data, (bytes, bytearray)) or not data:
            raise PortableError("Choose a Manim Studio file that ends in .manimstudio.")
        if len(data) > MAX_FILE_BYTES:
            raise PortableTooLarge("This file is larger than 200 MB and can't be opened.")
        self._buffer = io.BytesIO(bytes(data))
        try:
            self._zip = zipfile.ZipFile(self._buffer)
        except (zipfile.BadZipFile, OSError):
            raise PortableError("This isn't a Manim Studio file. Choose one that ends in .manimstudio.") from None
        self._entries: dict = {}
        self._check()

    def _check(self) -> None:
        infos = self._zip.infolist()
        if len(infos) > MAX_ENTRIES:
            raise PortableError(f"This file has too many parts to open ({len(infos)}).")
        total = 0
        seen = set()
        for info in infos:
            name = info.filename
            if not isinstance(name, str) or not name or "\\" in name or "\x00" in name:
                raise PortableError(_UNSAFE)
            if any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
                raise PortableError(_UNSAFE)
            if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
                raise PortableError(_UNSAFE)
            if _is_symlink(info):
                raise PortableError(_UNSAFE)
            if info.flag_bits & 0x1:
                raise PortableError(_UNSAFE)
            if info.is_dir():
                if name != ASSETS_PREFIX:
                    raise PortableError(_UNEXPECTED)
                continue
            parts = name.split("/")
            if any(part in ("", ".", "..") for part in parts):
                raise PortableError(_UNSAFE)
            if name != PROJECT_ENTRY and not (name.startswith(ASSETS_PREFIX) and len(parts) == 2):
                raise PortableError(_UNEXPECTED)
            if info.file_size > MAX_ENTRY_BYTES:
                raise PortableTooLarge(f"One file inside is too large to open: {parts[-1]}.")
            if info.file_size > RATIO_FLOOR and info.compress_size * MAX_RATIO < info.file_size:
                raise PortableError("This file is packed in a way Manim Studio doesn't open.")
            total += info.file_size
            if total > MAX_TOTAL_BYTES:
                raise PortableTooLarge("This file is too large to open when unpacked.")
            key = unicodedata.normalize("NFC", name).casefold()
            if key in seen:
                raise PortableError("This file has the same part twice.")
            seen.add(key)
            self._entries[name] = info
        if PROJECT_ENTRY not in self._entries:
            raise PortableError("This isn't a Manim Studio project file. Choose one that ends in .manimstudio.")

    def _read(self, info: zipfile.ZipInfo, limit: int) -> bytes:
        try:
            with self._zip.open(info) as entry:
                data = entry.read(limit + 1)
        except (zipfile.BadZipFile, RuntimeError, OSError, EOFError):
            raise PortableError(_DAMAGED) from None
        if len(data) > limit:
            raise PortableTooLarge(f"One file inside is too large to open: {info.filename.rsplit('/', 1)[-1]}.")
        if len(data) != info.file_size:
            raise PortableError(_DAMAGED)
        return data

    def project(self) -> dict:
        raw = self._read(self._entries[PROJECT_ENTRY], MAX_PROJECT_BYTES)
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise PortableError(_DAMAGED) from None
        if not isinstance(document, dict):
            raise PortableError(_DAMAGED)
        return document

    def asset(self, name: str) -> Optional[bytes]:
        """The bytes of asset *name*, or None when the file didn't include it."""
        name = asset_name(name)
        if name is None:
            return None
        info = self._entries.get(ASSETS_PREFIX + name)
        if info is None:
            return None
        return self._read(info, MAX_ENTRY_BYTES)

    def close(self) -> None:
        self._zip.close()
        self._buffer.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.close()
