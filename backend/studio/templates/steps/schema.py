"""Steps: a short list revealed one item at a time: agenda, instructions, recipe, schedule."""

from typing import Literal, Optional

from pydantic import field_validator

from studio.schema import HexColor, Item, Preset, TemplateMeta, TemplateParams, choice, color, icon, integer, items
from studio.schema import text as text_field

META = TemplateMeta(
    id="steps",
    title="Steps",
    summary="A short list, one item at a time: an agenda, instructions, a recipe or a schedule.",
    category="teach",
    when_to_use="Revealing a short list in order with time to read each item: a meeting or workshop agenda "
                "with times, classroom or how-to instructions, recipe steps, an event schedule. 2 to 7 items, "
                "each with a short line, an optional detail, time and icon; numbered, checklist (each item "
                "ticks as it appears) or a timeline with times on a vertical line.",
    not_for="More than 7 items or long paragraphs (use a text or quote template), one single announcement, "
            "a live countdown, or a quiz with answers.",
    default_aspect="9:16",
    min_length=6,
    max_length=60,
    default_length=14,
    tags=["steps", "agenda", "instructions", "recipe", "schedule", "how to", "checklist", "timeline",
          "meeting", "classroom"],
)

STYLES = {"numbered": "Numbered", "checklist": "Checklist", "timeline": "Timeline"}


class Step(Item):
    # Dense square lists use a flowing label/detail paragraph instead of shrinking.
    text: str = text_field("", title="Step", max_length=40, placeholder="Review last sprint's open items",
                           description="The step itself, up to 40 characters. Short sentences wrap naturally.",
                           help="The step itself, up to 40 characters.")
    detail: str = text_field("", title="Detail", max_length=24, placeholder="Shipped work, blockers",
                             description="Optional detail, up to 24 characters. Dense lists flow it after the step.",
                             help="Optional short detail, up to 24 characters.")
    time: str = text_field("", title="Time", max_length=6, placeholder="09:30",
                           description="An optional short time or length, e.g. '09:30' or '10 min'.",
                           help="Optional time or length, e.g. 09:30.")
    icon: Optional[str] = icon(None, title="Icon", description="Optional icon, e.g. clock, users, flame.")

    @field_validator("text")
    @classmethod
    def _filled(cls, value):
        if not value.strip():
            raise ValueError("Write the step text.")
        return value


class Params(TemplateParams):
    kicker: str = text_field("", title="Top line", max_length=26, placeholder="Monday stand-up",
                             description="A small line above the title. Leave empty for none.",
                             help="A small line above the title.")
    title: str = text_field("Today's plan", title="Title", max_length=40,
                            description="What the list is about. Wrap a word in *asterisks* to color it.")
    steps: list[Step] = items(
        [Step(text="Welcome and quick intros", detail="Two minutes each", time="09:30", icon="users"),
         Step(text="Review last sprint's open items", detail="Shipped work, blockers",
              time="09:40", icon="list-checks"),
         Step(text="Decisions and action items", detail="Who does what by Friday",
              time="10:00", icon="check-check")],
        title="Steps", min_items=2, max_items=7, item_title="Step",
        description="2 to 7 items, each one short line with an optional detail, time and icon.")
    style: Literal["numbered", "checklist", "timeline"] = choice(
        "numbered", title="Style", labels=STYLES,
        option_help={"numbered": "A number badge on every item.",
                     "checklist": "A tick appears on every item as it is shown.",
                     "timeline": "Times sit on a vertical line beside the items."},
        description="Numbered: 1 2 3 badges. Checklist: each item gets a tick as it appears. Timeline: "
                    "times on a vertical line. All three show one item at a time.")
    highlight: int = integer(0, title="Highlight step", ge=0, le=7,
                             help="Marks the current step; 0 for none.",
                             description="Highlights one item as 'now': 1 is the first step, 2 the second, "
                                         "and so on. 0 turns it off.")
    accent: HexColor = color(None, title="Accent color")

    @field_validator("highlight")
    @classmethod
    def _highlight_exists(cls, value, info):
        steps = info.data.get("steps")
        if steps is not None and value > len(steps):
            raise ValueError(f"There are only {len(steps)} steps: choose a number from 0 to {len(steps)}.")
        return value


