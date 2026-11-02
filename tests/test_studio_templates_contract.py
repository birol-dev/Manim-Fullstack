"""Every installed template keeps the studio contract (backend/studio/README.md).

The schema checks run without Manim (CI); the poster render of every preset is skipped
when Manim isn't installed.
"""

import ast
import importlib.util
import os
import sys

import pytest

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from studio import registry  # noqa: E402
from studio.schema import ASPECTS, CATEGORY_TITLES, RenderSettings  # noqa: E402
from studio.schema import image  # noqa: E402
from studio.themes import THEMES  # noqa: E402

TEMPLATE_IDS = registry.template_ids()
LATEX_NAMES = {"MathTex", "Tex", "SingleStringMathTex", "DecimalNumber", "Integer", "Variable", "BulletedList"}
KNOWN_WIDGETS = {"text", "textarea", "number", "integer", "duration", "choice", "toggle", "color", "image", "icon",
                 "list", "table"}


def test_templates_are_installed():
    assert {"countdown", "lower_third", "before_after", "slideshow", "chart"} <= set(TEMPLATE_IDS)


@pytest.mark.parametrize("template_id", TEMPLATE_IDS)
def test_meta_and_presets_validate(template_id):
    spec = registry.get_template(template_id)
    meta = spec.meta
    assert meta.category in CATEGORY_TITLES
    assert meta.when_to_use.strip(), "agents need when_to_use"
    assert set(meta.aspects) <= set(ASPECTS) and meta.default_aspect in meta.aspects
    assert meta.min_length <= meta.default_length <= meta.max_length
    assert spec.presets, "every template needs at least one gallery preset"
    ids = [p.id for p in spec.presets]
    assert len(ids) == len(set(ids)), "preset ids must be unique within a template"
    spec.params_model()  # the defaults alone must be valid
    for preset in spec.presets:
        settings = {**preset.settings}
        settings.setdefault("aspect", meta.default_aspect)
        registry.validate_job(template_id, preset.params, settings)
        assert RenderSettings(**settings).theme in THEMES, f"{preset.id}: unknown theme"


def test_preset_ids_are_unique_across_the_gallery():
    seen = {}
    for spec in registry.all_templates():
        for preset in spec.presets:
            key = preset.id
            assert key not in seen, f"preset id {key!r} is used by {seen[key]} and {spec.id}"
            seen[key] = spec.id


@pytest.mark.parametrize("template_id", TEMPLATE_IDS)
def test_every_field_has_a_label_and_known_widget(template_id):
    schema = registry.get_template(template_id).params_model.model_json_schema()

    def check(props, where):
        for name, prop in props.items():
            assert prop.get("title"), f"{where}.{name} needs a title (form label)"
            widget = prop.get("x-widget")
            if widget is not None:
                assert widget in KNOWN_WIDGETS, f"{where}.{name}: unknown x-widget {widget!r}"
            if widget == "image":
                description = prop.get("description", "")
                assert description.strip() and description != "Optional picture.", f"{where}.{name} needs its own picture help"
                assert "file name" not in description.lower(), f"{where}.{name} exposes an implementation detail"

    check(schema.get("properties", {}), template_id)
    for def_name, definition in schema.get("$defs", {}).items():
        check(definition.get("properties", {}), f"{template_id}.$defs.{def_name}")


def test_image_help_default_is_friendly():
    assert image(title="Picture").description == "Optional picture."


@pytest.mark.parametrize("template_id", TEMPLATE_IDS)
def test_array_choice_markers_reference_sibling_arrays(template_id):
    props = registry.get_template(template_id).params_model.model_json_schema()["properties"]
    for name, prop in props.items():
        if "x-choice-of" not in prop:
            continue
        assert prop["type"] == "integer" and prop["minimum"] == 1
        assert props[prop["x-choice-of"]]["type"] == "array", f"{name} needs a sibling array"


def test_quiz_correct_answer_keeps_its_integer_contract():
    spec = registry.get_template("quiz")
    field = spec.params_model.model_json_schema()["properties"]["correct"]
    assert field["x-choice-of"] == "options"
    assert field["description"] == "The position of the correct answer in the list: 1 is the first answer, 2 the second, and so on."
    assert field["default"] == 2 and field["minimum"] == 1 and field["maximum"] == 4
    assert spec.params_model(options=["Yes", "No"], correct=2).correct == 2


@pytest.mark.parametrize("template_id", TEMPLATE_IDS)
def test_schema_module_does_not_import_manim(template_id):
    """schema.py is imported by the API and MCP server on every request: no Manim there."""
    path = os.path.join(registry.TEMPLATES_DIR, template_id, "schema.py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        assert not any(n == "manim" or n.startswith("manim.") or n.startswith("studio.kit") for n in names), \
            f"{template_id}/schema.py imports {names}"


@pytest.mark.parametrize("template_id", TEMPLATE_IDS)
def test_scene_avoids_latex(template_id):
    path = os.path.join(registry.TEMPLATES_DIR, template_id, "scene.py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | \
           {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not (used & LATEX_NAMES), f"{template_id} uses LaTeX-backed classes: {sorted(used & LATEX_NAMES)}"


def test_invalid_input_reports_field_paths():
    with pytest.raises(registry.TemplateError) as info:
        registry.validate_job("countdown", {"seconds": -5, "nope": 1}, {"aspect": "3:2"})
    fields = {e["field"] for e in info.value.errors}
    assert "params.seconds" in fields
    assert "params.nope" in fields
    assert "settings.aspect" in fields


def test_unknown_template_is_refused():
    with pytest.raises(registry.TemplateError):
        registry.get_template("../kit")
    with pytest.raises(registry.TemplateError):
        registry.get_template("not_a_template")


MANIM = importlib.util.find_spec("manim") is not None
PRESET_CASES = [(spec.id, preset.id) for spec in registry.all_templates() for preset in spec.presets]


@pytest.mark.skipif(not MANIM, reason="Manim is not installed")
@pytest.mark.parametrize("template_id, preset_id", PRESET_CASES)
def test_every_preset_renders_a_poster(tmp_path, template_id, preset_id):
    from studio.dev import render_preview

    spec = registry.get_template(template_id)
    preset = next(p for p in spec.presets if p.id == preset_id)
    for aspect in ("16:9", "9:16"):
        if aspect not in spec.meta.aspects:
            continue
        out = tmp_path / f"{preset_id}-{aspect.replace(':', 'x')}.png"
        settings = {**preset.settings, "aspect": aspect}
        render_preview(template_id, preset.params, settings, "poster", str(out), short=180,
                       media_dir=str(tmp_path / "media"))
        assert out.is_file() and out.stat().st_size > 500
