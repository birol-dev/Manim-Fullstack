"""Field helpers, template metadata, presets, and render settings. No Manim import.

A template's ``schema.py`` declares ``META``, ``Params`` and ``PRESETS`` with these
helpers. ``Params.model_json_schema()`` drives the app's form and is the MCP tool's
input schema, so every field gets a ``title`` (the form label) and, where it helps an
agent, a ``description``. ``x-widget`` tells the form which control to draw. Optional
``x-help`` replaces the description in the UI; ``x-option-help`` describes just the
selected enum value. Agent-facing descriptions stay intact.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator
from .sound import SoundSettings

Aspect = Literal["16:9", "9:16", "1:1", "4:5"]
ASPECTS: tuple = ("16:9", "9:16", "1:1", "4:5")
Category = Literal["announce", "celebrate", "timers", "creator", "teach", "numbers", "sports", "travel", "screens"]
CATEGORY_TITLES = {
    "announce": "Announce something",
    "celebrate": "Celebrate",
    "timers": "Timers & countdowns",
    "creator": "For your videos",
    "teach": "Teach & quiz",
    "numbers": "Show numbers",
    "sports": "Sports & clubs",
    "travel": "Maps & travel",
    "screens": "Shop screen loops",
}
Energy = Literal["calm", "normal", "punchy"]
Ending = Literal["hold", "fade", "cut"]

HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
TEMPLATE_ID = re.compile(r"^[a-z][a-z0-9_]{1,40}$")


def _extra(widget: str, **more) -> dict:
    return {"x-widget": widget, **{f"x-{k.replace('_', '-')}": v for k, v in more.items() if v is not None}}


def text(default: str = "", *, title: str, max_length: int = 60, description: Optional[str] = None,
         placeholder: Optional[str] = None, multiline: bool = False, help: Optional[str] = None) -> Any:
    """One line of text (or a paragraph with ``multiline``). Templates fit it to the frame."""
    return Field(default, title=title, description=description, max_length=max_length,
                 json_schema_extra=_extra("textarea" if multiline else "text", placeholder=placeholder, help=help))


def number(default: float = 0, *, title: str, ge: Optional[float] = None, le: Optional[float] = None,
           description: Optional[str] = None, step: Optional[float] = None, unit: Optional[str] = None,
           help: Optional[str] = None) -> Any:
    return Field(default, title=title, description=description, ge=ge, le=le,
                 json_schema_extra=_extra("number", step=step, unit=unit, help=help))


def integer(default: int = 0, *, title: str, ge: Optional[int] = None, le: Optional[int] = None,
            description: Optional[str] = None, unit: Optional[str] = None, choice_of: Optional[str] = None,
            help: Optional[str] = None) -> Any:
    """An integer; ``choice_of`` presents a 1-based index into a sibling array as choices."""
    return Field(default, title=title, description=description, ge=ge, le=le,
                 json_schema_extra=_extra("integer", unit=unit, choice_of=choice_of, help=help))


def duration(default: float, *, title: str, ge: float = 1, le: float = 3600, description: Optional[str] = None,
             help: Optional[str] = None) -> Any:
    """Seconds, shown as mm:ss in the form."""
    return Field(default, title=title, description=description, ge=ge, le=le,
                 json_schema_extra=_extra("duration", help=help))


def choice(default: str, *, title: str, labels: Optional[dict] = None, description: Optional[str] = None,
           help: Optional[str] = None, option_help: Optional[dict[str, str]] = None) -> Any:
    """Use with a ``Literal[...]`` annotation. ``labels`` maps values to what the form shows."""
    return Field(default, title=title, description=description,
                 json_schema_extra=_extra("choice", labels=labels, help=help, option_help=option_help))


def toggle(default: bool, *, title: str, description: Optional[str] = None, help: Optional[str] = None) -> Any:
    return Field(default, title=title, description=description, json_schema_extra=_extra("toggle", help=help))


def color(default: Optional[str] = None, *, title: str, description: Optional[str] = None,
          help: Optional[str] = None) -> Any:
    """A ``#RRGGBB`` color, or None for the theme's accent. Annotate the field with ``HexColor``."""
    return Field(default, title=title, description=description or "Leave empty to use the theme color.",
                 json_schema_extra=_extra("color", help=help if help is not None else "Choose a color, or use the theme color."))


