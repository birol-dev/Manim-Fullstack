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
    style: Literal["ring", "bar", "big", "segments", "minimal"] = choice(
        "ring", title="Style", labels={"ring": "Ring", "bar": "Progress bar", "big": "Big numbers",
                                      "segments": "Segments", "minimal": "Minimal clock"},
        option_help={"ring": "A circle that empties as time runs out.",
                     "bar": "A bar that shrinks as time runs out.",
                     "big": "Large seconds that pop. Best for short countdowns.",
                     "segments": "Twenty blocks switch off as time passes.",
                     "minimal": "An oversized clock with no progress meter."},
        description="Ring: a circle that empties. Progress bar: a bar that shrinks. Big numbers: large seconds "
                    "that pop (best for short countdowns like 10 to 1). Segments disappear one at a time; "
                    "minimal shows only the clock.")
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
    Preset(id="launch-countdown", title="10…1 countdown", summary="Ten bold seconds before a launch or activity.",
           params={"seconds": 10, "title": "Ready?", "style": "big", "finish_text": "Let's go!", "confetti": False},
           settings={"theme": "pop", "energy": "punchy"}),
    Preset(id="deep-focus", title="25-minute focus", summary="A distraction-free clock for a full focus session.",
           params={"seconds": 1500, "title": "One thing at a time", "subtitle": "Focus session",
                   "style": "minimal", "finish_text": "Take a break", "warn_last": False},
           settings={"theme": "midnight", "energy": "calm"}, tags=["focus", "study", "pomodoro"]),
    Preset(id="presentation-timer", title="Presentation timer", summary="A three-minute speaking slot with a shrinking bar.",
           params={"seconds": 180, "title": "Your three minutes", "subtitle": "One idea. Make it count.",
                   "style": "bar", "finish_text": "Wrap it up"},
           settings={"theme": "newsroom"}, tags=["presentation", "meeting", "speaking"]),
    Preset(id="cooking-timer", title="Kitchen timer", summary="A twelve-minute ring for cooking and recipe videos.",
           params={"seconds": 720, "title": "In the oven", "subtitle": "Check when the timer ends",
                   "style": "ring", "finish_text": "Ready to check"},
           settings={"theme": "pastel"}, tags=["cooking", "recipe", "kitchen"]),
    Preset(id="exam-timer", title="Exam countdown", summary="Forty-five minutes, with blocks showing the time left.",
           params={"seconds": 2700, "title": "Independent work", "subtitle": "Read carefully. You have time.",
                   "style": "segments", "finish_text": "Pens down"},
           settings={"theme": "chalk", "energy": "calm"}, tags=["exam", "classroom", "study"]),
    Preset(id="stream-starting", title="Stream starting soon", summary="A two-minute countdown before going live.",
           params={"seconds": 120, "title": "Starting soon", "subtitle": "Get comfortable. We're almost ready.",
                   "style": "ring", "finish_text": "We're live"},
           settings={"theme": "midnight", "aspect": "16:9"}, tags=["stream", "live", "starting soon"]),
    Preset(id="five-second-start", title="Ready, set, go", summary="Five bold seconds before an activity or video starts.",
           params={"seconds": 5, "title": "Get ready", "style": "big", "finish_text": "Go!"},
           settings={"theme": "clean", "energy": "punchy"}, tags=["short", "start", "countdown"]),
]
