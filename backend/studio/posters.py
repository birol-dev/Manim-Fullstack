"""Bundled, immutable gallery thumbnails. Looking one up never starts a renderer."""
from __future__ import annotations

import json
from pathlib import Path
import re

from .storage import STUDIO_DIR, png_size

POSTERS_DIR = Path(STUDIO_DIR) / "assets" / "posters"


def read_manifest(folder=None):
    try:
        value = json.loads((Path(folder or POSTERS_DIR) / "manifest.json").read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def manifest_stamp(folder):
    """Invalidate catalog metadata when a bake is replaced or a bundled file disappears."""
    try:
        directory = Path(folder).stat()
        manifest = (Path(folder) / "manifest.json").stat()
        return directory.st_mtime_ns, manifest.st_mtime_ns, manifest.st_size
    except OSError:
        return None


def name_for(card, aspect, default_aspect):
    name = f'{card["template"]}/{card["id"]}'
    return name if aspect == default_aspect else f"{name}@{aspect}"


def gallery_requests(catalog):
    """Default card artwork plus HomeHero's three exact aspect-ratio variants."""
    templates = {template["id"]: template for template in catalog["templates"]}
    seen = set()
    for template in templates.values():
        for card in template["presets"]:
            settings = {"aspect": template["default_aspect"], **card["settings"]}
            name = name_for(card, settings["aspect"], settings["aspect"])
            seen.add(name)
            yield name, card, settings
    pools = [section["cards"] for section in catalog["sections"] if section["cards"]]
    picks = []
    for round_index in range(4):
        for pool in pools:
            if round_index < len(pool) and len(picks) < 3:
                card = pool[round_index]
                if not any(old["template"] == card["template"] and old["id"] == card["id"] for old in picks):
                    picks.append(card)
    for index, card in enumerate(picks):
        template = templates[card["template"]]
        wanted = "9:16" if index == 1 else "16:9"
        aspect = wanted if wanted in template["aspects"] else template["default_aspect"]
        default_aspect = card["settings"].get("aspect", template["default_aspect"])
        name = name_for(card, aspect, default_aspect)
        if name not in seen:
            seen.add(name)
            yield name, card, {**card["settings"], "aspect": aspect}


def current_assets(service, card, settings, manifest, folder=None, *, job=None, files=None):
    """Publish only files matching the current template, content, theme and shape."""
    default_aspect = settings["aspect"]
    assets = {}
    for aspect in ("16:9", "9:16", "1:1", "4:5"):
        name = name_for(card, aspect, default_aspect)
        key = manifest.get(name)
        if not isinstance(key, str) or not re.fullmatch(r"[a-f0-9]{32}", key):
            continue
        if job is None:
            spec, params, validated, _ = service._validate(card["template"], card["params"], {**settings, "aspect": aspect})
        else:
            spec, params, validated, _ = job
            if aspect not in spec.meta.aspects:
                continue
            validated = {**validated, "aspect": aspect}
        if key != service._preview_key(spec, params, validated, "poster", service.poster_short, files=files):
            continue
        size = png_size(str(Path(folder or POSTERS_DIR) / f"{key}.png"))
        if size:
            assets[aspect] = {"url": f"/api/studio/posters/{key}.png", "width": size[0], "height": size[1]}
    return assets


def asset_path(key, folder=None):
    """A manifest-listed image under the installation directory; no catalog scan or cache copy."""
    folder = Path(folder or POSTERS_DIR)
    if not isinstance(key, str) or not re.fullmatch(r"[a-f0-9]{32}", key):
        return None
    path = folder / f"{key}.png"
    if key in read_manifest(folder).values() and png_size(str(path)):
        return path
    return None
