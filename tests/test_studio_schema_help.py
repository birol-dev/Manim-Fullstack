"""UI help stays short while the full tool descriptions remain available."""

from typing import Literal

import pytest

from studio import registry, schema


@pytest.mark.parametrize("template_id", registry.template_ids())
def test_template_ui_help_is_short_and_option_keys_match_the_enum(template_id):
    root = registry.get_template(template_id).params_model.model_json_schema()
    for definition in [root, *root.get("$defs", {}).values()]:
        for name, prop in definition.get("properties", {}).items():
            where = f"{template_id}.{name}"
            help = prop.get("x-help")
            options = prop.get("x-option-help")
            if help is not None:
                assert isinstance(help, str) and help.strip(), where
                assert len(help) <= 70 and "\n" not in help, where
            if options is not None:
                assert isinstance(options, dict) and options, where
                assert set(options) <= set(prop.get("enum", [])), where
                assert all(isinstance(line, str) and line.strip() and len(line) <= 70 and "\n" not in line
                           for line in options.values()), where
            if len(prop.get("description", "")) > 110:
                assert help or options, f"{where} needs short UI help"
            if prop.get("x-widget") in ("duration", "color", "icon") or prop.get("x-choice-of"):
                assert help, f"{where} should describe the visible control"


@pytest.mark.parametrize("template_id, field", [
    ("announcement", "layout"), ("celebration", "occasion"), ("countdown", "style"),
    ("quote", "reveal"), ("year_in_review", "style"),
])
def test_multi_option_descriptions_have_help_for_each_choice(template_id, field):
    prop = registry.get_template(template_id).params_model.model_json_schema()["properties"][field]
    assert set(prop["x-option-help"]) == set(prop["enum"])
    assert prop["description"]  # retained for agents


@pytest.mark.parametrize("helper, args", [
    (schema.text, ()), (schema.number, ()), (schema.integer, ()), (schema.duration, (30,)),
    (schema.choice, ("one",)), (schema.toggle, (True,)), (schema.color, ()), (schema.image, ()),
    (schema.icon, ()), (schema.datetime_text, ()), (schema.items, ([],)),
])
def test_field_helpers_keep_ui_help_separate_from_description(helper, args):
    field = helper(*args, title="Example", description="Full agent description.", help="Short help.")
    assert field.description == "Full agent description."
    assert field.json_schema_extra["x-help"] == "Short help."


def test_choice_helper_emits_option_help_and_omits_absent_extras():
    class Params(schema.TemplateParams):
        style: Literal["one", "two"] = schema.choice(
            "one", title="Style", description="Full options for agents.",
            option_help={"one": "First option.", "two": "Second option."})
        title: str = schema.text(title="Title")

    props = Params.model_json_schema()["properties"]
    assert props["style"]["x-option-help"] == {"one": "First option.", "two": "Second option."}
    assert props["style"]["description"] == "Full options for agents."
    assert "x-help" not in props["title"] and "x-option-help" not in props["title"]


def test_duration_and_choice_descriptions_keep_the_agent_contract():
    countdown = registry.get_template("countdown").params_model.model_json_schema()["properties"]
    assert countdown["seconds"]["description"] == "How long the timer runs, in seconds (5 minutes = 300)."
    assert countdown["seconds"]["x-help"] == "How long the timer runs."
    assert countdown["style"]["description"] == (
        "Ring: a circle that empties. Progress bar: a bar that shrinks. Big numbers: large seconds "
        "that pop (best for short countdowns like 10 to 1).")
