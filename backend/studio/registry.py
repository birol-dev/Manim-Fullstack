"""Discovers templates (``studio/templates/<id>/schema.py``) and validates jobs. No Manim import.

Each template package has ``schema.py`` (META, Params, PRESETS; importable without
Manim) and ``scene.py`` (class ``Template``, a ``kit.StudioScene``).
"""

from __future__ import annotations

import importlib
import os
import pkgutil
from dataclasses import dataclass
from typing import Optional

from pydantic import ValidationError

from .schema import CATEGORY_TITLES, Preset, RenderSettings, TemplateMeta

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
PACKAGE = __name__.rsplit(".", 1)[0] + ".templates"


@dataclass(frozen=True)
class TemplateSpec:
    meta: TemplateMeta
    params_model: type
    presets: tuple

    @property
    def id(self) -> str:
        return self.meta.id

    def public(self) -> dict:
        """Catalog entry for the API and MCP: metadata, JSON schema, presets."""
        return {
            **self.meta.model_dump(),
            "schema": self.params_model.model_json_schema(),
            "defaults": self.params_model().model_dump(mode="json"),
            "presets": [preset_card(self, p) for p in self.presets],
        }


def preset_card(spec: TemplateSpec, preset: Preset) -> dict:
    return {
        "id": preset.id,
        "template": spec.id,
        "title": preset.title,
        "summary": preset.summary,
        "category": preset.category or spec.meta.category,
        "params": preset.params,
        "settings": preset.settings,
        "tags": preset.tags,
    }


class TemplateError(ValueError):
    """A bad template id, params, or settings. ``errors`` lists field-level problems."""

    def __init__(self, message: str, errors: Optional[list] = None):
        super().__init__(message)
        self.errors = errors or []


_cache: dict = {}


def _load(template_id: str) -> TemplateSpec:
    module = importlib.import_module(f"{PACKAGE}.{template_id}.schema")
    meta = module.META
    if meta.id != template_id:
        raise RuntimeError(f"templates/{template_id}: META.id is {meta.id!r}")
    presets = tuple(getattr(module, "PRESETS", ()))
    return TemplateSpec(meta=meta, params_model=module.Params, presets=presets)


def template_ids() -> list:
    return sorted(
        info.name for info in pkgutil.iter_modules([TEMPLATES_DIR])
        if info.ispkg and not info.name.startswith("_")
        and os.path.isfile(os.path.join(TEMPLATES_DIR, info.name, "schema.py"))
    )


def all_templates() -> list:
    specs = []
    for template_id in template_ids():
        if template_id not in _cache:
            _cache[template_id] = _load(template_id)
        specs.append(_cache[template_id])
    return specs


def get_template(template_id: str) -> TemplateSpec:
    if not isinstance(template_id, str) or template_id not in template_ids():
        raise TemplateError(f"Unknown template {template_id!r}.")
    if template_id not in _cache:
        _cache[template_id] = _load(template_id)
    return _cache[template_id]


def catalog() -> dict:
    """Gallery sections in display order, each with its preset cards."""
    sections = {key: [] for key in CATEGORY_TITLES}
    for spec in all_templates():
        for preset in spec.presets:
            card = preset_card(spec, preset)
            sections[card["category"]].append(card)
    return {
        "sections": [
            {"id": key, "title": CATEGORY_TITLES[key], "cards": cards}
            for key, cards in sections.items() if cards
        ],
        "templates": [spec.public() for spec in all_templates()],
    }


def _field_errors(exc: ValidationError, prefix: str) -> list:
    out = []
    for err in exc.errors():
        path = ".".join(str(part) for part in (prefix, *err["loc"]) if part != "")
        out.append({"field": path, "message": err["msg"]})
    return out


def validate_job(template_id: str, params: Optional[dict], settings: Optional[dict]) -> tuple:
    """(spec, Params instance, RenderSettings) or TemplateError with per-field messages."""
    spec = get_template(template_id)
    errors = []
    try:
        model = spec.params_model(**(params or {}))
    except ValidationError as exc:
        errors += _field_errors(exc, "params")
        model = None
    except TypeError:
        errors.append({"field": "params", "message": "params must be an object"})
        model = None
    try:
        render_settings = RenderSettings(**(settings or {}))
    except ValidationError as exc:
        errors += _field_errors(exc, "settings")
        render_settings = None
    except TypeError:
        errors.append({"field": "settings", "message": "settings must be an object"})
        render_settings = None
    if render_settings is not None and render_settings.aspect not in spec.meta.aspects:
        errors.append({"field": "settings.aspect",
                       "message": f"{spec.id} supports {', '.join(spec.meta.aspects)}"})
    if errors:
        raise TemplateError(f"Invalid input for {template_id}.", errors)
    return spec, model, render_settings
