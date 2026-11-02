r"""Measure the brand logo against every gallery card, aspect and storyboard frame.

    python desktop/scripts/logo_check.py
    python desktop/scripts/logo_check.py --aspects 16:9,9:16 --jobs 4 --short 480
    python desktop/scripts/logo_check.py --no-animation

For every gallery card and every aspect this renders the poster twice through
``StudioService``: once without a logo and once with a solid magenta 2:1 test logo.
The difference between the two gives the logo's box; the same box, grown by 2 % of
the short side, is measured in each of the four corners of the no-logo poster. A
corner is clean when the pixels there are one flat or smooth background: low color
spread, a small residual against a smooth surface, and little edge content.

Templates whose content moves or appears late are also rendered as storyboards
(with and without the logo). The logo's box is located in each captured frame and
the no-logo frame is measured there too, because a corner that is clear on the
poster can still be covered later in the video.

The chosen region of each template (``logo_region`` / ``logo_height``, possibly a
dict per aspect) is read from its ``scene.py``. The process exits non-zero when a
chosen corner collides, when an animated frame is unclean, or when a render fails.

Output goes to a new folder under the system temp folder (or ``--out``):
``contact-sheet.png`` (one tile per template per aspect, with the logo) and
``failures/`` crops for anything unclean. The full path is printed at the end.

The thresholds below were tuned on real renders: year_in_review 16:9 bottom-right
("countries visited" card) measured spread 142 / residual 124 / edge 86, announcement
9:16 top-right ("THIS WEEKEND ONLY" pill) measured 202 / 172 / 46, while quote 1:1
top-right and quiz 4:5 bottom-left both measured 0 / 0 / 0.
"""

from __future__ import annotations

import argparse
import ast
import concurrent.futures
import itertools
import os
from pathlib import Path
import sys
import tempfile
import threading
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

TEST_LOGO = "logo-check.png"
ASPECT_ORDER = ("16:9", "9:16", "1:1", "4:5")
CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right")
MARGIN_SHARE = 0.02  # grow the measured box by 2 % of the short side
SPREAD_LIMIT = 30.0  # max channel (p99.5 - p0.5) in 0..255
RESIDUAL_LIMIT = 26.0  # max deviation from a smooth quadratic surface
EDGE_LIMIT = 10.0  # p99.5 gradient magnitude in 0..255
STRONG_LIMIT = 0.004  # share of pixels with a gradient above 40
CLEAN, COLLIDES = "clean", "collides"
ANIMATED_TEMPLATES = ("announcement", "celebration", "countdown", "quiz", "quote", "steps", "year_in_review")


# --------------------------------------------------------------------------- declarations
def _assignments(path, class_name) -> dict:
    """Literal class attributes of ``class_name`` in *path* (no imports, so no Manim)."""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    found = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for statement in node.body:
            if (isinstance(statement, ast.Assign) and len(statement.targets) == 1
                    and isinstance(statement.targets[0], ast.Name)):
                try:
                    found[statement.targets[0].id] = ast.literal_eval(statement.value)
                except (ValueError, SyntaxError):
                    pass
    return found


def _module_constants(path, names) -> dict:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    found = {}
    for statement in tree.body:
        if (isinstance(statement, ast.Assign) and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Name) and statement.targets[0].id in names):
            try:
                found[statement.targets[0].id] = ast.literal_eval(statement.value)
            except (ValueError, SyntaxError):
                pass
    return found


def logo_declarations() -> tuple:
    """``{template: {"logo_region", "logo_height", "logo_reserved_*"}}`` plus the kit's defaults and regions."""
    from studio import registry

    constants = _module_constants(Path(registry.__file__).with_name("kit") / "scene.py",
                                  {"LOGO_REGIONS", "LOGO_HEIGHT", "LOGO_MIN_HEIGHT"})
    regions = tuple(constants.get("LOGO_REGIONS", CORNERS))
    default_height = float(constants.get("LOGO_HEIGHT", 7))
    declarations = {}
    for template_id in registry.template_ids():
        declared = _assignments(Path(registry.TEMPLATES_DIR) / template_id / "scene.py", "Template")
        declarations[template_id] = {
            "logo_region": declared.get("logo_region", "bottom-right"),
            "logo_height": declared.get("logo_height", default_height),
            "logo_reserved_aspects": declared.get("logo_reserved_aspects", ()),
            "logo_reserved_layouts": declared.get("logo_reserved_layouts", {}),
        }
    return declarations, regions, default_height