PRESETS = [
    Preset(
        id="meeting-agenda", title="Meeting agenda",
        summary="A five-item agenda with times on a timeline, the current item marked.",
        params={
            "kicker": "Monday stand-up",
            "title": "Today's *agenda*",
            "steps": [
                {"text": "Welcome and quick intros", "detail": "Two minutes each", "time": "09:30",
                 "icon": "users"},
                {"text": "Review last sprint's open items", "detail": "Shipped work, blockers",
                 "time": "09:40", "icon": "list-checks"},
                {"text": "Budget review for next quarter", "detail": "Q3 numbers and forecast",
                 "time": "10:00", "icon": "chart-column"},
                {"text": "Blockers and who unblocks them", "detail": "Owners and next steps",
                 "time": "10:20", "icon": "circle-alert"},
                {"text": "Decisions and action items", "detail": "Who does what by Friday",
                 "time": "10:40", "icon": "check-check"},
            ],
            "style": "timeline",
            "highlight": 2,
        },
        settings={"theme": "clean", "aspect": "16:9"},
        tags=["meeting", "agenda", "stand-up", "team"],
    ),
    Preset(
        id="classroom-instructions", title="Classroom instructions",
        summary="Five numbered instructions for a lesson, with what to do next in each.",
        params={
            "kicker": "Year 4 · Science",
            "title": "Your *task* for today",
            "steps": [
                {"text": "Collect a worksheet and a pencil", "detail": "From the front desk",
                 "time": "2 min", "icon": "notebook"},
                {"text": "Read the question on the board", "detail": "On your own, in silence",
                 "time": "3 min", "icon": "book-open"},
                {"text": "Work in pairs on task one", "detail": "Share one answer each",
                 "time": "10 min", "icon": "users"},
                {"text": "Draw your results in the table", "detail": "Use a ruler for lines",
                 "time": "8 min", "icon": "pencil"},
                {"text": "Hand in your sheet before lunch", "detail": "The tray by the door",
                 "time": "2 min", "icon": "clipboard-check"},
            ],
            "style": "numbered",
        },
        settings={"theme": "pastel"},
        tags=["classroom", "school", "instructions", "lesson", "teacher"],
    ),
    Preset(
        id="recipe-steps", title="Recipe steps",
        summary="Six cooking steps that tick off one by one: great for a recipe reel.",
        params={
            "kicker": "Weeknight pasta · serves 4",
            "title": "How to make *pasta*",
            "steps": [
                {"text": "Boil a large pot of salted water", "detail": "One litre per 100 g",
                 "icon": "cooking-pot"},
                {"text": "Chop the onion and garlic finely", "detail": "Small, even pieces",
                 "icon": "chef-hat"},
                {"text": "Fry them in olive oil for 5 min", "detail": "Until soft, not brown",
                 "icon": "flame"},
                {"text": "Add the tomatoes and simmer", "detail": "Ten minutes on low heat",
                 "icon": "timer"},
                {"text": "Cook the pasta until al dente", "detail": "Check two minutes early",
                 "icon": "utensils"},
                {"text": "Mix, season and serve hot", "detail": "A little pasta water",
                 "icon": "soup"},
            ],
            "style": "checklist",
        },
        settings={"theme": "chalk"},
        tags=["recipe", "cooking", "food", "dinner", "how to"],
    ),
    Preset(
        id="event-schedule", title="Event schedule",
        summary="A vertical line-up for stories: five moments with times, one marked now.",
        params={
            "kicker": "Friday · Main stage",
            "title": "Tonight's *line-up*",
            "steps": [
                {"text": "Doors open and welcome drinks", "detail": "Grab a name badge",
                 "time": "18:00", "icon": "door-open"},
                {"text": "Opening talk with Maya", "detail": "Ten minutes to say hello",
                 "time": "18:30", "icon": "mic"},
                {"text": "Live demo: the new features", "detail": "Ask anything in chat",
                 "time": "19:00", "icon": "monitor"},
                {"text": "Break and snacks", "detail": "Fifteen minutes",
                 "time": "20:00", "icon": "coffee"},
                {"text": "Panel and audience questions", "detail": "Until 21:15",
                 "time": "20:30", "icon": "message-circle"},
            ],
            "style": "timeline",
            "highlight": 3,
        },
        settings={"theme": "midnight", "aspect": "9:16"},
        tags=["event", "schedule", "line-up", "conference", "party"],
    ),
]
