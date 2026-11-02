"""A current value, a target and an animated, numerically accurate progress display."""
from typing import Literal

from pydantic import ConfigDict

from studio.schema import Preset, TemplateMeta, TemplateParams, choice, integer, number, text

META = TemplateMeta(
    id="goal_progress", title="Goal progress", category="numbers",
    summary="A ring, a bar or milestone blocks showing the distance to a real target.",
    when_to_use="Fundraising, savings, project completion, reading goals and sales targets. "
                "The percentage is calculated from current / target; values above the goal remain visible.",
    not_for="A countdown: use countdown. Historical trends: use chart. This is a fixed snapshot, not a live tracker.",
    default_length=8, min_length=4, max_length=30,
    tags=["goal", "progress", "target", "fundraising", "savings", "milestone"],
)


class Params(TemplateParams):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)
    title: str = text("Closer every day", title="Title", max_length=48)
    current: float = number(12400, title="Current value", ge=0, le=999_999_999)
    target: float = number(20000, title="Target", ge=0.01, le=999_999_999)
    prefix: str = text("$", title="Before the number", max_length=4)
    suffix: str = text("", title="Unit", max_length=8)
    decimals: int = integer(0, title="Decimal places", ge=0, le=2)
    style: Literal["ring", "bar", "segments"] = choice("ring", title="Progress style",
        labels={"ring": "Ring", "bar": "Progress bar", "segments": "Milestone blocks"})
    note: str = text("Every contribution brings us closer", title="Note", max_length=80)


PRESETS = [
    Preset(id="fundraising-goal", title="Fundraising goal", summary="Money raised, the full target and the percentage reached.",
        params={"title": "Help build the next chapter", "current": 12400, "target": 20000, "prefix": "$",
            "note": "Example campaign · Every contribution counts"},
        settings={"theme": "clean"}, tags=["fundraising", "charity", "goal", "example data"]),
    Preset(id="savings-goal", title="Savings goal", summary="A growing bar showing progress toward a savings target.",
        params={"title": "A little closer to the trip", "current": 3250, "target": 5000, "prefix": "$",
            "style": "bar", "note": "Example savings plan"},
        settings={"theme": "pastel"}, tags=["savings", "money", "target", "example data"]),
    Preset(id="project-completion", title="Project completion", summary="Completed tasks out of the total, shown as milestone blocks.",
        params={"title": "The launch is taking shape", "current": 37, "target": 50, "prefix": "",
            "suffix": " tasks", "style": "segments", "note": "Example project · One task at a time"},
        settings={"theme": "midnight"}, tags=["project", "tasks", "progress", "example data"]),
    Preset(id="reading-challenge", title="Reading challenge", summary="Books finished out of your reading goal, with a progress ring.",
        params={"title": "One more chapter", "current": 18, "target": 24, "prefix": "", "suffix": " books",
            "note": "Example reading goal"},
        settings={"theme": "chalk", "aspect": "9:16"}, tags=["reading", "books", "challenge", "example data"]),
    Preset(id="sales-target", title="Sales target", summary="Show a target exceeded, with the true percentage still visible.",
        params={"title": "Beyond the target", "current": 54000, "target": 50000, "prefix": "$",
            "style": "bar", "note": "Example quarterly result"},
        settings={"theme": "newsroom"}, tags=["sales", "target", "business", "example data"]),
]
