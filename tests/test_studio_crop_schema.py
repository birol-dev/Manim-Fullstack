"""Image crop hints are validated authoring metadata, shared by the UI and agents."""
import pytest
from studio import registry, schema

@pytest.mark.parametrize("crop", ["circle", "free", "1:1", "16:9", "4:5", "9:16", "3:2"])
def test_crop_hint_accepts_shapes_and_positive_aspects(crop):
    field = schema.image(title="Photo", crop=crop)
    assert field.json_schema_extra["x-crop"] == crop

@pytest.mark.parametrize("crop", ["", "square", "0:1", "1:0", "-1:1", "1.5:1", "1:2:3", "1/1", " 1:1 ", 1, True, [], "1:10000", "1:1９"])
def test_crop_hint_rejects_invalid_values(crop):
    with pytest.raises(ValueError, match="crop must"):
        schema.image(title="Photo", crop=crop)

def test_crop_hint_is_optional_for_existing_schemas():
    assert "x-crop" not in schema.image(title="Photo").json_schema_extra

@pytest.mark.parametrize("template_id", registry.template_ids())
def test_every_template_image_has_a_crop_hint(template_id):
    root = registry.get_template(template_id).params_model.model_json_schema()
    for definition in [root, *root.get("$defs", {}).values()]:
        for prop in definition.get("properties", {}).values():
            if prop.get("x-widget") == "image":
                assert "x-crop" in prop
                if prop.get("x-shape") == "circle":
                    assert prop["x-crop"] == "circle"
