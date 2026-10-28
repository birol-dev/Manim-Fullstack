"""Year in review: "My 2026 in numbers", a shareable recap of 3 to 6 stats that count up."""

from typing import Literal, Optional

from studio.schema import Item, Preset, TemplateMeta, TemplateParams, choice, icon, items, number, text, toggle
from studio.schema import image as image_field

META = TemplateMeta(
    id="year_in_review",
    title="Year in numbers",
    summary="Your year as a few big numbers that count up, then one recap to share.",
    category="celebrate",
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
    photo: Optional[str] = image_field(title="Photo", shape="circle",
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
        description="moments: each number gets the full screen in turn, then the recap; grid: the recap "
                    "grid builds number by number.")


PRESETS = [
    Preset(
        id="personal-year", title="My year in numbers", summary="Books, runs, coffees and trips: your year, counted.",
        params={
            "year": "2026",
            "title": "My year in *numbers*",
            "name": "@maya.reads",
            "stats": [
                {"value": 38, "label": "books read", "icon": "book-open"},
                {"value": 1240, "label": "kilometres run", "suffix": "km", "icon": "footprints"},
                {"value": 612, "label": "cups of coffee", "icon": "coffee"},
                {"value": 9, "label": "countries visited", "icon": "plane"},
            ],
            "closing": "Here's to *2027*!",
            "style": "moments",
        },
        settings={"theme": "pastel"},
        tags=["personal", "goals", "reading", "running"],
    ),
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
    Preset(
        id="creator-year", title="Creator year", summary="Followers, videos and views, with short numbers like 18.6M.",
        params={
            "year": "2026",
            "title": "My year on camera",
            "name": "@leo.makes",
            "stats": [
                {"value": 128400, "label": "new followers", "icon": "users", "compact": True},
                {"value": 214, "label": "videos posted", "icon": "video"},
                {"value": 18600000, "label": "views", "icon": "trending-up", "compact": True},
                {"value": 2300000, "label": "likes", "icon": "heart", "compact": True},
                {"value": 12, "label": "brand collabs", "icon": "star"},
            ],
            "closing": "Thank you for *watching*. More soon!",
            "style": "moments",
        },
        settings={"theme": "pop", "energy": "punchy"},
        tags=["creator", "followers", "youtube", "tiktok", "instagram"],
    ),
    Preset(
        id="fitness-year", title="Training year", summary="Kilometres, workouts and personal bests from your "
                                                          "training log.",
        params={
            "year": "2026",
            "title": "A year of *training*",
            "name": "Coach Deniz",
            "stats": [
                {"value": 1842, "label": "kilometres run", "suffix": "km", "icon": "footprints"},
                {"value": 186, "label": "workouts", "icon": "dumbbell"},
                {"value": 4210, "label": "kilometres on the bike", "suffix": "km", "icon": "bike"},
                {"value": 312, "label": "hours of training", "suffix": "h", "icon": "flame"},
                {"value": 3, "label": "marathons finished", "icon": "trophy"},
                {"value": 14, "label": "personal bests", "icon": "trending-up"},
            ],
            "closing": "Stronger in *2027*",
            "style": "moments",
        },
        settings={"theme": "midnight"},
        tags=["fitness", "running", "gym", "sport", "training"],
    ),
    Preset(
        id="family-travel-year", title="Family year", summary="Trips, flights, photos and pizza nights: a year "
                                                              "to remember.",
        params={
            "year": "2026",
            "title": "Our family year",
            "name": "The Kaya family",
            "stats": [
                {"value": 7, "label": "countries explored", "icon": "globe"},
                {"value": 23, "label": "flights taken", "icon": "plane"},
                {"value": 4860, "label": "photos taken", "icon": "camera"},
                {"value": 14, "label": "mountains climbed", "icon": "mountain"},
                {"value": 52, "label": "pizza nights", "icon": "pizza"},
            ],
            "closing": "Same time *next year*?",
            "style": "moments",
        },
        settings={"theme": "chalk", "energy": "calm"},
        tags=["family", "travel", "holiday", "memories"],
    ),
]