def image(*, title: str, description: Optional[str] = None, shape: Literal["any", "circle", "logo"] = "any",
          help: Optional[str] = None, crop: Optional[str] = None) -> Any:
    """An uploaded asset's file name, or None. ``crop`` only controls the editor's crop mask."""
    if crop is not None and (not isinstance(crop, str) or
                             (crop not in ("circle", "free") and not re.fullmatch(r"[1-9][0-9]{0,3}:[1-9][0-9]{0,3}", crop))):
        raise ValueError("crop must be 'circle', 'free', or a positive aspect ratio such as '16:9'")
    return Field(None, title=title, description=description or "Optional picture.",
                 json_schema_extra=_extra("image", shape=shape, help=help, crop=crop))


def icon(default: Optional[str] = None, *, title: str, description: Optional[str] = None,
         help: Optional[str] = None) -> Any:
    """A name from the bundled icon set (``studio.icons.ICON_NAMES``), or None."""
    return Field(default, title=title, description=description or "Name of a bundled icon, e.g. 'gift' or 'clock'.",
                 json_schema_extra=_extra("icon", help=help if help is not None else "Choose an icon, or leave empty for none."))


def datetime_text(default: str = "", *, title: str, description: Optional[str] = None, help: Optional[str] = None) -> Any:
    """A date and/or time as the person wants it written ("Sat 14 June, 7 pm"). Shown as typed."""
    return Field(default, title=title, description=description, max_length=60,
                 json_schema_extra=_extra("text", placeholder="Sat 14 June, 7 pm", help=help))


def items(default: list, *, title: str, min_items: int = 1, max_items: int = 10, description: Optional[str] = None,
          widget: Literal["list", "table"] = "list", item_title: str = "Item", help: Optional[str] = None) -> Any:
    """A repeated group (``list[SomeModel]``). ``table`` draws a spreadsheet grid that accepts pasted rows."""
    return Field(default, title=title, description=description, min_length=min_items, max_length=max_items,
                 json_schema_extra=_extra(widget, item_title=item_title, help=help))


def check_color(value):
    if value in (None, ""):
        return None
    if not isinstance(value, str) or not HEX_COLOR.match(value):
        raise ValueError("Use a color like #2563EB.")
    return value.upper()


# Annotate optional color fields with this: ``accent: HexColor = color(title="Accent")``.
HexColor = Annotated[Optional[str], BeforeValidator(check_color)]


class TemplateParams(BaseModel):
    """Base for every template's ``Params``. Unknown fields are refused, so agents learn the schema."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Item(BaseModel):
    """Base for repeated groups inside ``Params``."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TemplateMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    version: int = 1
    title: str
    summary: str = Field(description="One line for the gallery card.")
    category: Category
    when_to_use: str = Field(description="For agents: what this template is for.")
    not_for: str = Field("", description="For agents: what to use instead, and when.")
    aspects: list[Aspect] = list(ASPECTS)
    default_aspect: Aspect = "16:9"
    min_length: float = 3
    max_length: float = 60
    default_length: float = 8
    loopable: bool = False
    export_fps: Optional[int] = Field(None, description="Suggested frame rate for exports (long timers use less).")
    length_from_params: bool = Field(False, description="The params set the length (e.g. a timer's duration).")
    tags: list[str] = []

    @field_validator("id")
    @classmethod
    def _id(cls, value):
        if not TEMPLATE_ID.match(value):
            raise ValueError("template ids are lowercase letters, digits and underscores")
        return value


class Preset(BaseModel):
    """A gallery card: a template with ready-made content and look."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    summary: str
    category: Optional[Category] = None  # defaults to the template's category
    params: dict = {}
    settings: dict = {}
    tags: list[str] = []


class Background(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["theme", "solid", "gradient", "transparent"] = "theme"
    color: HexColor = None
    color2: HexColor = None


class Brand(BaseModel):
    """Overrides from the brand kit: applied on top of the theme."""

    model_config = ConfigDict(extra="forbid")

    accent: HexColor = None
    accent2: HexColor = None
    font: Optional[str] = Field(None, max_length=60)
    logo: Optional[str] = Field(None, max_length=200)


class RenderSettings(BaseModel):
    """Controls every template shares; templates read them through the kit."""

    model_config = ConfigDict(extra="forbid")
    sound: SoundSettings = Field(default_factory=SoundSettings)

    aspect: Aspect = "16:9"
    length: Optional[float] = Field(None, ge=1, le=3600, description="Seconds; None uses the template default.")
    theme: str = "clean"
    background: Background = Background()
    brand: Brand = Brand()
    energy: Energy = "normal"
    ending: Ending = "hold"
    safe_zone: bool = Field(False, description="Keep text clear of TikTok/Reels buttons (bottom and right).")
    locale: str = Field("en", pattern=r"^[a-z]{2}(-[A-Z]{2})?$", description="Number and date formatting, e.g. en, tr, de.")