def is_reserved(declaration: dict, card: dict, aspect: str) -> bool:
    """Whether this card makes room for the logo when one is set (so only the logo render shows it)."""
    if aspect in (declaration.get("logo_reserved_aspects") or ()):
        return True
    layouts = declaration.get("logo_reserved_layouts") or {}
    names = layouts.get(aspect) if isinstance(layouts, dict) else ()
    return bool(names) and card["params"].get("layout") in names


def option(value, aspect, default):
    return value.get(aspect, default) if isinstance(value, dict) else value


def chosen_region(declaration: dict, aspect: str, regions: tuple) -> str:
    region = option(declaration.get("logo_region"), aspect, "bottom-right")
    return region if region in regions else "bottom-right"


# --------------------------------------------------------------------------- rendering
def make_test_logo(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / TEST_LOGO
    image = Image.new("RGB", (480, 240), (255, 0, 255))
    if not path.is_file():
        image.save(path)
    return path


def settings_for(card: dict, aspect: str, logo: bool) -> dict:
    settings = {key: value for key, value in card["settings"].items() if key != "aspect"}
    settings["aspect"] = aspect
    if logo:
        brand = dict(settings.get("brand") or {})
        brand["logo"] = TEST_LOGO
        settings["brand"] = brand
    return settings


def render(service, card: dict, aspect: str, *, logo: bool, mode: str, short: int) -> tuple:
    """(RGB array, storyboard metadata or None, preview path) from the service's cached preview."""
    result = service.preview_sync(card["template"], card["params"], settings_for(card, aspect, logo),
                                 mode, short)
    with Image.open(result["path"]) as image:
        pixels = np.asarray(image.convert("RGB")).copy()
    return pixels, result.get("storyboard"), result["path"]


class RenderPool:
    """One warm StudioService per thread, so Manim renders run in parallel processes."""

    def __init__(self, root: Path, assets: Path, short: int):
        self.root, self.assets, self.short = root, assets, short
        self._local = threading.local()
        self._services = []
        self._indexes = itertools.count()
        self._lock = threading.Lock()

    def service(self):
        service = getattr(self._local, "service", None)
        if service is None:
            from studio.service import StudioService

            with self._lock:
                index = next(self._indexes)
            folder = self.root / f"worker-{index}"
            service = StudioService(str(folder), media_dir=str(folder / "media"), assets_dir=str(self.assets),
                                    preview_timeout=600.0)
            self._local.service = service
            with self._lock:
                self._services.append(service)
        return service

    def close(self):
        for service in self._services:
            try:
                service.shutdown_sync()
            except Exception:  # noqa: BLE001 - cleanup must not hide the results
                pass


# --------------------------------------------------------------------------- measurement
def locate_logo(base: np.ndarray, with_logo: np.ndarray) -> tuple | None:
    """The magenta test logo's first..last pixels, requiring it to differ from the base."""
    magenta = ((with_logo[:, :, 0] > 200) & (with_logo[:, :, 1] < 80)
               & (with_logo[:, :, 2] > 200))
    difference = np.abs(base.astype(np.int16) - with_logo.astype(np.int16)).max(axis=2) > 8
    ys, xs = np.nonzero(magenta & difference)
    if len(xs) < 40:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _smooth_residual(values: np.ndarray, height: int, width: int) -> np.ndarray:
    yy, xx = np.mgrid[0:height, 0:width]
    xn = (xx - (width - 1) / 2) / max(width, 1)
    yn = (yy - (height - 1) / 2) / max(height, 1)
    terms = [np.ones_like(xn), xn, yn, xn * xn, xn * yn, yn * yn]
    design = np.stack(terms, axis=-1).reshape(-1, len(terms))
    residual = np.empty((height, width, values.shape[2]), np.float32)
    for channel in range(values.shape[2]):
        flat = values[:, :, channel].reshape(-1)
        coefficients, *_ = np.linalg.lstsq(design, flat, rcond=None)
        residual[:, :, channel] = (flat - design @ coefficients).reshape(height, width)
    return residual


def measure(crop: np.ndarray) -> dict:
    """Color spread, smooth-surface residual and edge content of a no-logo crop."""
    height, width = crop.shape[:2]
    values = crop.astype(np.float32)
    channels = values.reshape(-1, 3)
    low, high = np.percentile(channels, 0.5, axis=0), np.percentile(channels, 99.5, axis=0)
    spread = float(np.max(high - low))
    residual = float(np.percentile(np.abs(_smooth_residual(values, height, width)).max(axis=2), 99.5))
    gray = values.mean(axis=2)
    gradient_y, gradient_x = np.gradient(gray)
    gradient = np.hypot(gradient_x, gradient_y)
    return {
        "spread": round(spread, 1),
        "residual": round(residual, 1),
        "edge": round(float(np.percentile(gradient, 99.5)), 1),
        "strong": round(float((gradient > 40).mean()), 4),
        "size": [width, height],
    }


def verdict(metrics: dict) -> str:
    clean = (metrics["spread"] <= SPREAD_LIMIT and metrics["residual"] <= RESIDUAL_LIMIT
             and metrics["edge"] <= EDGE_LIMIT and metrics["strong"] <= STRONG_LIMIT)
    return CLEAN if clean else COLLIDES


def mask_logo(crop: np.ndarray, logo_box: tuple) -> np.ndarray:
    """Fill the logo's rectangle with the surrounding color, leaving the margin ring to measure."""
    crop = crop.copy()
    height, width = crop.shape[:2]
    x0, y0, x1, y1 = logo_box
    x0, y0 = max(0, x0 - 1), max(0, y0 - 1)
    x1, y1 = min(width, x1 + 1), min(height, y1 + 1)
    ring = np.ones((height, width), bool)
    ring[y0:y1, x0:x1] = False
    if ring.any():
        crop[~ring] = np.median(crop[ring], axis=0).astype(crop.dtype)
    return crop


def measure_ring(crop: np.ndarray, logo_box: tuple) -> dict:
    """Cleanliness of the margin around the logo (the logo itself and its edge excluded)."""
    height, width = crop.shape[:2]
    ring = np.ones((height, width), bool)
    x0, y0, x1, y1 = logo_box
    x0, y0 = max(0, x0 - 2), max(0, y0 - 2)
    x1, y1 = min(width, x1 + 2), min(height, y1 + 2)
    ring[y0:y1, x0:x1] = False
    if not ring.any():
        return measure(crop)
    values = crop.astype(np.float32)
    pixels = values[ring]
    low, high = np.percentile(pixels, 0.5, axis=0), np.percentile(pixels, 99.5, axis=0)
    spread = float(np.max(high - low))

    yy, xx = np.mgrid[0:height, 0:width]
    xn = (xx - (width - 1) / 2) / max(width, 1)
    yn = (yy - (height - 1) / 2) / max(height, 1)
    terms = [np.ones_like(xn), xn, yn, xn * xn, xn * yn, yn * yn]
    design = np.stack(terms, axis=-1).reshape(-1, len(terms))
    residual = np.empty((height, width, values.shape[2]), np.float32)
    for channel in range(values.shape[2]):
        flat = values[:, :, channel].reshape(-1)
        coefficients, *_ = np.linalg.lstsq(design[ring.reshape(-1)], flat[ring.reshape(-1)], rcond=None)
        residual[:, :, channel] = np.abs(flat - design @ coefficients).reshape(height, width)
    residual_value = float(np.percentile(residual[ring], 99.5))

    gray = values.mean(axis=2)
    gradient_y, gradient_x = np.gradient(gray)
    gradient = np.hypot(gradient_x, gradient_y)
    return {
        "spread": round(spread, 1),
        "residual": round(residual_value, 1),
        "edge": round(float(np.percentile(gradient[ring], 99.5)), 1),
        "strong": round(float((gradient[ring] > 40).mean()), 4),
        "size": [width, height],
    }


def corners_of(base: np.ndarray, box: tuple, *, mask_logo_pixels: bool = False) -> dict:
    """Measure the logo's box in all four corners of an image.

    The logo is placed the same distance from the safe area's edges in every corner,
    so the box's offset from the frame edge can be mirrored without extra renders.
    With ``mask_logo_pixels``, the margin ring around the logo is what gets measured
    (for a layout that only makes room when a logo is set).
    """
    height, width = base.shape[:2]
    x0, y0, x1, y1 = box
    logo_width, logo_height = x1 - x0, y1 - y0
    pad_x = x0 if x0 + x1 < width else width - x1
    pad_y = y0 if y0 + y1 < height else height - y1
    margin = max(1, round(MARGIN_SHARE * min(width, height)))
    measured = {}
    for corner in CORNERS:
        logo_left = pad_x if corner.endswith("left") else width - pad_x - logo_width
        logo_top = pad_y if corner.startswith("top") else height - pad_y - logo_height
        left, top = max(0, logo_left - margin), max(0, logo_top - margin)
        right = min(width, left + logo_width + 2 * margin)
        bottom = min(height, top + logo_height + 2 * margin)
        crop = base[top:bottom, left:right]
        logo_box = [logo_left - left, logo_top - top,
                    logo_left - left + logo_width, logo_top - top + logo_height]
        stats = measure_ring(crop, logo_box) if mask_logo_pixels else measure(crop)
        stats["verdict"] = verdict(stats)
        stats["box"] = [left, top, right, bottom]
        stats["logo_box"] = logo_box
        measured[corner] = stats
    return measured


def save_crop(crop: np.ndarray, path: Path, scale: int = 4) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.fromarray(crop.astype(np.uint8))
    image.resize((image.width * scale, image.height * scale), Image.NEAREST).save(path)


def measure_pair(base: np.ndarray, with_logo: np.ndarray) -> dict:
    box = locate_logo(base, with_logo)
    if box is None:
        return {"error": "the magenta test logo was not found in the render"}
    return {"box": list(box), "corners": corners_of(base, box),
            "corners_logo": corners_of(with_logo, box, mask_logo_pixels=True)}


# --------------------------------------------------------------------------- jobs
def poster_job(pool: RenderPool, card: dict, aspect: str, short: int) -> dict:
    error = None
    for _attempt in (1, 2):
        try:
            service = pool.service()
            base, _, base_path = render(service, card, aspect, logo=False, mode="poster", short=short)
            with_logo, _, logo_path = render(service, card, aspect, logo=True, mode="poster", short=short)
        except Exception as exc:  # noqa: BLE001 - one failed card must not hide the others; retry once
            error = exc
            continue
        result = measure_pair(base, with_logo)
        result.update(card=card, aspect=aspect, base_path=base_path, logo_path=logo_path)
        return result
    return {"card": card, "aspect": aspect, "error": f"{type(error).__name__}: {error}"}


def storyboard_job(service, card: dict, aspect: str, short: int, reserved: bool = False) -> dict:
    """Compare every captured storyboard frame at the logo's fixed box."""
    try:
        base, base_meta, base_path = render(service, card, aspect, logo=False, mode="storyboard", short=short)
        with_logo, logo_meta, logo_path = render(service, card, aspect, logo=True, mode="storyboard", short=short)
    except Exception as exc:  # noqa: BLE001
        return {"card": card, "aspect": aspect, "error": f"{type(exc).__name__}: {exc}"}
    if not base_meta or not logo_meta or base_meta["frame_size"] != logo_meta["frame_size"]:
        return {"card": card, "aspect": aspect, "error": "the storyboards have no matching metadata"}

    def tiles(pixels, meta):
        tile_width, tile_height = meta["frame_size"]
        gap, columns = 8, meta["columns"]
        out = []
        for i in range(meta["frames"]):
            row, column = divmod(i, columns)
            left, top = gap + column * (tile_width + gap), gap + row * (tile_height + gap)
            out.append(pixels[top:top + tile_height, left:left + tile_width])
        return out

    base_tiles, logo_tiles = tiles(base, base_meta), tiles(with_logo, logo_meta)
    if len(base_tiles) != len(logo_tiles):
        return {"card": card, "aspect": aspect,
                "error": f"the storyboards captured {len(base_tiles)}/{len(logo_tiles)} frames"}
    box = None
    for tile in logo_tiles:
        magenta = ((tile[:, :, 0] > 200) & (tile[:, :, 1] < 80) & (tile[:, :, 2] > 200))
        ys, xs = np.nonzero(magenta)
        if len(xs) >= 40:
            box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
            break
    if box is None:
        return {"card": card, "aspect": aspect, "error": "the magenta test logo was not found in the storyboard"}

    height, width = base_tiles[0].shape[:2]
    x0, y0, x1, y1 = box
    corner = ("bottom-" if (y0 + y1) / 2 >= height / 2 else "top-") + \
             ("left" if (x0 + x1) / 2 < width / 2 else "right")
    margin = max(1, round(MARGIN_SHARE * min(width, height)))
    left, top = max(0, x0 - margin), max(0, y0 - margin)
    right, bottom = min(width, x1 + margin), min(height, y1 + margin)

    frames = []
    logo_rect = [x0 - left, y0 - top, x1 - left, y1 - top]
    for index, (_base_tile, logo_tile) in enumerate(zip(base_tiles, logo_tiles)):
        # Measure the logo render itself: a template may move text aside or clip particles
        # only when a logo is set, and that is the frame a viewer sees.
        stats = measure_ring(logo_tile[top:bottom, left:right], logo_rect)
        stats.update(verdict=verdict(stats), time=base_meta["times"][index])
        frames.append(stats)
    return {"card": card, "aspect": aspect, "corner": corner, "box": [left, top, right, bottom],
            "frames": frames, "length": base_meta["length"], "reserved": reserved,
            "frame_size": base_meta["frame_size"], "columns": base_meta["columns"],
            "base_path": base_path, "logo_path": logo_path}


# --------------------------------------------------------------------------- reporting
def print_poster_table(results: list, declarations: dict, regions: tuple) -> int:
    print("POSTERS - every card, every aspect; the four corners of the no-logo poster")
    label_width = max((len(f'{result["card"]["template"]}/{result["card"]["preset"]}') for result in results),
                      default=28) + 2
    print(f'{"card":{label_width}s} aspect  chosen        top-left   top-right  bottom-left  bottom-right  result')
    print("-" * (label_width + 89))
    failures = 0
    for result in results:
        card = result["card"]
        label = f'{card["template"]}/{card["preset"]}'
        aspect = result["aspect"]
        declaration = declarations.get(card["template"], {})
        chosen = chosen_region(declaration, aspect, regions)
        reserved = is_reserved(declaration, card, aspect)
        if "error" in result:
            print(f'{label:{label_width}s} {aspect:6s}  {chosen:13s} ERROR {result["error"]}')
            failures += 1
            continue
        corners = result["corners"]
        flags = [corners[corner]["verdict"] for corner in CORNERS]
        ok = (result["corners_logo"][chosen]["verdict"] if reserved else corners[chosen]["verdict"]) == CLEAN
        failures += 0 if ok else 1
        outcome = "ok" if ok and not reserved else ("ok (reserved)" if ok else "COLLIDES")
        print(f'{label:{label_width}s} {aspect:6s}  {chosen:13s} '
              + "  ".join(f"{flag:9s}" for flag in flags) + f'  {outcome}')
        if not ok:
            detail = result["corners_logo"][chosen] if reserved else corners[chosen]
            print(f'    {chosen}: spread {detail["spread"]}, residual {detail["residual"]}, '
                  f'edge {detail["edge"]}, strong {detail["strong"]}'
                  + (" (logo render ring)" if reserved else " (no-logo poster)"))
    print("-" * (label_width + 89))
    print("reserved: the template moves its content out of the logo's band only when a logo is set;")
    print("          its chosen corner is measured on the logo render with the logo masked out.")
    print(f"{len(results)} card/aspect pairs, {failures} chosen corner(s) colliding")
    return failures


def print_animation_table(results: list) -> int:
    print("\nANIMATION - storyboards (content that moves or appears late), logo in its chosen corner")
    label_width = max((len(f'{result["card"]["template"]}/{result["card"]["preset"]}') for result in results),
                      default=28) + 2
    print(f'{"template":{label_width}s} aspect  frames  corner        unclean frames')
    print("-" * (label_width + 55))
    failures = 0
    for result in results:
        card = result["card"]
        label = f'{card["template"]}/{card["preset"]}'
        if "error" in result:
            print(f'{label:{label_width}s} {result["aspect"]:6s}  ERROR {result["error"]}')
            failures += 1
            continue
        frames = result["frames"]
        unclean = [frame for frame in frames if frame["verdict"] != CLEAN]
        failures += len(unclean)
        times = ", ".join(f'{frame["time"]:g}s' for frame in unclean) or "none"
        print(f'{label:{label_width}s} {result["aspect"]:6s}  {len(frames):6d}  {result["corner"]:13s} {times}')
        for frame in unclean:
            print(f'    {frame["time"]:g}s: spread {frame["spread"]}, residual {frame["residual"]}, '
                  f'edge {frame["edge"]}, strong {frame["strong"]}')
    print("-" * (label_width + 55))
    print(f"{failures} unclean animated frame(s)")
    return failures


def save_animation_failures(out: Path, results: list) -> None:
    """Crop each unclean storyboard tile so the covered corner can be looked at."""
    gap = 8
    for result in results:
        if "error" in result or "frames" not in result:
            continue
        unclean = [(index, frame) for index, frame in enumerate(result["frames"])
                   if frame["verdict"] != CLEAN]
        if not unclean:
            continue
        source = result["logo_path"] if result["reserved"] else result["base_path"]
        with Image.open(source) as image:
            sheet = np.asarray(image.convert("RGB"))
        tile_width, tile_height = result["frame_size"]
        left, top, right, bottom = result["box"]
        for index, frame in unclean:
            row, column = divmod(index, result["columns"])
            x, y = gap + column * (tile_width + gap), gap + row * (tile_height + gap)
            crop = sheet[y + top:y + bottom, x + left:x + right]
            save_crop(crop, out / "failures"
                      / f'{result["card"]["template"]}-{result["card"]["preset"]}-'
                        f'{result["aspect"].replace(":", "x")}-animation-{frame["time"]:g}s.png')


def contact_sheet(out: Path, catalog: list, results: dict, aspects: list) -> Path:
    """One tile per template per aspect, using the first gallery card, with the logo."""
    cell_width, cell_height, label_height, padding, name_width, header = 400, 300, 30, 12, 210, 54
    width = name_width + cell_width * len(aspects)
    height = header + (label_height + cell_height + 2 * padding) * len(catalog)
    sheet = Image.new("RGB", (width, height), (22, 24, 28))
    draw = ImageDraw.Draw(sheet)
    font_path = BACKEND / "studio" / "assets" / "fonts" / "InterStudio-SemiBold.ttf"
    try:
        title_font = ImageFont.truetype(str(font_path), 24)
        label_font = ImageFont.truetype(str(font_path), 17)
    except OSError:
        title_font = label_font = ImageFont.load_default()
    draw.text((18, 14), "Brand logo placement - magenta test logo, one tile per template and aspect",
              font=title_font, fill=(240, 242, 248))
    for column, aspect in enumerate(aspects):
        draw.text((name_width + column * cell_width + padding, 18), aspect, font=label_font, fill=(150, 200, 255))

    for row, template in enumerate(catalog):
        top = header + row * (label_height + cell_height + 2 * padding)
        draw.text((18, top + padding + 6), template["title"], font=label_font, fill=(240, 242, 248))
        draw.text((18, top + padding + 28), template["id"], font=label_font, fill=(140, 150, 165))
        for column, aspect in enumerate(aspects):
            left = name_width + column * cell_width
            draw.rectangle([left + 2, top + 2, left + cell_width - 2, top + cell_height + 2 * padding],
                           outline=(48, 52, 60), width=1)
            result = results.get((template["id"], template["presets"][0]["id"], aspect))
            if not result or "error" in result or not result.get("logo_path"):
                draw.text((left + padding, top + padding + 10), "render failed", font=label_font,
                          fill=(220, 110, 120))
                continue
            with Image.open(result["logo_path"]) as image:
                image.thumbnail((cell_width - 2 * padding, cell_height - 2 * padding), Image.LANCZOS)
                x = left + (cell_width - image.width) // 2
                y = top + padding + (cell_height - 2 * padding - image.height) // 2
                sheet.paste(image.convert("RGB"), (x, y))
    path = out / "contact-sheet.png"
    sheet.save(path)
    return path


# --------------------------------------------------------------------------- main
def parse_aspects(value: str) -> list:
    aspects = [part.strip() for part in value.split(",") if part.strip()]
    unknown = [aspect for aspect in aspects if aspect not in ASPECT_ORDER]
    if unknown:
        raise argparse.ArgumentTypeError(f"unknown aspect(s): {', '.join(unknown)}")
    return aspects or list(ASPECT_ORDER)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--aspects", type=parse_aspects, default=list(ASPECT_ORDER),
                        help="comma separated (default: 16:9,9:16,1:1,4:5)")
    parser.add_argument("--short", type=int, default=480, help="pixels on the poster's short side (default 480)")
    parser.add_argument("--jobs", type=int, default=min(4, os.cpu_count() or 1),
                        help="parallel render workers (default: up to 4)")
    parser.add_argument("--out", type=Path, default=None, help="output folder (default: a new temp folder)")
    parser.add_argument("--no-animation", action="store_true", help="skip the storyboard checks")
    parser.add_argument("--template", action="append", default=None, help="only these template ids (repeatable)")
    parser.add_argument("--preset", action="append", default=None, help="only these preset ids (repeatable)")
    args = parser.parse_args(argv)

    started = time.perf_counter()
    out = Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix="studio-logo-check-"))
    out.mkdir(parents=True, exist_ok=True)
    assets = out / "assets"
    make_test_logo(assets)

    from studio.service import StudioService

    catalog_service = StudioService(str(out / "catalog"))
    try:
        catalog = catalog_service._catalog_sync()["templates"]
    finally:
        catalog_service.shutdown_sync()
    cards = [{"template": template["id"], "preset": card["id"], "params": card["params"],
              "settings": card["settings"], "default_aspect": template["default_aspect"]}
             for template in catalog for card in template["presets"]]
    if args.template:
        catalog = [template for template in catalog if template["id"] in args.template]
        cards = [card for card in cards if card["template"] in args.template]
    if args.preset:
        cards = [card for card in cards if card["preset"] in args.preset]
    if not cards:
        parser.error("no cards match --template/--preset")
    declarations, regions, _default_height = logo_declarations()
    aspects = [aspect for aspect in ASPECT_ORDER if aspect in args.aspects]
    jobs = [(card, aspect) for card in cards for aspect in aspects]
    print(f"Rendering {len(jobs)} cards/aspects (base + logo) with {min(args.jobs, len(jobs))} workers...",
          flush=True)

    pool = RenderPool(out / "cache", assets, args.short)
    results = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(args.jobs, len(jobs))) as executor:
            futures = [executor.submit(poster_job, pool, card, aspect, args.short) for card, aspect in jobs]
            for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
                result = future.result()
                results.append(result)
                if index % 10 == 0 or index == len(futures):
                    print(f"  {index}/{len(futures)} done ({time.perf_counter() - started:.0f}s)", flush=True)
    finally:
        pool.close()
    results.sort(key=lambda result: (result["card"]["template"], result["card"]["preset"], result["aspect"]))

    by_card = {(result["card"]["template"], result["card"]["preset"], result["aspect"]): result
               for result in results}
    failures = print_poster_table(results, declarations, regions)
    for result in results:
        if "error" in result:
            continue
        declaration = declarations.get(result["card"]["template"], {})
        chosen = chosen_region(declaration, result["aspect"], regions)
        reserved = is_reserved(declaration, result["card"], result["aspect"])
        corner = (result["corners_logo"] if reserved else result["corners"])[chosen]
        if corner["verdict"] == CLEAN:
            continue
        left, top, right, bottom = corner["box"]
        source = result["logo_path"] if reserved else result["base_path"]
        with Image.open(source) as image:
            crop = np.asarray(image.convert("RGB"))[top:bottom, left:right]
        if reserved:
            crop = mask_logo(crop, corner["logo_box"])
        save_crop(crop, out / "failures"
                  / f'{result["card"]["template"]}-{result["card"]["preset"]}-'
                    f'{result["aspect"].replace(":", "x")}-{chosen}.png')

    animation_failures = 0
    animation_results = []
    if not args.no_animation:
        animation_service = StudioService(str(out / "animation"), media_dir=str(out / "animation" / "media"),
                                          assets_dir=str(assets))
        try:
            for template in catalog:
                if template["id"] not in ANIMATED_TEMPLATES or not template["presets"]:
                    continue
                card = {"template": template["id"], "preset": template["presets"][0]["id"],
                        "params": template["presets"][0]["params"],
                        "settings": template["presets"][0]["settings"],
                        "default_aspect": template["default_aspect"]}
                declaration = declarations.get(template["id"], {})
                animation_results.append(storyboard_job(
                    animation_service, card, template["default_aspect"], args.short,
                    reserved=is_reserved(declaration, card, template["default_aspect"])))
        finally:
            animation_service.shutdown_sync()
        animation_failures = print_animation_table(animation_results)
        save_animation_failures(out, animation_results)

    sheet = None
    try:
        sheet = contact_sheet(out, catalog, by_card, aspects)
    except Exception as exc:  # noqa: BLE001 - the measurements matter more than the sheet
        print(f"contact sheet failed: {type(exc).__name__}: {exc}")

    print(f"\nOutput folder: {out.resolve()}")
    if sheet is not None:
        print(f"Contact sheet: {sheet.resolve()}")
    print(f"Finished in {time.perf_counter() - started:.0f}s")
    return 1 if failures or animation_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
