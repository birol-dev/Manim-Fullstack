"""Read-only gallery peek lookup. Importing/checking this module never starts a worker."""
from __future__ import annotations

import json
from pathlib import Path

from .storage import STUDIO_DIR

PEEKS_DIR = Path(STUDIO_DIR) / "assets" / "peeks"
VERSION = 1
LONG_SIDE = 480
FPS = 15
MAX_DURATION = 4.5
MAX_FILE_BYTES = 300_000
MAX_TOTAL_BYTES = 8_000_000
# 29 presets currently: <= 7.25 MB of movies, leaving room for the manifest.
TARGET_FILE_BYTES = 250_000


def peek_key(service, card, settings):
    spec, params, validated, _ = service._validate(card["template"], card["params"], settings)
    return service._preview_key(spec, params, validated,
                                f"peek-v{VERSION}-{FPS}-{MAX_DURATION}-{TARGET_FILE_BYTES}", LONG_SIDE)


def read_manifest(folder=None):
    try:
        value = json.loads((Path(folder or PEEKS_DIR) / "manifest.json").read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def current_path(service, card, settings, manifest, folder=None):
    key = peek_key(service, card, settings)
    name = f'{card["template"]}/{card["id"]}'
    path = Path(folder or PEEKS_DIR) / f"{key}.mp4"
    try:
        if manifest.get(name) == key and path.is_file() and 0 < path.stat().st_size <= MAX_FILE_BYTES:
            return path
    except OSError:
        pass
    return None


def check_baked(service, folder=None):
    """Missing/stale presets plus size violations; works without Manim/FFmpeg."""
    from .bake_posters import preset_requests

    folder = Path(folder or PEEKS_DIR)
    manifest = read_manifest(folder)
    problems = [f'{card["template"]}/{card["id"]}' for card, settings in preset_requests(service)
                if current_path(service, card, settings, manifest, folder) is None]
    total = 0
    for path in folder.rglob("*"):
        if path.is_file():
            size = path.stat().st_size
            total += size
            if path.suffix == ".mp4" and size > MAX_FILE_BYTES:
                problems.append(f"{path.name}: exceeds {MAX_FILE_BYTES} bytes")
    if total > MAX_TOTAL_BYTES:
        problems.append(f"peeks folder: {total} bytes exceeds {MAX_TOTAL_BYTES}")
    return problems
