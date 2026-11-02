"""A small photo story, with time to enjoy every picture."""
from typing import Literal, Optional

from pydantic import field_validator

from studio.schema import HexColor, Item, Preset, TemplateMeta, TemplateParams, choice, color, image, items, number
from studio.schema import text as text_field

META = TemplateMeta(
    id="slideshow", title="Pictures & captions", category="creator",
    summary="A photo story with gentle zooms, captions and soft changes between pictures.",
    when_to_use="A holiday recap, product collection or school event with 2 to 12 pictures. "
                "Each picture has an optional caption. Empty pictures become soft gradient panels.",
    not_for="A comparison of two pictures (use Before & after) or a long text presentation.",
    default_aspect="9:16", min_length=4, max_length=124, default_length=12,
    length_from_params=True, tags=["photos", "slideshow", "holiday", "product", "school", "recap"])


class Slide(Item):
    picture: Optional[str] = image(title="Picture", crop="free",
        description="Choose a picture for this moment. Leave empty for a soft color panel.")
    caption: str = text_field("", title="Caption", max_length=80,
        description="A short line about this picture, up to 80 characters. Leave empty for no caption.")

    @field_validator("caption")
    @classmethod
    def _tidy(cls, value):
        return " ".join(value.split())


class Params(TemplateParams):
    title: str = text_field("A few *good moments*", title="Title", max_length=60,
        help="Optional. Put *asterisks* around words to color them.",
        description="Optional title above the pictures. Put *asterisks* around a word to color it.")
    slides: list[Slide] = items([Slide(caption="A day to remember"), Slide(caption="More days like this")],
        title="Pictures", min_items=2, max_items=12, item_title="Picture",
        help="Add 2 to 12 pictures with optional captions.",
        description="2 to 12 pictures, each with an optional caption. Empty pictures show soft color panels.")
    seconds_per_slide: float = number(4, title="Seconds per picture", ge=2, le=10, step=.5,
        help="Time for each picture, including the soft change to the next one.",
        description="2 to 10 seconds per picture. More pictures make a longer video.")
    caption_position: Literal["bottom", "top"] = choice("bottom", title="Caption position",
        labels={"bottom": "Bottom", "top": "Top"},
        description="Where the caption sits inside each picture.")
    accent: HexColor = color(None, title="Accent color")

    @field_validator("title")
    @classmethod
    def _tidy(cls, value):
        return " ".join(value.split())

    @field_validator("slides", mode="before")
    @classmethod
    def _count(cls, value):
        if isinstance(value, list) and not 2 <= len(value) <= 12:
            raise ValueError("Choose between 2 and 12 pictures. Empty pictures can stay as color panels.")
        return value

    @field_validator("seconds_per_slide", mode="before")
    @classmethod
    def _seconds(cls, value):
        if isinstance(value, (int, float)) and not 2 <= value <= 10:
            raise ValueError("Choose between 2 and 10 seconds for each picture.")
        return value


PRESETS = [
    Preset(id="holiday-recap", title="Holiday recap", summary="Three moments from a weekend by the coast.",
        params={"title": "A weekend to *remember*", "slides": [
            {"caption": "First stop: a walk along the harbour"},
            {"caption": "An afternoon with nowhere to hurry"},
            {"caption": "One last sunset before the trip home"}], "seconds_per_slide": 4},
        settings={"theme": "pastel", "energy": "calm"}, tags=["holiday", "travel", "memories"]),
    Preset(id="product-showcase", title="Product showcase", summary="A simple three-piece ceramics collection.",
        params={"title": "Meet the *morning collection*", "slides": [
            {"caption": "Everyday mug · made for slow mornings"},
            {"caption": "Breakfast bowl · a little room for more"},
            {"caption": "Serving plate · bring everyone together"}], "caption_position": "top"},
        settings={"theme": "clean", "aspect": "1:1"}, tags=["product", "collection", "shop"]),
    Preset(id="school-event", title="School event", summary="Highlights from a school garden day.",
        params={"title": "Our *garden day*", "slides": [
            {"caption": "Year 4 planted the first seeds"},
            {"caption": "Families helped build the raised beds"},
            {"caption": "Thank you to everyone who joined us"}], "seconds_per_slide": 3},
        settings={"theme": "chalk", "aspect": "16:9"}, tags=["school", "event", "community"]),
]
