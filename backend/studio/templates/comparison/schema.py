"""Two named options compared on one to four numerical measures."""
from typing import Literal

from pydantic import ConfigDict

from studio.schema import Item, Preset, TemplateMeta, TemplateParams, choice, integer, items, number, text, toggle

META = TemplateMeta(
    id="comparison", title="Side-by-side comparison", category="compare",
    summary="Two options, matching measures, animated values and honest, shared-scale bars.",
    when_to_use="Before/after results, two plans, A/B experiments, price comparisons and this month vs last month. "
                "Each row compares the same measure, in the same units, on a shared zero-based scale.",
    not_for="Photo reveals: use before_after. More than two options: use chart. Negative values: use chart.",
    default_length=9, min_length=5, max_length=30,
    tags=["compare", "versus", "before after", "plans", "A/B", "results"],
)


class Metric(Item):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)
    label: str = text("Monthly cost", title="Measure", max_length=28)
    left: float = number(49, title="First value", ge=0, le=999_999_999)
    right: float = number(29, title="Second value", ge=0, le=999_999_999)
    prefix: str = text("", title="Before the number", max_length=4)
    suffix: str = text("", title="Unit", max_length=8)
    decimals: int = integer(0, title="Decimal places", ge=0, le=2)
    better: Literal["neutral", "higher", "lower"] = choice("neutral", title="Preferred result",
        labels={"neutral": "No preference", "higher": "Higher", "lower": "Lower"},
        help="Highlights the preferred value. Equal values have no winner.")


class Params(TemplateParams):
    title: str = text("A clearer comparison", title="Title", max_length=48)
    left_label: str = text("Before", title="First option", max_length=24)
    right_label: str = text("After", title="Second option", max_length=24)
    metrics: list[Metric] = items([Metric(label="Monthly cost", left=49, right=29, prefix="$", better="lower")],
        title="Measures", min_items=1, max_items=4, item_title="Measure")
    show_bars: bool = toggle(True, title="Show comparison bars")
    takeaway: str = text("", title="Takeaway", max_length=80,
        help="Optional. Empty shows the change in the first measure.")
    source: str = text("", title="Source or context", max_length=96,
        help="Add a source, period or note about the numbers.")


PRESETS = [
    Preset(id="before-after-results", title="Before vs after", summary="Show the effect of a change with three matching measures.",
        params={"title": "A faster website", "left_label": "Before", "right_label": "After", "metrics": [
            {"label": "Load time", "left": 4.8, "right": 1.6, "suffix": " s", "decimals": 1, "better": "lower"},
            {"label": "Page size", "left": 3.2, "right": 1.1, "suffix": " MB", "decimals": 1, "better": "lower"},
            {"label": "Performance score", "left": 48, "right": 96, "better": "higher"}],
            "source": "Example results. Replace with your measurements."},
        settings={"theme": "clean"}, tags=["before after", "performance", "example data"]),
    Preset(id="plan-comparison", title="Compare two plans", summary="Price, storage and seats in a clear two-column comparison.",
        params={"title": "Which plan fits?", "left_label": "Starter", "right_label": "Team", "metrics": [
            {"label": "Monthly price", "left": 12, "right": 29, "prefix": "$"},
            {"label": "Storage", "left": 10, "right": 100, "suffix": " GB", "better": "higher"},
            {"label": "Seats included", "left": 1, "right": 5, "better": "higher"}],
            "takeaway": "Choose the capacity your team needs", "source": "Example plans"},
        settings={"theme": "midnight"}, tags=["plans", "pricing", "product", "example data"]),
    Preset(id="month-over-month", title="This month vs last", summary="Put two periods side by side, with three business measures.",
        params={"title": "A month of progress", "left_label": "Last month", "right_label": "This month", "metrics": [
            {"label": "Revenue", "left": 18000, "right": 24000, "prefix": "$", "better": "higher"},
            {"label": "Orders", "left": 320, "right": 410, "better": "higher"},
            {"label": "Repeat customers", "left": 28, "right": 36, "suffix": "%", "better": "higher"}],
            "source": "Example monthly figures"},
        settings={"theme": "newsroom"}, tags=["monthly", "business", "growth", "example data"]),
    Preset(id="ab-results", title="A/B test results", summary="Two variants, one conversion measure, with the uplift calculated.",
        params={"title": "One change. Measurable results.", "left_label": "Version A", "right_label": "Version B",
            "metrics": [{"label": "Conversion rate", "left": 2.4, "right": 3.1, "suffix": "%", "decimals": 1,
                         "better": "higher"}], "source": "Example A/B results"},
        settings={"theme": "pastel", "aspect": "1:1"}, tags=["A/B", "experiment", "conversion", "example data"]),
    Preset(id="cost-comparison", title="Compare running costs", summary="Show the cost of two alternatives over the same period.",
        params={"title": "What does it cost to run?", "left_label": "Option A", "right_label": "Option B",
            "metrics": [{"label": "Annual running cost", "left": 1240, "right": 680, "prefix": "$", "better": "lower"}],
            "source": "Example estimate. Same usage and period for both."},
        settings={"theme": "chalk"}, tags=["cost", "savings", "comparison", "example data"]),
    Preset(id="product-head-to-head", title="Product head-to-head", summary="Compare battery life, weight and price without declaring one winner.",
        params={"title": "Pick what matters to you", "left_label": "Model A", "right_label": "Model B", "metrics": [
            {"label": "Battery life", "left": 12, "right": 18, "suffix": " h", "better": "higher"},
            {"label": "Weight", "left": 1.2, "right": 1.6, "suffix": " kg", "decimals": 1, "better": "lower"},
            {"label": "Price", "left": 899, "right": 1099, "prefix": "$", "better": "lower"}],
            "takeaway": "Different strengths. Your priorities decide.", "source": "Example specifications"},
        settings={"theme": "clean"}, tags=["product", "specifications", "versus", "example data"]),
]
