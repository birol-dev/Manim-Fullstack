"""Year in review: "My 2026 in numbers", a shareable recap of 3 to 6 stats that count up."""

from typing import Literal, Optional

from studio.schema import Item, Preset, TemplateMeta, TemplateParams, choice, icon, items, number, text, toggle
from studio.schema import image as image_field

META = TemplateMeta(
    id="year_in_review",
    title="Year in numbers",
    summary="Your year as a few big numbers that count up, then one recap to share.",
    category="numbers",
    when_to_use="A year-end (or season, or anniversary) recap for a person, family, team or small business: "
                "3 to 6 numbers with a short label each (books read, km run, coffees served, followers), "
                "the year big at the start and a recap grid of all numbers at the end.",
    not_for="A single big number or milestone (a milestone/celebration template), a chart of values over "
            "time (a chart template), a list of more than 6 numbers.",
    default_aspect="9:16",
    min_length=8,
    max_length=40,
    default_length=14,
    tags=["year in review", "recap", "wrapped", "stats", "numbers", "new year", "anniversary", "milestones"],
)


class Stat(Item):
    value: float = number(0, title="Number", ge=0, le=999_999_999,
                          description="The number to count up to, e.g. 38 or 12480 or 4.9.")
    label: str = text("", title="What it counts", max_length=32, placeholder="books read",
                      description="A few words under the number, e.g. 'books read' or 'happy customers'.")
    prefix: str = text("", title="Before the number", max_length=3, placeholder="$",
                       description="Optional, e.g. '$', '€' or '+'.")
    suffix: str = text("", title="After the number", max_length=8, placeholder="km",
                       description="Optional unit, e.g. 'km', 'hours', '%' or '+'. Units are written smaller.")
    icon: Optional[str] = icon(None, title="Icon", description="Optional icon, e.g. book-open, coffee, plane.")
    compact: bool = toggle(False, title="Short number (12.4K)",
                           description="Write big numbers short: 12,480 as 12.5K, 2,300,000 as 2.3M.")


STYLES = {"moments": "One by one", "grid": "Grid build"}


class Params(TemplateParams):
    year: str = text("2026", title="Year", max_length=9, description="Shown big at the start, e.g. 2026 or 2025/26.")
    title: str = text("My year in numbers", title="Title", max_length=40,
                      description="A short title under the year. Wrap a word in *asterisks* to color it.")
    name: str = text("", title="Name or handle", max_length=30, placeholder="@yourname",
                     description="Optional: your name, handle or business name.")
    photo: Optional[str] = image_field(title="Photo", shape="circle", crop="circle",
                                       description="Optional profile photo or logo, shown in a circle.")
    stats: list[Stat] = items(
        [Stat(value=38, label="books read", icon="book-open"),
         Stat(value=1240, label="kilometres run", suffix="km", icon="footprints"),
         Stat(value=612, label="cups of coffee", icon="coffee"),
         Stat(value=9, label="countries visited", icon="plane")],
        title="Your numbers", min_items=3, max_items=6, item_title="Number",
        description="3 to 6 numbers, each with a short label.")
    closing: str = text("Here's to *2027*!", title="Closing line", max_length=60,
                        description="The last line, under the recap. Wrap a word in *asterisks* to color it.")
    style: Literal["moments", "grid"] = choice(
        "moments", title="Style", labels=STYLES,
        option_help={"moments": "Each number fills the screen, then all appear in a recap.",
                     "grid": "The recap grid builds one number at a time."},
        description="One by one: each number gets the full screen in turn, then the recap. Grid build: the "
                    "recap grid builds number by number.")


PRESETS = [
    Preset(
        id="small-business-year", title="Our year at the shop", summary="Thank your customers with the numbers "
                                                                        "behind your year.",
        params={
            "year": "2026",
            "title": "Our year at Bean & Bloom",
            "name": "Bean & Bloom Café",
            "stats": [
                {"value": 12480, "label": "coffees served", "icon": "coffee"},
                {"value": 3215, "label": "regulars and new faces", "icon": "users"},
                {"value": 487, "label": "five-star reviews", "icon": "star"},
                {"value": 96, "label": "cakes baked every week", "icon": "heart"},
            ],
            "closing": "Thank you for a *wonderful* year!",
            "style": "grid",
        },
        settings={"theme": "clean"},
        tags=["business", "cafe", "shop", "customers", "thank you"],
    ),
]
