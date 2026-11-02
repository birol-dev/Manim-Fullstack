"""Before & after: two pictures and a line that sweeps to reveal the change."""

from typing import Literal, Optional

from pydantic import field_validator, model_validator

from studio.schema import HexColor, Preset, TemplateMeta, TemplateParams, choice, color
from studio.schema import image as image_field
from studio.schema import text as text_field

META = TemplateMeta(
    id="before_after",
    title="Before & after",
    summary="Two pictures and a line that sweeps across: show a makeover, a redo or your progress.",
    category="compare",
    when_to_use="Showing a change with two pictures: a room or garden makeover, a design redo, a haircut, a "
                "fitness or renovation progress. The 'after' picture is revealed with a clean sweeping line. "
                "Leave a picture empty and a neat color panel takes its place, so it still works without photos.",
    not_for="More than two pictures, a slideshow of many moments, or a video that needs a long explanation. "
            "Use a steps or quote template for text-led stories.",
    default_aspect="16:9",
    min_length=4,
    max_length=20,
    default_length=7,
    tags=["before after", "makeover", "renovation", "progress", "transformation", "comparison", "then and now"],
)

DIRECTIONS = {"horizontal": "Side by side", "vertical": "Top and bottom"}
SPEEDS = {"slow": "Slow", "normal": "Normal", "fast": "Fast"}


class Params(TemplateParams):
    before: Optional[str] = image_field(
        title="Before picture", crop="free",
        help="Optional. Empty draws a color panel with the word.",
        description="The 'before' photo. It fills the frame. Leave empty to draw a neat color panel with "
                    "the before label, so the card still looks finished.")
    after: Optional[str] = image_field(
        title="After picture", crop="free",
        help="Optional. Empty draws a color panel with the word.",
        description="The 'after' photo, revealed by the sweeping line. Leave empty to draw a color panel "
                    "with the after label.")
    before_label: str = text_field(
        "Before", title="Before label", max_length=16, placeholder="Before",
        help="The word on the before side.",
        description="The word on the 'before' side, up to 16 characters (Before, Week 1, Old logo). "
                    "Leave empty for no label.")
    after_label: str = text_field(
        "After", title="After label", max_length=16, placeholder="After",
        help="The word on the after side.",
        description="The word on the 'after' side, up to 16 characters (After, Week 12, New logo). "
                    "Leave empty for no label.")
    headline: str = text_field(
        "", title="Headline", max_length=60, placeholder="Same room, new life",
        help="A line above the pictures. Optional.",
        description="An optional line above the pictures, up to 60 characters. Wrap a word in *asterisks* "
                    "to color it.")
    direction: Literal["horizontal", "vertical"] = choice(
        "horizontal", title="Picture layout", labels=DIRECTIONS,
        option_help={"horizontal": "Before on the left, After on the right. Reveals from the right edge.",
                     "vertical": "Before on top, After below. Reveals from the bottom edge."},
        description="Before is always first: left or top. After appears from the far edge. "
                    "Older left/right settings mean side by side; top/bottom mean top and bottom.")
    speed: Literal["slow", "normal", "fast"] = choice(
        "normal", title="Sweep speed", labels=SPEEDS,
        option_help={"slow": "A calm, slow reveal.", "normal": "A steady reveal.",
                     "fast": "A quick snap to the result."},
        description="How fast the line sweeps across: slow, normal or fast.")
    accent: HexColor = color(None, title="Accent color",
                             help="Color for the after panel, labels and line.",
                             description="Color of the after panel, the after label and the line. "
                                         "Empty = the theme's.")

    @field_validator("headline", "before_label", "after_label")
    @classmethod
    def _one_line(cls, value):
        return " ".join(value.split())

    @field_validator("direction", mode="before")
    @classmethod
    def _old_direction(cls, value):
        return {"left": "horizontal", "right": "horizontal", "top": "vertical",
                "bottom": "vertical"}.get(value, value)

    @model_validator(mode="after")
    def _different_pictures(self):
        if self.before and self.after and self.before == self.after:
            raise ValueError("Choose two different pictures for before and after.")
        return self

    @model_validator(mode="after")
    def _has_something_to_say(self):
        if not (self.before or self.after or self.before_label.strip() or self.after_label.strip()
                or self.headline.strip()):
            raise ValueError("Add a headline or a label so the video says what changed.")
        return self


PRESETS = [
    Preset(
        id="room-makeover", title="Room makeover",
        summary="The same room, before and after a weekend of work.",
        params={"before_label": "Before", "after_label": "After",
                "headline": "Same room, *new life*.", "direction": "left", "speed": "normal"},
        settings={"theme": "pastel"},
        tags=["makeover", "room", "home", "renovation", "interior"],
    ),
    Preset(
        id="design-redo", title="Design redo",
        summary="An old look and its fresh new version, side by side.",
        params={"before_label": "Old logo", "after_label": "New logo",
                "headline": "A *fresh* look", "direction": "right", "speed": "fast"},
        settings={"theme": "clean"},
        tags=["design", "logo", "brand", "rebrand", "graphic"],
    ),
    Preset(
        id="fitness-progress", title="Progress check",
        summary="Week one and week twelve, for a fitness or training update.",
        params={"before_label": "Week 1", "after_label": "Week 12",
                "headline": "Twelve weeks *stronger*", "direction": "top", "speed": "normal"},
        settings={"theme": "pop", "energy": "punchy"},
        tags=["fitness", "progress", "training", "gym", "transformation"],
    ),
]
