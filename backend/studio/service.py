"""The studio service: what the REST routes (``studio/api.py``) and the MCP server call.

Transport-agnostic: async methods that take and return plain JSON-able dicts. Bad
input raises ``registry.TemplateError`` (``errors`` = ``[{"field", "message"}]``); other
failures raise ``errors.StudioError`` subclasses carrying an HTTP-like ``status``.
Nothing here imports Manim: previews go to the warm worker (``studio/worker.py``),
exports to a Manim subprocess (``studio/exports.py``).

    service = StudioService(workspace_dir, media_dir, assets_dir)
    await service.catalog()
    await service.preview("countdown", {"seconds": 60}, {"aspect": "9:16"}, "poster")
    export = await service.start_export("countdown", {...}, {...}, format="mp4", quality="720p")

Files (``workspace`` and ``media`` are configurable):

* previews: ``media/studio/previews/<key>.png`` (+ ``.json`` for storyboards), served at
  ``/media/studio/previews/<key>.png``; the key hashes template id + version + the
  template's and kit's files + params + settings + mode + size.
* exports: ``media/studio/exports/<slug>-<id6>.<ext>``; index ``workspace/studio/exports.json``.
* projects: ``workspace/studio/projects/<id>.json``.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import copy
import hashlib
import io
import json
import logging
import os
import re
import secrets
import shutil
import sys
import threading
import time
from typing import Optional
from xml.etree import ElementTree

from . import peeks, registry
from .errors import NotFoundError, RenderError, RendererUnavailable, RenderTimeout, StudioError
from .exports import EXPORT_FORMATS, ExportManager, ManimVideoRunner
from .formats import ASPECT_RATIOS, QUALITIES, pixel_size
from .registry import TemplateError
from .motion import MotionPreviews, LONG_SIDE, FPS, MAX_DURATION
from .schema import CATEGORY_TITLES
from .storage import (ICONS_DIR, KIT_ROOTS, STUDIO_DIR, TEMP_MARK, ImageCropStore, png_size, prune_previews, slugify,
                      template_dir, tree_fingerprint, utc_now)
from .themes import THEMES, public_themes
from .worker import PreviewWorker, WorkerCrashed, WorkerReplyError, WorkerStartError, WorkerTimeout

BACKEND_DIR = os.path.dirname(STUDIO_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import file_ops  # noqa: E402

logger = logging.getLogger("studio")

DEFAULT_WORKSPACE = os.path.join(os.path.dirname(BACKEND_DIR), "workspace")
PREVIEW_MODES = ("poster", "storyboard")
EXPORT_QUALITIES = ("draft", "720p", "1080p", "1080p60", "4k")
MIN_SHORT, MAX_SHORT = 120, 1080
MAX_INPUT_BYTES = 256 * 1024  # params + settings of one preview, export or project
MAX_TITLE = 120
KEY_VERSION = 2
PROJECT_ID = re.compile(r"^[0-9a-f]{16}$")
ICON_NAME = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
ASSET_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg")
MAX_IMAGE_BYTES = 8 * 1024 * 1024  # as base64 it still fits the app's request size limit
MAX_IMAGE_PIXELS = 40_000_000
IMAGE_FORMATS = {"PNG": ".png", "JPEG": ".jpg", "GIF": ".gif", "WEBP": ".webp"}
_UNSET = object()

ASPECT_LABELS = {"16:9": "Landscape", "9:16": "Vertical", "1:1": "Square", "4:5": "Portrait"}
QUALITY_LABELS = {"draft": "Draft", "720p": "HD 720p", "1080p": "Full HD 1080p", "1080p60": "Full HD 1080p, 60 fps",
                  "4k": "4K"}
FORMAT_INFO = [
    {"id": "mp4", "label": "MP4 video", "kind": "video", "transparent": False},
    {"id": "webm", "label": "WebM video", "kind": "video", "transparent": True},
    {"id": "mov", "label": "MOV video", "kind": "video", "transparent": True},
    {"id": "gif", "label": "Animated GIF", "kind": "video", "transparent": False},
    {"id": "png", "label": "PNG image", "kind": "image", "transparent": True},
]


def _field_error(field: str, message: str, summary: Optional[str] = None) -> TemplateError:
    return TemplateError(summary or message, [{"field": field, "message": message}])


class StudioService:
    def __init__(self, workspace_dir: Optional[str] = None, media_dir: Optional[str] = None,
                 assets_dir: Optional[str] = None, **options):
        self._worker = None
        self._motion = None
        self._exports: Optional[ExportManager] = None
        self._render_lock = threading.Lock()  # one preview render at a time; identical ones render once
        self._state_lock = threading.RLock()
        self._template_fps: dict = {}
        self._kit_fp = (0.0, None)
        self._icons_fp = (0.0, None)
        self._worker_kit_fp = None
        self._catalog_cache = None
        self._warming = False
        self.configure(workspace_dir, media_dir, assets_dir, **options)

    def configure(self, workspace_dir: Optional[str] = None, media_dir: Optional[str] = None,
                  assets_dir: Optional[str] = None, *, app_root: Optional[str] = None, worker_factory=None,
                  runner_factory=None, icons_dir: Optional[str] = None, poster_short: int = 360,
                  preview_timeout: float = 45.0, cache_limit: int = 500, max_worker_jobs: int = 200,
                  export_timeout: Optional[float] = None, max_active_exports: int = 20, prewarm: bool = False,
                  motion_worker_factory=None):
        """Point the service at a workspace. Stops a worker or export queue from an earlier configuration."""
        self.shutdown_sync()
        workspace = os.path.abspath(workspace_dir or DEFAULT_WORKSPACE)
        self.workspace_dir = workspace
        self.media_dir = os.path.abspath(media_dir or os.path.join(workspace, "media"))
        self.assets_dir = os.path.abspath(assets_dir or os.path.join(workspace, "assets"))
        self.app_root = app_root or os.path.dirname(workspace)
        self.studio_dir = os.path.join(workspace, "studio")
        self.projects_dir = os.path.join(self.studio_dir, "projects")
        self.tmp_dir = os.path.join(self.studio_dir, "tmp")
        self.index_path = os.path.join(self.studio_dir, "exports.json")
        self.previews_dir = os.path.join(self.media_dir, "studio", "previews")
        self.exports_dir = os.path.join(self.media_dir, "studio", "exports")
        self.icons_dir = icons_dir or ICONS_DIR
        self.poster_short = int(poster_short)
        self.preview_timeout = float(preview_timeout)
        self.cache_limit = int(cache_limit)
        self.max_worker_jobs = int(max_worker_jobs)
        self.export_timeout = export_timeout
        self.max_active_exports = int(max_active_exports)
        self.prewarm = bool(prewarm)
        self._worker_factory = worker_factory or self._default_worker
        self._motion_worker_factory = motion_worker_factory or (lambda: PreviewWorker(
            media_dir=os.path.join(self.tmp_dir, "motion-media"), request_timeout=120.0))
        self._runner_factory = runner_factory or (lambda: ManimVideoRunner(app_root=self.app_root))
        self._worker = None
        self._motion = None
        self._exports = None
        self._worker_kit_fp = None
        self._icons_fp = (0.0, None)
        self._catalog_cache = None
        return self

    # -- lifecycle -----------------------------------------------------------------
    def _default_worker(self):
        return PreviewWorker(media_dir=os.path.join(self.tmp_dir, "preview-media"),
                             request_timeout=self.preview_timeout, max_jobs=self.max_worker_jobs)

    def _get_worker(self):
        with self._state_lock:
            if self._worker is None:
                self._worker = self._worker_factory()
            return self._worker

    def _export_manager(self) -> ExportManager:
        with self._state_lock:
            if self._exports is None:
                self._exports = ExportManager(
                    exports_dir=self.exports_dir, work_dir=os.path.join(self.tmp_dir, "exports"),
                    index_path=self.index_path, media_root=self.media_dir, plan=self._plan_export,
                    still=self._render_still, runner_factory=self._runner_factory,
                    base_timeout=self.export_timeout, max_active=self.max_active_exports)
            return self._exports

    def shutdown_sync(self) -> None:
        """Stop the running export and the preview worker (both restart on next use)."""
        motion = getattr(self, "_motion", None)
        if motion is not None:
            motion.close()
        exports, worker = getattr(self, "_exports", None), getattr(self, "_worker", None)
        if exports is not None:
            exports.shutdown(timeout=10.0, on_stopping=worker.close if worker is not None else None)
        elif worker is not None:
            worker.close()

    async def shutdown(self) -> None:
        await asyncio.to_thread(self.shutdown_sync)

    def warm_up(self) -> None:
        """Start the preview worker in the background (no-op when it runs or is starting)."""
        with self._state_lock:
            worker = self._get_worker()
            if self._warming or getattr(worker, "alive", False):
                return
            self._warming = True

        def run():
            try:
                worker.start()
            except Exception as exc:  # noqa: BLE001 - warm-up is best effort
                logger.info("studio: preview worker warm-up failed (%s)", exc)
            finally:
                self._warming = False

        threading.Thread(target=run, name="studio-warm-up", daemon=True).start()

    # -- templates -----------------------------------------------------------------
    def _refresh_template(self, template_id: str) -> str:
        """Drop the cached schema of a template whose files changed on disk; returns its fingerprint."""
        fingerprint = tree_fingerprint(template_dir(template_id))
        with self._state_lock:
            seen = self._template_fps.get(template_id)
            self._template_fps[template_id] = fingerprint
            if seen is not None and seen != fingerprint:
                package = f"{registry.PACKAGE}.{template_id}"
                for name in [n for n in sys.modules if n == package or n.startswith(package + ".")]:
                    sys.modules.pop(name, None)
                registry._cache.pop(template_id, None)
        return fingerprint

    def _spec(self, template_id):
        if not isinstance(template_id, str) or not template_id:
            raise _field_error("template", "Choose a template.")
        if template_id not in registry.template_ids():
            raise _field_error("template", f"Unknown template {template_id!r}.")
        self._refresh_template(template_id)
        try:
            return registry.get_template(template_id)
        except TemplateError:
            raise
        except Exception as exc:  # noqa: BLE001 - a template that doesn't import
            raise StudioError(f"Template {template_id!r} failed to load: {type(exc).__name__}: {exc}") from exc

    def _catalog_sync(self) -> dict:
        ids = registry.template_ids()
        key = tuple((tid, self._refresh_template(tid)) for tid in ids)
        with self._state_lock:
            if self._catalog_cache is not None and self._catalog_cache[0] == key:
                return self._with_peeks(copy.deepcopy(self._catalog_cache[1]))
        sections = {name: [] for name in CATEGORY_TITLES}
        templates = []
        for tid in ids:
            try:
                public = self._spec(tid).public()
            except Exception as exc:  # noqa: BLE001 - one broken template must not hide the others
                logger.warning("studio: template %s is unavailable (%s)", tid, exc)
                continue
            templates.append(public)
            for card in public["presets"]:
                sections.setdefault(card["category"], []).append(card)
        result = {
            "sections": [{"id": name, "title": CATEGORY_TITLES.get(name, name), "cards": cards}
                         for name, cards in sections.items() if cards],
            "templates": templates,
            "themes": public_themes(),
            "aspects": [{"id": a, "label": ASPECT_LABELS.get(a, a), "ratio": list(r)} for a, r in ASPECT_RATIOS.items()],
            "qualities": [{"id": q, "label": QUALITY_LABELS[q], **QUALITIES[q]} for q in EXPORT_QUALITIES],
            "formats": copy.deepcopy(FORMAT_INFO),
        }
        with self._state_lock:
            self._catalog_cache = (key, result)
        return self._with_peeks(copy.deepcopy(result))

    def _with_peeks(self, catalog):
        manifest = peeks.read_manifest()
        for template in catalog["templates"]:
            for card in template["presets"]:
                settings = {"aspect": template["default_aspect"], **card["settings"]}
                path = peeks.current_path(self, card, settings, manifest)
                card["peek_url"] = f"/api/studio/peeks/{path.name}" if path else None
        return catalog

    def peek_path(self, key):
        if isinstance(key, str) and re.fullmatch(r"[a-f0-9]{32}", key):
            url = f"/api/studio/peeks/{key}.mp4"
            if any(card.get("peek_url") == url for template in self._catalog_sync()["templates"]
                   for card in template["presets"]):
                return peeks.PEEKS_DIR / f"{key}.mp4"
        raise NotFoundError("That gallery peek is no longer available.")

    async def catalog(self) -> dict:
        """Gallery sections, templates (schema, defaults, presets), themes, aspects, qualities, formats."""
        if self.prewarm:
            self.warm_up()
        return await asyncio.to_thread(self._catalog_sync)

    async def template_info(self, template_id: str) -> dict:
        def run():
            try:
                return self._spec(template_id).public()
            except TemplateError as exc:
                raise NotFoundError(str(exc)) from None

        return await asyncio.to_thread(run)

    # -- validation ------------------------------------------------------------------
    @staticmethod
    def _object(name: str, value) -> dict:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise _field_error(name, f"{name} must be an object.")
        return value

    @staticmethod
    def _check_size(*values) -> None:
        size = sum(len(json.dumps(v, ensure_ascii=False, default=str)) for v in values)
        if size > MAX_INPUT_BYTES:
            raise _field_error("params", f"The content is too large ({size // 1024} KB; the limit is "
                                         f"{MAX_INPUT_BYTES // 1024} KB).")

    @staticmethod
    def _title(value, default: Optional[str] = None) -> Optional[str]:
        if value is None:
            return default
        if not isinstance(value, str):
            raise _field_error("title", "title must be text.")
        value = value.strip()
        if len(value) > MAX_TITLE:
            raise _field_error("title", f"Use at most {MAX_TITLE} characters.")
        return value or default

    def _validate(self, template, params, settings) -> tuple:
        """(spec, params as JSON, settings as JSON, RenderSettings); raises TemplateError."""
        spec = self._spec(template)
        params, settings = self._object("params", params), self._object("settings", settings)
        self._check_size(params, settings)
        spec, model, render_settings = registry.validate_job(spec.id, params, settings)
        errors = []
        if render_settings.theme not in THEMES:
            errors.append({"field": "settings.theme",
                           "message": f"Unknown theme; use one of {', '.join(THEMES)}."})
        meta = spec.meta
        length = render_settings.length
        if length is not None and not meta.length_from_params and not meta.min_length <= length <= meta.max_length:
            errors.append({"field": "settings.length",
                           "message": f"{spec.id} runs {meta.min_length:g}-{meta.max_length:g} seconds."})
        if errors:
            raise TemplateError(f"Invalid input for {spec.id}.", errors)
        return spec, model.model_dump(mode="json"), render_settings.model_dump(mode="json"), render_settings

    # -- previews ----------------------------------------------------------------------
    def _kit_fingerprint(self) -> str:
        checked, value = self._kit_fp
        now = time.monotonic()
        if value is None or now - checked > 1.0:
            value = tree_fingerprint(*KIT_ROOTS)
            self._kit_fp = (now, value)
        return value

    def _icons_fingerprint(self) -> str:
        checked, value = self._icons_fp
        now = time.monotonic()
        if value is None or now - checked > 1.0:
            value = tree_fingerprint(self.icons_dir)
            self._icons_fp = (now, value)
        return value

    def _asset_stamps(self, *values) -> list:
        """(name, mtime, size) of uploaded files the input names, so a re-upload refreshes previews."""
        names, stack = set(), list(values)
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                stack.extend(value.values())
            elif isinstance(value, list):
                stack.extend(value)
            elif (isinstance(value, str) and value.lower().endswith(ASSET_EXTENSIONS)
                  and os.path.basename(value) == value and not value.startswith(".")):
                names.add(value)
        stamps = []
        for name in sorted(names):
            try:
                info = os.stat(os.path.join(self.assets_dir, name))
                stamps.append([name, info.st_mtime_ns, info.st_size])
            except OSError:
                stamps.append([name, None, None])
        return stamps

    def _preview_key(self, spec, params: dict, settings: dict, mode: str, short: int) -> str:
        payload = {"v": KEY_VERSION, "template": spec.id, "version": spec.meta.version,
                   "files": self._refresh_template(spec.id), "kit": self._kit_fingerprint(),
                   "icons": self._icons_fingerprint(),
                   "params": params, "settings": settings, "mode": mode, "short": short,
                   "assets": self._asset_stamps(params, settings)}
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(blob.encode("ascii")).hexdigest()[:32]

    def _short(self, short) -> int:
        if short is None:
            return self.poster_short
        if isinstance(short, bool) or not isinstance(short, int) or not MIN_SHORT <= short <= MAX_SHORT:
            raise _field_error("short", f"Use a whole number of pixels from {MIN_SHORT} to {MAX_SHORT}.")
        return short

    def _media_url(self, path: str) -> str:
        return "/media/" + os.path.relpath(path, self.media_dir).replace("\\", "/")

    @staticmethod
    def _cache_hit(png: str, meta: str, mode: str) -> bool:
        if not os.path.isfile(png) or (mode == "storyboard" and not os.path.isfile(meta)):
            return False
        try:
            os.utime(png)  # most recently used survives pruning
        except OSError:
            pass
        return True

    def _render_with_worker(self, job: dict, width: int, height: int, timeout: Optional[float] = None) -> dict:
        worker = self._get_worker()
        kit = self._kit_fingerprint()
        if self._worker_kit_fp is not None and kit != self._worker_kit_fp:
            worker.stop()  # the kit changed on disk: it can only be re-imported in a new process
        self._worker_kit_fp = kit
        try:
            return worker.render(job, width, height, timeout=timeout or self.preview_timeout)
        except WorkerReplyError as exc:
            raise RenderError(f"The template could not render this: {exc}", exc.traceback) from None
        except WorkerTimeout as exc:
            raise RenderTimeout(str(exc)) from None
        except WorkerCrashed as exc:
            raise RenderError(str(exc)) from None
        except WorkerStartError as exc:
            raise RendererUnavailable(str(exc)) from None
        except OSError as exc:
            raise RendererUnavailable(f"The preview worker could not start ({exc.strerror or exc}).") from None

    def _render_into_cache(self, spec, params, settings, mode, width, height, key) -> None:
        os.makedirs(self.previews_dir, exist_ok=True)
        stem = os.path.join(self.previews_dir, f"{TEMP_MARK}{key}-{secrets.token_hex(4)}")
        job = {"template": spec.id, "params": params, "settings": settings, "mode": mode,
               "assets_dir": self.assets_dir, "output": stem + ".png"}
        try:
            self._render_with_worker(job, width, height)
            if not os.path.isfile(stem + ".png"):
                raise RenderError("The preview finished without writing an image.")
            if mode == "storyboard":
                os.replace(stem + ".json", os.path.join(self.previews_dir, key + ".json"))
            os.replace(stem + ".png", os.path.join(self.previews_dir, key + ".png"))
        finally:
            for leftover in (stem + ".png", stem + ".json"):
                try:
                    os.unlink(leftover)
                except OSError:
                    pass
        prune_previews(self.previews_dir, self.cache_limit)

    def _seed_poster(self, key: str, destination: str) -> bool:
        # Only an exact current request key can select a baked file. Old bakes fall
        # through to the worker; no writable cache is needed in the installation.
        source = os.path.join(STUDIO_DIR, "assets", "posters", key + ".png")
        if png_size(source) is None:
            return False
        os.makedirs(self.previews_dir, exist_ok=True)
        temporary = destination + TEMP_MARK + secrets.token_hex(4)
        try:
            shutil.copyfile(source, temporary)
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return True

    def preview_sync(self, template, params=None, settings=None, mode: str = "poster", short=None) -> dict:
        started = time.perf_counter()
        if mode not in PREVIEW_MODES:
            raise _field_error("mode", "Use poster or storyboard.", "Invalid preview mode.")
        short = self._short(short)
        spec, params, settings, render_settings = self._validate(template, params, settings)
        width, height = pixel_size(render_settings.aspect, short)
        key = self._preview_key(spec, params, settings, mode, short)
        png = os.path.join(self.previews_dir, key + ".png")
        meta = os.path.join(self.previews_dir, key + ".json")
        cached = self._cache_hit(png, meta, mode)
        if not cached:
            with self._render_lock:
                cached = self._cache_hit(png, meta, mode)
                if not cached and mode == "poster":
                    cached = self._seed_poster(key, png)
                if not cached:
                    self._render_into_cache(spec, params, settings, mode, width, height, key)
        size = png_size(png) or (width, height)
        result = {"url": self._media_url(png), "path": png, "mode": mode, "width": size[0], "height": size[1],
                  "cached": cached, "ms": round((time.perf_counter() - started) * 1000)}
        if mode == "storyboard":
            try:
                with open(meta, encoding="utf-8") as f:
                    result["storyboard"] = json.load(f)
            except (OSError, ValueError) as exc:
                raise RenderError(f"The storyboard metadata is missing ({exc}).") from None
        return result

    async def preview(self, template, params=None, settings=None, mode: str = "poster", short=None) -> dict:
        """A cached poster or storyboard: ``{url, path, mode, width, height, cached, ms, storyboard?}``."""
        return await asyncio.to_thread(self.preview_sync, template, params, settings, mode, short)

    def _motion_manager(self):
        with self._state_lock:
            if self._motion is None:
                self._motion = MotionPreviews(self, self._motion_worker_factory())
            return self._motion

    def start_motion_sync(self, project, template, params=None, settings=None):
        if not isinstance(project, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", project):
            raise _field_error("project", "Use a project or editor session id (1–64 letters, numbers, - or _).")
        spec, params, settings, render_settings = self._validate(template, params, settings)
        # pixel_size uses the short side; round even for MP4's yuv420p encoder.
        aspect = ASPECT_RATIOS[render_settings.aspect]
        width = max(2, round(LONG_SIDE * aspect[0] / max(aspect) / 2) * 2)
        height = max(2, round(LONG_SIDE * aspect[1] / max(aspect) / 2) * 2)
        key = self._preview_key(spec, params, settings, f"motion-{FPS}-{MAX_DURATION}", LONG_SIDE)
        return self._motion_manager().start(project, {"template": spec.id, "params": params,
            "settings": settings, "assets_dir": self.assets_dir}, width, height, key)

    async def start_motion(self, project, template, params=None, settings=None):
        """Queue a silent 720px/15fps preview (first 20s); supersede this project's prior request."""
        return await asyncio.to_thread(self.start_motion_sync, project, template, params, settings)

    async def get_motion(self, preview_id):
        return self._motion_manager().get(preview_id)

    async def cancel_motion(self, preview_id):
        return self._motion_manager().cancel(preview_id)

    def _cached_poster_url(self, template, params, settings) -> Optional[str]:
        try:
            spec, params, settings, _ = self._validate(template, params, settings)
        except Exception:  # noqa: BLE001 - drafts may be incomplete
            return None
        key = self._preview_key(spec, params, settings, "poster", self.poster_short)
        png = os.path.join(self.previews_dir, key + ".png")
        return self._media_url(png) if os.path.isfile(png) else None

    # -- exports -------------------------------------------------------------------------
    def _plan_export(self, job: dict) -> dict:
        return self.preview_sync(job["template"], job["params"], job["settings"], "storyboard")["storyboard"]

    def _render_still(self, job: dict, width: int, height: int, out: str) -> None:
        with self._render_lock:
            self._render_with_worker({**job, "mode": "poster", "output": out}, width, height,
                                     timeout=max(self.preview_timeout, 120.0))
        if not os.path.isfile(out):
            raise RenderError("The poster finished without writing an image.")

    def start_export_sync(self, template, params=None, settings=None, format: str = "mp4",
                          quality: str = "1080p", title=None) -> dict:
        errors = []
        if format not in EXPORT_FORMATS:
            errors.append({"field": "format", "message": f"Use one of {', '.join(EXPORT_FORMATS)}."})
        if quality not in EXPORT_QUALITIES:
            errors.append({"field": "quality", "message": f"Use one of {', '.join(EXPORT_QUALITIES)}."})
        if errors:
            raise TemplateError("Invalid export settings.", errors)
        title = self._title(title)
        spec, params, settings, render_settings = self._validate(template, params, settings)
        q = QUALITIES[quality]
        width, height = pixel_size(render_settings.aspect, q["short"])
        transparent = render_settings.background.kind == "transparent"
        fmt = "mov" if (transparent and format == "mp4") else format  # MP4 can't hold transparency
        record = {"template": spec.id, "title": title or spec.meta.title, "format": fmt, "quality": quality,
                  "aspect": render_settings.aspect, "width": width, "height": height,
                  "fps": spec.meta.export_fps or q["fps"], "transparent": transparent,
                  "_slug": slugify(title, fallback=spec.id) if title else slugify(spec.id, fallback="video")}
        job = {"template": spec.id, "params": params, "settings": settings, "assets_dir": self.assets_dir}
        return self._export_manager().start(record, job)

    async def start_export(self, template, params=None, settings=None, format: str = "mp4",
                           quality: str = "1080p", title=None) -> dict:
        """Queue an export; returns the ``export`` record (status ``queued``)."""
        return await asyncio.to_thread(self.start_export_sync, template, params, settings, format, quality, title)

    async def get_export(self, export_id: str) -> dict:
        return self._export_manager().get(export_id)

    async def list_exports(self) -> list:
        return self._export_manager().list()

    async def cancel_export(self, export_id: str, wait: float = 5.0) -> dict:
        """Cancel a queued or running export; waits up to *wait* s for a running one to stop."""
        manager = self._export_manager()
        record = await asyncio.to_thread(manager.cancel, export_id)
        deadline = time.monotonic() + wait
        while record["status"] == "rendering" and time.monotonic() < deadline:
            await asyncio.sleep(0.1)
            record = manager.get(export_id)
        return record

    async def remove_export(self, export_id: str) -> dict:
        """Forget a finished export and delete its file."""
        return await asyncio.to_thread(self._export_manager().remove, export_id)

    # -- projects --------------------------------------------------------------------------
    def _project_path(self, project_id) -> str:
        if not isinstance(project_id, str) or not PROJECT_ID.match(project_id):
            raise NotFoundError(f"No project {project_id!r}.")
        return os.path.join(self.projects_dir, project_id + ".json")

    @staticmethod
    def _read_project(path: str) -> dict:
        try:
            with open(path, encoding="utf-8") as f:
                project = json.load(f)
        except FileNotFoundError:
            raise NotFoundError(f"No project {os.path.splitext(os.path.basename(path))[0]!r}.") from None
        except (OSError, ValueError) as exc:
            raise StudioError(f"The project file can't be read ({exc}).") from None
        if not isinstance(project, dict):
            raise StudioError("The project file is damaged.")
        return project

    def _encode_project(self, project: dict) -> bytes:
        data = json.dumps(project, ensure_ascii=False, indent=1).encode("utf-8")
        if len(data) > MAX_INPUT_BYTES:
            raise _field_error("params", f"The project is too large ({len(data) // 1024} KB; the limit is "
                                         f"{MAX_INPUT_BYTES // 1024} KB).")
        return data

    @staticmethod
    def _canonical_params(template_id, params: dict) -> dict:
        """Valid params as the template reads them (e.g. quiz answers given as plain strings become
        answer objects), so the editor shows what renders. Drafts that don't validate are kept as given."""
        try:
            model = registry.get_template(template_id).params_model(**params)
            return model.model_dump(mode="json", exclude_unset=True)
        except Exception:  # noqa: BLE001 - incomplete drafts are allowed
            return params

    def _with_poster(self, project: dict) -> dict:
        return {**project, "poster_url": self._cached_poster_url(project.get("template"), project.get("params"),
                                                                 project.get("settings"))}

    def create_project_sync(self, template, params=None, settings=None, title=None) -> dict:
        spec = self._spec(template)
        params, settings = self._object("params", params), self._object("settings", settings)
        params = self._canonical_params(spec.id, params)
        now = utc_now()
        project = {"id": "", "title": self._title(title, spec.meta.title), "template": spec.id,
                   "params": params, "settings": settings, "created": now, "updated": now}
        os.makedirs(self.projects_dir, exist_ok=True)
        for _attempt in range(5):
            project["id"] = secrets.token_hex(8)
            path = self._project_path(project["id"])
            try:
                with file_ops.locked(path):
                    file_ops.atomic_write(path, self._encode_project(project), exclusive=True)
                return self._with_poster(project)
            except FileExistsError:
                continue
        raise StudioError("Could not pick a project id.")  # pragma: no cover

    def update_project_sync(self, project_id, *, title=_UNSET, params=_UNSET, settings=_UNSET) -> dict:
        path = self._project_path(project_id)
        with file_ops.locked(path):
            project = self._read_project(path)
            if title is not _UNSET:
                default = None
                try:
                    default = registry.get_template(project.get("template")).meta.title
                except Exception:  # noqa: BLE001 - the template may be gone
                    pass
                project["title"] = self._title(title, default or project.get("title") or "Untitled")
            if params is not _UNSET:
                project["params"] = self._canonical_params(project.get("template"), self._object("params", params))
            if settings is not _UNSET:
                project["settings"] = self._object("settings", settings)
            project["updated"] = utc_now()
            file_ops.atomic_write(path, self._encode_project(project))
        return self._with_poster(project)

    def delete_project_sync(self, project_id) -> dict:
        path = self._project_path(project_id)
        with file_ops.locked(path):
            project = self._read_project(path)
            try:
                os.unlink(path)
            except FileNotFoundError:
                raise NotFoundError(f"No project {project_id!r}.") from None
        return project

    def list_projects_sync(self) -> list:
        try:
            entries = list(os.scandir(self.projects_dir))
        except FileNotFoundError:
            return []
        projects = []
        for entry in entries:
            stem, ext = os.path.splitext(entry.name)
            if ext != ".json" or not PROJECT_ID.match(stem):
                continue
            try:
                project = self._read_project(entry.path)
            except StudioError:
                continue
            projects.append(project)
        projects.sort(key=lambda p: str(p.get("updated", "")), reverse=True)
        return [{"id": p.get("id"), "title": p.get("title"), "template": p.get("template"),
                 "created": p.get("created"), "updated": p.get("updated"),
                 "poster_url": self._cached_poster_url(p.get("template"), p.get("params"), p.get("settings"))}
                for p in projects]

    async def list_projects(self) -> list:
        """``[{id, title, template, created, updated, poster_url}]``, most recently updated first."""
        return await asyncio.to_thread(self.list_projects_sync)

    async def get_project(self, project_id: str) -> dict:
        return await asyncio.to_thread(lambda: self._with_poster(self._read_project(self._project_path(project_id))))

    async def create_project(self, template, params=None, settings=None, title=None) -> dict:
        return await asyncio.to_thread(self.create_project_sync, template, params, settings, title)

    async def update_project(self, project_id: str, *, title=_UNSET, params=_UNSET, settings=_UNSET) -> dict:
        """Replace the given fields (omitted ones stay); ``title=None`` resets it to the template's title."""
        return await asyncio.to_thread(
            lambda: self.update_project_sync(project_id, title=title, params=params, settings=settings))

    async def delete_project(self, project_id: str) -> dict:
        return await asyncio.to_thread(self.delete_project_sync, project_id)

    # -- images from agents ---------------------------------------------------------------------
    @staticmethod
    def _decode_image(data) -> bytes:
        if isinstance(data, str):
            text = data.strip()
            if text.startswith("data:") and "," in text:  # a data URL
                text = text.split(",", 1)[1]
            try:
                data = base64.b64decode(text, validate=True)
            except (ValueError, binascii.Error):
                raise _field_error("data", "Send the image as base64.") from None
        if not isinstance(data, (bytes, bytearray)) or not data:
            raise _field_error("data", "Send the image as base64.")
        if len(data) > MAX_IMAGE_BYTES:
            raise _field_error("data", f"Use an image of at most {MAX_IMAGE_BYTES // (1024 * 1024)} MB.")
        return bytes(data)

    @staticmethod
    def _image_kind(data: bytes) -> tuple:
        """(extension, width, height) of a PNG/JPEG/GIF/WebP/SVG; TemplateError for anything else."""
        unsupported = _field_error("data", "Use a PNG, JPEG, GIF, WebP or SVG image.")
        head = data[:1024].lstrip()
        if head.startswith((b"<?xml", b"<svg", b"<!--")):
            try:
                root = ElementTree.fromstring(data)
            except ElementTree.ParseError:
                raise unsupported from None
            if root.tag.rsplit("}", 1)[-1] != "svg":
                raise unsupported
            return ".svg", None, None
        from PIL import Image, UnidentifiedImageError

        try:
            with Image.open(io.BytesIO(data)) as img:
                fmt, (width, height) = img.format, img.size
                if width * height > MAX_IMAGE_PIXELS:
                    raise _field_error("data", "The image has too many pixels; send a smaller one.")
                img.verify()
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
            raise unsupported from None
        if fmt not in IMAGE_FORMATS:
            raise unsupported
        return IMAGE_FORMATS[fmt], width, height

    def add_image_sync(self, data) -> dict:
        """Store an image an agent sends (base64 or bytes) with the uploads; ``{name, width, height}``.

        The name comes from the content, so sending the same picture again returns the same name.
        """
        data = self._decode_image(data)
        ext, width, height = self._image_kind(data)
        name = f"agent-{hashlib.sha256(data).hexdigest()[:16]}{ext}"
        path = os.path.join(self.assets_dir, name)
        os.makedirs(self.assets_dir, exist_ok=True)
        if not os.path.isfile(path):
            try:
                file_ops.atomic_write(path, data, exclusive=True)
            except FileExistsError:
                pass  # the same picture sent twice at once
        return {"name": name, "width": width, "height": height}

    async def add_image(self, data) -> dict:
        return await asyncio.to_thread(self.add_image_sync, data)

    def image_info_sync(self, name: str) -> dict:
        try:
            crops = ImageCropStore(self.workspace_dir, self.assets_dir)
            path = crops.image_path(name)
        except ValueError as exc:
            raise _field_error("name", str(exc)) from None
        if not os.path.isfile(path):
            raise NotFoundError("Image not found.")
        return {"name": name, "crop": crops.read(name)}

    async def image_info(self, name: str) -> dict:
        return await asyncio.to_thread(self.image_info_sync, name)

    def save_image_crop_sync(self, name: str, crop: dict) -> dict:
        try:
            recipe = ImageCropStore(self.workspace_dir, self.assets_dir).write(name, crop)
        except FileNotFoundError:
            raise NotFoundError("The crop or its original image is missing.") from None
        except FileExistsError as exc:
            conflict = StudioError(str(exc))
            conflict.status = 409
            raise conflict from None
        except ValueError as exc:
            raise _field_error("crop", str(exc)) from None
        return {"name": name, "crop": recipe}

    async def save_image_crop(self, name: str, crop: dict) -> dict:
        return await asyncio.to_thread(self.save_image_crop_sync, name, crop)

    # -- icons ---------------------------------------------------------------------------------
    def icon_names_sync(self) -> list:
        try:
            names = os.listdir(self.icons_dir)
        except OSError:
            return []
        return sorted(n[:-4] for n in names
                      if n.endswith(".svg") and ICON_NAME.match(n[:-4]) and len(n) <= 68
                      and os.path.isfile(os.path.join(self.icons_dir, n)))

    async def icon_names(self) -> list:
        return await asyncio.to_thread(self.icon_names_sync)

    def icon_path(self, name: str) -> str:
        """Path of bundled icon *name* (TemplateError for a malformed name, NotFoundError if missing)."""
        if not isinstance(name, str) or len(name) > 64 or not ICON_NAME.match(name):
            raise _field_error("name", "Icon names are lowercase letters, digits, '-' and '_'.", "Invalid icon name.")
        root = os.path.realpath(self.icons_dir)
        path = os.path.realpath(os.path.join(root, name + ".svg"))
        if os.path.dirname(path) != root or not os.path.isfile(path):
            raise NotFoundError(f"No icon {name!r}.")
        return path


# The instance the app configures (main.py) and the API routes use.
service = StudioService()
