"""The brand kit: preference validation, bundled fonts and each template's logo corner."""

import ast
import os

import pytest

from studio import registry, themes
from studio.preferences import PreferenceStore
from studio.registry import TemplateError
from studio.schema import Brand

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
SCENE = os.path.join(BACKEND, "studio", "kit", "scene.py")


def _assigned(tree, class_name, attr):
    """The literal value of ``attr = ...`` inside ``class class_name``, or None."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for statement in node.body:
                if (isinstance(statement, ast.Assign) and len(statement.targets) == 1
                        and isinstance(statement.targets[0], ast.Name)
                        and statement.targets[0].id == attr):
                    return ast.literal_eval(statement.value)
    return None


def _regions():
    with open(SCENE, encoding="utf-8") as source:
        return set(ast.literal_eval(next(
            statement.value for statement in ast.parse(source.read()).body
            if isinstance(statement, ast.Assign) and isinstance(statement.targets[0], ast.Name)
            and statement.targets[0].id == "LOGO_REGIONS")))


# --------------------------------------------------------------------------- #
# Fonts
# --------------------------------------------------------------------------- #


def test_a_brand_font_only_uses_bundled_families():
    clean = themes.THEMES["clean"]["font"]
    assert themes.theme_tokens("clean", Brand(font="JetBrains Mono"))["font"] == "JetBrains Mono"
    assert themes.theme_tokens("clean", Brand(font="Inter Studio"))["font"] == "Inter"
    for unknown in ("Comic Sans", "", None, "Inter Black"):
        assert themes.theme_tokens("pop", Brand(font=unknown))["font"] == themes.THEMES["pop"]["font"]
    assert themes.bundled_font(" jetbrains MONO ") == "JetBrains Mono"
    assert themes.bundled_font("Arial") is None
    assert clean in themes.BUNDLED_FONTS


def test_brand_accents_still_apply_on_top_of_the_theme():
    tokens = themes.theme_tokens("midnight", Brand(accent="#123456", accent2="#ABCDEF"))
    assert tokens["accent"][0] == "#123456"
    assert tokens["accent"][1] == "#ABCDEF"
    assert tokens["font"] == themes.THEMES["midnight"]["font"]


# --------------------------------------------------------------------------- #
# Preferences
# --------------------------------------------------------------------------- #


def test_brand_kit_preferences_validate_and_persist(tmp_path):
    store = PreferenceStore(str(tmp_path))
    kit = {"accent": "2563eb", "accent2": "#00aa88", "font": "JetBrains Mono", "logo": "logo.png"}
    assert store.update({"brand_kit": kit})["brand_kit"] == {
        "accent": "#2563EB", "accent2": "#00AA88", "font": "JetBrains Mono", "logo": "logo.png"}
    assert store.read()["brand_kit"]["accent"] == "#2563EB"

    # A partial kit replaces the whole object; null clears one value and survives a reload.
    assert store.update({"brand_kit": {"accent": None, "logo": "brand.svg"}})["brand_kit"] == {
        "accent": None, "logo": "brand.svg"}
    assert store.read()["brand_kit"] == {"accent": None, "logo": "brand.svg"}
    assert store.update({"brand_kit": {}})["brand_kit"] == {}

    # brand_color keeps working beside it (old files and the welcome tour use it).
    assert store.update({"brand_color": "ff3366"})["brand_color"] == "#FF3366"


def test_bad_brand_kits_are_refused_with_field_paths(tmp_path):
    store = PreferenceStore(str(tmp_path))
    store.update({"brand_kit": {"logo": "good.png"}})
    cases = [
        (["not", "an", "object"], "brand_kit"),
        ({"accent": "blue"}, "brand_kit.accent"),
        ({"accent2": "#12345"}, "brand_kit.accent2"),
        ({"font": "x" * 61}, "brand_kit.font"),
        ({"font": 3}, "brand_kit.font"),
        ({"logo": "../outside.png"}, "brand_kit.logo"),
        ({"logo": "a/b.png"}, "brand_kit.logo"),
        ({"logo": ""}, "brand_kit.logo"),
        ({"nope": True}, "brand_kit.nope"),
    ]
    for value, field in cases:
        with pytest.raises(TemplateError) as info:
            store.update({"brand_kit": value})
        assert field in {error["field"] for error in info.value.errors}, value
    assert store.read()["brand_kit"] == {"logo": "good.png"}


def test_brand_kit_round_trips_through_render_settings():
    settings = Brand(accent="#2563EB", accent2=None, font="Inter", logo="logo.png")
    assert settings.model_dump() == {"accent": "#2563EB", "accent2": None, "font": "Inter", "logo": "logo.png"}


# --------------------------------------------------------------------------- #
# Logo placement contract
# --------------------------------------------------------------------------- #


def test_the_base_scene_default_is_a_valid_region():
    with open(SCENE, encoding="utf-8") as source:
        default = _assigned(ast.parse(source.read()), "StudioScene", "logo_region")
    assert default in _regions()


@pytest.mark.parametrize("template_id", registry.template_ids())
def test_every_template_declares_a_valid_logo_region(template_id):
    path = os.path.join(registry.TEMPLATES_DIR, template_id, "scene.py")
    with open(path, encoding="utf-8") as source:
        region = _assigned(ast.parse(source.read()), "Template", "logo_region")
    assert region in _regions(), f"{template_id} needs its own logo_region"
