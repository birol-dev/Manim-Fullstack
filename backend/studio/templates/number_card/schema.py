"""One striking number or a small, animated KPI dashboard."""
from pydantic import ConfigDict

from studio.schema import Item, Preset, TemplateMeta, TemplateParams, integer, items, number, text, toggle

META = TemplateMeta(
    id="number_card", title="Number spotlight", category="numbers",
    summary="A big animated figure, or up to four clear KPI cards with labels and context.",
    when_to_use="A statistic, a revenue counter, audience size, savings, a research finding or a compact KPI summary. "
                "Numbers animate from an editable starting value; units and decimal places are independent for each card.",
    not_for="Changes over time: use chart. Two alternatives: use comparison. Progress toward a target: use goal_progress.",
    default_length=8, min_length=4, max_length=30,
    tags=["number", "counter", "statistic", "KPI", "dashboard", "revenue"],
)


class Figure(Item):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)
    label: str = text("People reached", title="Label", max_length=32)
    value: float = number(12480, title="Final number", ge=-999_999_999, le=999_999_999)
    start: float = number(0, title="Count from", ge=-999_999_999, le=999_999_999)
    prefix: str = text("", title="Before the number", max_length=4)
    suffix: str = text("", title="Unit", max_length=8)
    decimals: int = integer(0, title="Decimal places", ge=0, le=2)
    compact: bool = toggle(False, title="Short number (12.5K)")
    note: str = text("", title="Context", max_length=64)


class Params(TemplateParams):
    title: str = text("The number that matters", title="Title", max_length=48)
    figures: list[Figure] = items([Figure()], title="Numbers", min_items=1, max_items=4, item_title="Number")
    source: str = text("", title="Source or period", max_length=96)


PRESETS = [
    Preset(id="big-statistic", title="One big statistic", summary="Lead with one clear number and the context that makes it useful.",
        params={"title": "Small actions. Real reach.", "figures": [{"label": "People reached", "value": 12480,
            "note": "Across our community projects"}], "source": "Example statistic. Add your source."},
        settings={"theme": "clean"}, tags=["statistic", "reach", "example data"]),
    Preset(id="revenue-counter", title="Revenue counter", summary="A currency counter with a label, period and short context.",
        params={"title": "A strong month", "figures": [{"label": "Revenue", "value": 48650, "prefix": "$",
            "note": "From 620 completed orders"}], "source": "Example figures · October"},
        settings={"theme": "midnight"}, tags=["revenue", "money", "business", "example data"]),
    Preset(id="kpi-snapshot", title="KPI snapshot", summary="Three business numbers, shown together as a compact dashboard.",
        params={"title": "The month at a glance", "figures": [
            {"label": "Revenue", "value": 48650, "prefix": "$", "note": "+18% vs last month"},
            {"label": "Orders", "value": 620, "note": "+64 vs last month"},
            {"label": "Repeat customers", "value": 36.5, "suffix": "%", "decimals": 1,
             "note": "Share of all customers"}], "source": "Example monthly figures"},
        settings={"theme": "newsroom"}, tags=["KPI", "dashboard", "business", "example data"]),
    Preset(id="audience-counter", title="Audience counter", summary="Count from an earlier audience size to the latest total.",
        params={"title": "Growing together", "figures": [{"label": "Subscribers", "value": 25000,
            "start": 18000, "compact": True, "note": "From 18K to 25K this quarter"}], "source": "Example audience figures"},
        settings={"theme": "pastel", "aspect": "9:16"}, tags=["audience", "subscribers", "counter", "example data"]),
    Preset(id="percentage-spotlight", title="Percentage spotlight", summary="Make a survey percentage the focus, with room for its source.",
        params={"title": "What people told us", "figures": [{"label": "Would recommend us", "value": 92.4,
            "suffix": "%", "decimals": 1, "note": "Of customers who answered the survey"}],
            "source": "Example survey · Add sample size and dates"},
        settings={"theme": "chalk", "aspect": "1:1"}, tags=["percentage", "survey", "statistic", "example data"]),
    Preset(id="impact-in-numbers", title="Impact in numbers", summary="Four measures of a project's impact, each with its own unit.",
        params={"title": "What we made possible", "figures": [
            {"label": "Meals shared", "value": 8500}, {"label": "Volunteer hours", "value": 1240},
            {"label": "Waste avoided", "value": 320, "suffix": " kg"},
            {"label": "Neighbourhoods", "value": 12}], "source": "Example community project"},
        settings={"theme": "clean"}, tags=["impact", "community", "dashboard", "example data"]),
]
