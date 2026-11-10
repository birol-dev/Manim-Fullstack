"""New numerical layouts retain the data while their typography and counts animate."""

import pytest

pytest.importorskip("manim")

from manim import VMobject, tempconfig

from studio import registry
from studio.compat import output_config
from studio.formats import frame_size, pixel_size
from studio.kit import Counter, runtime


@pytest.fixture
def make_scene(tmp_path):
    def make(template, params, aspect="9:16"):
        cls = registry.get_template(template)
        module = __import__(f"studio.templates.{template}.scene", fromlist=["Template"])
        validated = cls.params_model(**params).model_dump()
        fw, fh = frame_size(*pixel_size(aspect, 480))
        runtime.set_job({"params": validated, "settings": {"aspect": aspect, "safe_zone": True}, "mode": "video"})
        with tempconfig({**output_config(dry_run=True), "media_dir": str(tmp_path),
                         "frame_width": fw, "frame_height": fh, "skip_animations": True,
                         "verbosity": "ERROR", "progress_bar": "none"}):
            scene = module.Template()
            scene.setup()
            scene.build()
        return scene

    yield make
    runtime.set_job(None)


def counters(scene):
    return [mob for root in scene.mobjects for mob in root.get_family() if isinstance(mob, Counter)]


@pytest.mark.parametrize("layout", ["cards", "editorial"])
@pytest.mark.parametrize("aspect", ["16:9", "9:16", "1:1", "4:5"])
def test_number_counts_reach_the_saved_values_and_fit(make_scene, layout, aspect):
    figures = [{"label": "Audience", "start": 18000, "value": 25000, "compact": True},
               {"label": "Balance", "start": 200, "value": -1240.25, "prefix": "$", "decimals": 2}]
    scene = make_scene("number_card", {"layout": layout, "figures": figures}, aspect)
    visible = counters(scene)
    assert [counter.value for counter in visible] == [25000, -1240.25]
    for counter in visible:
        assert counter.get_left()[0] >= scene.layout.safe.left - .01
        assert counter.get_right()[0] <= scene.layout.safe.right + .01


@pytest.mark.parametrize("current", [0, 62, 108])
def test_ruler_reports_the_true_percentage_and_keeps_the_pointer_in_range(make_scene, current):
    scene = make_scene("goal_progress", {"style": "ruler", "current": current, "target": 100})
    assert [counter.value for counter in counters(scene)] == [current]
    visible = [mob for mob in scene.content() if isinstance(mob, VMobject)]
    assert all(mob.get_left()[0] >= scene.layout.safe.left - .01 and
               mob.get_right()[0] <= scene.layout.safe.right + .01 for mob in visible)


def test_ledger_keeps_equal_zero_values_and_the_complete_source(make_scene):
    source = "Example results. Replace with your measurements."
    scene = make_scene("comparison", {"layout": "ledger", "source": source,
        "metrics": [{"label": "Conversion", "left": 0, "right": 0, "suffix": "%"}]})
    assert [counter.value for counter in counters(scene)] == [0, 0]
    text = "".join(getattr(mob, "original_text", "") for root in scene.mobjects for mob in root.get_family())
    assert source.replace(" ", "") in text.replace(" ", "")


def test_editorial_dashboard_leaves_a_gutter_between_figures(make_scene):
    scene = make_scene("number_card", {"layout": "editorial", "figures": [
        {"label": "Revenue", "value": 48650, "prefix": "$"},
        {"label": "Orders", "value": 620},
        {"label": "Repeat customers", "value": 36.5, "suffix": "%", "decimals": 1},
    ]}, "16:9")
    values = counters(scene)
    for left, right in zip(values, values[1:]):
        assert right.get_left()[0] - left.get_right()[0] >= scene.layout.unit * 3
