"""Repeated, named timer phases for workouts, focus sessions and breathing."""
from pydantic import model_validator

from studio.schema import Item, Preset, TemplateMeta, TemplateParams, duration, integer, items, text, toggle

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
    seconds: float = duration(40, title="Step length", ge=1, le=3600)


class Params(TemplateParams):
    title: str = text("Work. Rest. Repeat.", title="Title", max_length=48)
    phases: list[Phase] = items([Phase(label="Work", seconds=40), Phase(label="Rest", seconds=20)],
        title="Timed steps", min_items=2, max_items=6, item_title="Step",
        description="Two to six steps, played in order. Each step has a name and duration.")
    rounds: int = integer(6, title="Rounds", ge=1, le=30)
    end_with_first: bool = toggle(True, title="Finish after the first step of the last round",
        help="Skip the final rest. Turn off to complete every step of the last round.")
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
    Preset(id="pomodoro-session", title="Pomodoro session", summary="Four 25-minute focus blocks with five-minute breaks.",
        params={"title": "Make room for deep work", "phases": [{"label": "Focus", "seconds": 1500},
            {"label": "Take a break", "seconds": 300}], "rounds": 4, "finish_text": "Good work. You're done."},
        settings={"theme": "midnight", "energy": "calm"}, tags=["pomodoro", "focus", "study"]),
    Preset(id="tabata-rounds", title="Tabata workout", summary="Eight rounds of 20 seconds on and 10 seconds off.",
        params={"title": "20 on / 10 off", "phases": [{"label": "Move", "seconds": 20},
            {"label": "Recover", "seconds": 10}], "rounds": 8, "finish_text": "Workout complete"},
        settings={"theme": "pop", "energy": "punchy"}, tags=["tabata", "workout", "fitness"]),
    Preset(id="hiit-circuit", title="HIIT circuit", summary="Six 40-second efforts with 20-second recovery breaks.",
        params={"title": "One round at a time", "rounds": 6},
        settings={"theme": "clean"}, tags=["hiit", "workout", "circuit"]),
    Preset(id="box-breathing", title="Box breathing", summary="Inhale, hold, exhale, hold: four equal steps, six cycles.",
        params={"title": "Find your rhythm", "phases": [{"label": "Breathe in", "seconds": 4},
            {"label": "Hold", "seconds": 4}, {"label": "Breathe out", "seconds": 4},
            {"label": "Hold", "seconds": 4}], "rounds": 6, "end_with_first": False,
            "finish_text": "Back to your own pace"},
        settings={"theme": "pastel", "energy": "calm"}, tags=["breathing", "calm", "cycle"]),
    Preset(id="study-sprints", title="Study sprints", summary="Three ten-minute study blocks with two-minute breaks.",
        params={"title": "A little, then a little more", "phases": [{"label": "Study", "seconds": 600},
            {"label": "Stretch & reset", "seconds": 120}], "rounds": 3, "finish_text": "Session finished"},
        settings={"theme": "chalk"}, tags=["study", "focus", "revision"]),
    Preset(id="classroom-stations", title="Classroom stations", summary="Four stations, with time to work and time to move.",
        params={"title": "Work together. Then rotate.", "phases": [{"label": "Station activity", "seconds": 180},
            {"label": "Move to the next station", "seconds": 30}], "rounds": 4,
            "finish_text": "Back to your seats"},
        settings={"theme": "newsroom"}, tags=["classroom", "stations", "teaching"]),
]
