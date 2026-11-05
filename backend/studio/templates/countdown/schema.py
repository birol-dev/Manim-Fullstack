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
    not_for="Workout rounds, breathing cycles or focus/break sessions: use interval_timer.",
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
    style: Literal["ring", "dial", "bar", "big", "segments", "minimal"] = choice(
        "ring", title="Style", labels={"ring": "Ring", "dial": "Instrument dial", "bar": "Progress bar", "big": "Big numbers",
                                      "segments": "Segments", "minimal": "Minimal clock"},
        option_help={"ring": "A circle that empties as time runs out.",
                     "dial": "A measured clock face with tick marks and a moving pointer.",
                     "bar": "A bar that shrinks as time runs out.",
                     "big": "Large seconds that pop. Best for short countdowns.",
                     "segments": "Twenty blocks switch off as time passes.",
                     "minimal": "An oversized clock with no progress meter."},
        description="Ring: a circle that empties. Instrument dial: a clock face with a moving pointer. "
                    "Progress bar: a bar that shrinks. Big numbers: large seconds "
                    "that pop (best for short countdowns like 10 to 1). Segments disappear one at a time; "
                    "minimal shows only the clock.")
    finish_text: str = text("Time's up!", title="Finish message", max_length=40)
    warn_last: bool = toggle(True, title="Highlight the last 10 seconds")
    confetti: bool = toggle(False, title="Confetti at the end")
    accent: HexColor = color(None, title="Timer color")


PRESETS = [
    Preset(id="classroom-timer", title="Everyday countdown", summary="Set the title and duration for any countdown.",
           params={"seconds": 300, "title": "Time remaining", "style": "dial"},
           settings={"theme": "midnight", "energy": "calm"},
           tags=["classroom", "activity", "cooking", "kitchen", "break", "presentation", "exam", "stream",
                 "short", "launch", "progress bar"]),
]
