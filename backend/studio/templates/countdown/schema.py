"""Countdown timer: a ring (or bar) that empties, mm:ss in the middle, a finish card."""

from typing import Literal

from studio.schema import HexColor, Preset, TemplateMeta, TemplateParams, choice, color, duration, text, toggle

META = TemplateMeta(
    id="countdown",
    title="Countdown timer",
    summary="A timer for class, meetings or workouts, with a clear finish.",
    category="timers",
    when_to_use="A visible timer people watch count down: classroom activities, breaks, meetings, "
                "presentations. The video lasts as long as the timer.",
    not_for="A 10-to-1 launch countdown: use style 'big' here with 10 seconds. Workout rounds with rest: "
            "a dedicated interval template.",
    default_aspect="16:9",
    min_length=5,
    max_length=3600,
    default_length=300,
    length_from_params=True,
    export_fps=15,
    tags=["timer", "classroom", "countdown", "break", "meeting"],
)


class Params(TemplateParams):
    seconds: float = duration(300, title="Timer length", ge=3, le=3600,
                              help="How long the timer runs.",
                              description="How long the timer runs, in seconds (5 minutes = 300).")
    title: str = text("Quiet reading time", title="Title", max_length=60,
                      description="What the time is for. Leave empty for no title.")
    subtitle: str = text("", title="Note", max_length=80, description="A second line, e.g. 'Back at 10:30'.")
    style: Literal["ring", "bar", "big"] = choice(
        "ring", title="Style", labels={"ring": "Ring", "bar": "Progress bar", "big": "Big numbers"},
        option_help={"ring": "A circle that empties as time runs out.",
                     "bar": "A bar that shrinks as time runs out.",
                     "big": "Large seconds that pop. Best for short countdowns."},
        description="Ring: a circle that empties. Progress bar: a bar that shrinks. Big numbers: large seconds "
                    "that pop (best for short countdowns like 10 to 1).")
    finish_text: str = text("Time's up!", title="Finish message", max_length=40)
    warn_last: bool = toggle(True, title="Highlight the last 10 seconds")
    confetti: bool = toggle(False, title="Confetti at the end")
    accent: HexColor = color(None, title="Timer color")


PRESETS = [
    Preset(id="classroom-timer", title="Classroom timer", summary="5 minutes with a calm ring.",
           params={"seconds": 300, "title": "Quiet reading time", "style": "ring"},
           settings={"theme": "clean", "energy": "calm"}),
    Preset(id="break-timer", title="Break timer", summary="10 minute break, back at a set time.",
           params={"seconds": 600, "title": "Coffee break", "subtitle": "Back at 10:30", "style": "bar"},
           settings={"theme": "midnight"}),
    Preset(id="launch-countdown", title="10…1 countdown", summary="Big numbers for a launch or New Year.",
           params={"seconds": 10, "title": "", "style": "big", "finish_text": "Happy New Year!", "confetti": True},
           settings={"theme": "pop", "energy": "punchy"}),
]
