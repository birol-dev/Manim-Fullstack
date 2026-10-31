"""A small set of labeled numbers, drawn as bars, a line or a pie."""
from typing import Literal
import math

from pydantic import field_validator, model_validator

from studio.schema import HexColor, Item, Preset, TemplateMeta, TemplateParams, choice, color, integer, items, number
from studio.schema import text as text_field

META = TemplateMeta(id="chart", title="Animated chart", category="numbers",
    summary="Bars, a line or a pie that draws itself while the numbers count up.",
    when_to_use="Comparing 2 to 12 labeled values: quarterly sales, survey answers or monthly visitors. "
                "Bars and lines accept negative values and zero. A pie shows shares of a positive total.",
    not_for="Large spreadsheets, live data or several different sets of numbers on the same chart.",
    default_aspect="16:9", min_length=5, max_length=40, default_length=8,
    tags=["chart", "bars", "line", "pie", "sales", "survey", "visitors", "numbers"])


class Datum(Item):
    label: str = text_field("", title="Label", max_length=20,
        description="What this value is for, up to 20 characters. Long labels wrap onto another line.")
    value: float = number(0, title="Value", ge=-1_000_000, le=1_000_000,
        description="A number from -1,000,000 to 1,000,000. Pie charts need zero or positive values.")

    @field_validator("label")
    @classmethod
    def _filled(cls, value):
        if not value.strip():
            raise ValueError("Write a label for each number.")
        return " ".join(value.split())

    @field_validator("value", mode="before")
    @classmethod
    def _finite(cls, value):
        if isinstance(value, (int, float)) and (not math.isfinite(value) or abs(value) > 1_000_000):
            raise ValueError("Use a number between -1,000,000 and 1,000,000.")
        return value


class Params(TemplateParams):
    title: str = text_field("A *strong* quarter", title="Title", max_length=48,
        help="Put *asterisks* around words to color them.",
        description="What the chart shows, up to 48 characters. Put *asterisks* around a word to color it.")
    values: list[Datum] = items([Datum(label="Q1", value=12000), Datum(label="Q2", value=18000),
        Datum(label="Q3", value=15500), Datum(label="Q4", value=24000)],
        title="Numbers", min_items=2, max_items=12, item_title="Number", widget="table",
        description="2 to 12 labels and values. You can paste the rows from a spreadsheet.")
    chart_type: Literal["bars", "line", "pie"] = choice("bars", title="Chart type",
        labels={"bars": "Bars", "line": "Line", "pie": "Pie"},
        option_help={"bars": "Compare the size of each value, including negatives.",
                     "line": "Show how values change in the order you enter them.",
                     "pie": "Show parts of a whole. Values must be zero or positive."})
    decimals: int = integer(0, title="Decimal places", ge=0, le=2,
        description="Show 0, 1 or 2 digits after the decimal point. Number separators follow your language.")
    accent: HexColor = color(None, title="Accent color")

    @field_validator("title")
    @classmethod
    def _filled(cls, value):
        if not value.strip():
            raise ValueError("Write a title for the chart.")
        return " ".join(value.split())

    @field_validator("values", mode="before")
    @classmethod
    def _count(cls, value):
        if isinstance(value, list) and not 2 <= len(value) <= 12:
            raise ValueError("Add between 2 and 12 labeled numbers.")
        return value

    @model_validator(mode="after")
    def _pie_values(self):
        if self.chart_type == "pie":
            if any(row.value < 0 for row in self.values):
                raise ValueError("Pie charts cannot show negative values. Use bars or a line instead.")
            if not any(row.value > 0 for row in self.values):
                raise ValueError("Give at least one number a value above zero to make a pie chart.")
        return self


PRESETS = [
    Preset(id="sales-by-quarter", title="Sales by quarter", summary="Example quarterly sales for a small shop.",
        params={"title": "Sales by *quarter*", "values": [
            {"label": "Q1", "value": 12000}, {"label": "Q2", "value": 18000},
            {"label": "Q3", "value": 15500}, {"label": "Q4", "value": 24000}], "chart_type": "bars"},
        settings={"theme": "clean"}, tags=["sales", "quarter", "business", "example data"]),
    Preset(id="survey-results", title="Survey results", summary="Example answers to a community survey.",
        params={"title": "Which event should we *run next*?", "values": [
            {"label": "Outdoor cinema", "value": 45}, {"label": "Food market", "value": 30},
            {"label": "Live music", "value": 25}], "chart_type": "pie"},
        settings={"theme": "pastel", "aspect": "1:1"}, tags=["survey", "community", "example data"]),
    Preset(id="monthly-visitors", title="Monthly visitors", summary="Example website visits across six months.",
        params={"title": "Monthly *visitors*", "values": [
            {"label": "January", "value": 820}, {"label": "February", "value": 1040},
            {"label": "March", "value": 980}, {"label": "April", "value": 1320},
            {"label": "May", "value": 1510}, {"label": "June", "value": 1840}], "chart_type": "line"},
        settings={"theme": "midnight", "aspect": "9:16"}, tags=["visitors", "website", "example data"]),
]
