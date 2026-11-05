"""Repeated, named timer phases for workouts, focus sessions and breathing."""
from typing import Literal

from pydantic import model_validator

from studio.schema import Item, Preset, TemplateMeta, TemplateParams, choice, duration, integer, items, text, toggle

META = TemplateMeta(
    id="interval_timer", title="Interval timer", category="timers",
    summary="Repeat timed steps, with a phase clock, round count and overall progress.",
    when_to_use="Work/rest intervals, Pomodoro sessions, breathing cycles and timed classroom stations. "
                "Each phase has its own name and duration; the whole sequence repeats for a set number of rounds.",
    not_for="A single countdown: use countdown. This exports a fixed video, not an interactive or live timer.",
    default_length=60, min_length=3, max_length=10800, length_from_params=True, export_fps=15,
    tags=["interval", "timer", "workout", "pomodoro", "breathing", "rounds"],
)


class Phase(Item):
    label: str = text("Work", title="Step name", max_length=28)
    seconds: float = duration(40, title="Step length", ge=1, le=3600,
        help="How long this step runs before the next one begins.")


class Params(TemplateParams):
    title: str = text("Work. Rest. Repeat.", title="Title", max_length=48)
    style: Literal["ring", "console"] = choice("ring", title="Style",
        labels={"ring": "Ring", "console": "Focus console"},
        option_help={"ring": "A circle empties with each step.", "console": "A framed clock with a progress meter."},
        description="Ring: a circle empties with each step. Focus console: a framed clock with a step meter "
                    "and a separate session meter when several steps play.")
    phases: list[Phase] = items([Phase(label="Work", seconds=40), Phase(label="Rest", seconds=20)],
        title="Timed steps", min_items=2, max_items=6, item_title="Step",
        description="Two to six steps, played in order. Each step has a name and duration.")
    rounds: int = integer(6, title="Rounds", ge=1, le=30)
    end_with_first: bool = toggle(True, title="Finish after the first step of the last round",
        help="Skip the final rest. Turn off to complete the last round.")
    finish_text: str = text("Session complete", title="Finish message", max_length=40)

    @model_validator(mode="after")
    def _duration_limit(self):
        if sum(seconds for _, seconds, _, _ in schedule(self)) > 10800:
            raise ValueError("Keep the whole session within three hours. Shorten a step or use fewer rounds.")
        return self


def schedule(params):
    """(name, seconds, phase index, round number), shared by validation and rendering."""
    return [(phase.label, float(phase.seconds), index, round_index + 1)
            for round_index in range(params.rounds)
            for index, phase in enumerate(params.phases)
            if not (params.end_with_first and round_index == params.rounds - 1 and index > 0)]


PRESETS = [
    Preset(id="pomodoro-session", title="Focus timer", summary="One 25-minute focus block. Add rounds for five-minute breaks.",
        params={"title": "Focus time", "style": "console", "phases": [{"label": "Focus", "seconds": 1500},
            {"label": "Break", "seconds": 300}], "rounds": 1, "end_with_first": True, "finish_text": "Take a break"},
        settings={"theme": "afterglow", "energy": "calm"},
        tags=["pomodoro", "25-minute", "deep focus", "study", "sprints", "classroom", "stations"]),
]
