"""Lower third: the name strip that sits at the bottom of a talking-head video."""

from typing import Literal

from pydantic import field_validator

from studio.schema import HexColor, Preset, TemplateMeta, TemplateParams, choice, color, integer
from studio.schema import text as text_field

META = TemplateMeta(
    id="lower_third",
    title="Name strip",
    summary="A name and role that slide in at the bottom of your video, ready to lay over your own footage.",
    category="creator",
    when_to_use="Putting a presenter's name, a podcast guest or a place on your own recording. The video "
                "exports see-through, so you can drop it on top of a camera clip in any video editor. "
                "The strip animates in, stays for the chosen time, then slides away.",
    not_for="A finished video with a background (use an announcement, quote or steps template). A caption "
            "that follows every spoken word (a subtitle tool). Several names at once.",
    default_aspect="16:9",
    min_length=2,
    max_length=30,
    default_length=6,
    tags=["lower third", "name", "caption", "presenter", "podcast", "interview", "overlay", "transparent"],
)

STYLES = {"panel": "Soft card", "block": "Solid color", "underline": "Underline"}
SIDES = {"left": "Left", "center": "Centered", "right": "Right"}


class Params(TemplateParams):
    name: str = text_field(
        "Maya Torres", title="Name", max_length=36, placeholder="Maya Torres",
        help="The name to show.",
        description="The person's name or the main line, up to 36 characters. It can wrap onto two lines.")
    role: str = text_field(
        "", title="Second line", max_length=48, placeholder="Product designer",
        help="A role, place or short line under the name.",
        description="A second line under the name, e.g. 'Product designer' or 'Live from Moda'. "
                    "Up to 48 characters. Leave empty for just the name.")
    side: Literal["left", "center", "right"] = choice(
        "left", title="Position", labels=SIDES,
        option_help={"left": "Sits at the bottom left.", "center": "Sits at the bottom center.",
                     "right": "Sits at the bottom right."},
        description="Where the strip sits at the bottom of the frame: left, centered or right.")
    style: Literal["panel", "block", "underline"] = choice(
        "panel", title="Style", labels=STYLES,
        option_help={"panel": "A soft card with a colored edge.",
                     "block": "A solid card in your accent color.",
                     "underline": "A soft card with a colored line under the name."},
        description="Soft card: a light or dark card with an accent bar. Solid color: the whole card in the "
                    "accent color. Underline: a soft card with a colored line along the bottom.")
    hold: int = integer(
        4, title="Time on screen", ge=1, le=25, unit="seconds",
        help="How long the strip stays before it slides out.",
        description="How many seconds the strip stays fully visible before it slides out. The video is about "
                    "one second longer than this.")
    accent: HexColor = color(None, title="Accent color",
                             help="Color for the bar, card or line.",
                             description="Color of the bar, solid card or underline. Empty = the theme's.")

    @field_validator("name")
    @classmethod
    def _has_a_name(cls, value):
        if not value.strip():
            raise ValueError("Write the name to show.")
        return " ".join(value.split())

    @field_validator("role")
    @classmethod
    def _one_line(cls, value):
        return " ".join(value.split())


PRESETS = [
    Preset(
        id="presenter-name", title="Presenter name",
        summary="A calm name card for the start of a talking-head video.",
        params={"name": "Maya Torres", "role": "Product designer at Northwind", "side": "left",
                "style": "panel", "hold": 5},
        settings={"theme": "clean", "background": {"kind": "transparent"}},
        tags=["presenter", "name", "talking head", "introduction"],
    ),
    Preset(
        id="podcast-guest", title="Podcast guest",
        summary="A bold guest card for an interview or podcast clip.",
        params={"name": "Dr. Elif Demir", "role": "Author of The Quiet Kitchen", "side": "left",
                "style": "block", "hold": 5},
        settings={"theme": "midnight", "background": {"kind": "transparent"}},
        tags=["podcast", "guest", "interview", "author"],
    ),
    Preset(
        id="location-tag", title="Location tag",
        summary="A place and date for a travel or behind-the-scenes clip.",
        params={"name": "Moda, Istanbul", "role": "Filmed on 21 June", "side": "right",
                "style": "underline", "hold": 4},
        settings={"theme": "pastel", "background": {"kind": "transparent"}},
        tags=["location", "travel", "place", "behind the scenes"],
    ),
]
