"""Bake gallery posters: run ``python -m backend.studio.bake_posters`` at the repo root."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from .service import StudioService
from .storage import STUDIO_DIR

POSTERS_DIR = Path(STUDIO_DIR) / "assets" / "posters"
BAKE_COMMAND = "python -m backend.studio.bake_posters"


def preset_requests(service):
    """Exactly Gallery.cardSettings: default aspect, followed by the preset's settings."""
    for template in service._catalog_sync()["templates"]:
        for card in template["presets"]:
            yield card, {"aspect": template["default_aspect"], **card["settings"]}


def check_baked(service, folder=POSTERS_DIR):
    """Return missing/stale preset names; usable without Manim, including in CI."""
    try:
        manifest = json.loads((Path(folder) / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manifest = {}
    problems = []
    for card, settings in preset_requests(service):
        spec, params, validated, _ = service._validate(card["template"], card["params"], settings)
        key = service._preview_key(spec, params, validated, "poster", service.poster_short)
        name = f'{card["template"]}/{card["id"]}'
        if manifest.get(name) != key or not (Path(folder) / f"{key}.png").is_file():
            problems.append(name)
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path,
                        default=Path(STUDIO_DIR).parents[1] / "workspace" / "studio" / "tmp" / "poster-bake")
    args = parser.parse_args()
    POSTERS_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {}
    service = StudioService(str(args.work_dir))
    try:
        for card, settings in preset_requests(service):
            result = service.preview_sync(card["template"], card["params"], settings)
            key = Path(result["path"]).stem
            shutil.copyfile(result["path"], POSTERS_DIR / f"{key}.png")
            name = f'{card["template"]}/{card["id"]}'
            manifest[name] = key
            print(f"Baked {name}: {key}", flush=True)
    finally:
        service.shutdown_sync()
    temporary = POSTERS_DIR / ".manifest.json"
    temporary.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    temporary.replace(POSTERS_DIR / "manifest.json")
    for path in POSTERS_DIR.glob("*.png"):
        if path.stem not in manifest.values():
            path.unlink()
    print(f"Baked {len(manifest)} gallery posters.")


if __name__ == "__main__":
    main()
