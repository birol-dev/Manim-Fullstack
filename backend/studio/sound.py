"""Shared sound contract and original track catalog. No Manim or audio-library imports."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

TRACKS = (
    {"id": "calm", "title": "Quiet morning", "description": "Warm, slow notes."},
    {"id": "upbeat", "title": "Small steps", "description": "A light, steady pulse."},
    {"id": "playful", "title": "Little discoveries", "description": "Soft, curious plucks."},
)
EFFECTS = ("tick", "tick_final", "finish", "reveal", "correct", "pop", "whoosh", "sparkle")
MAX_AUDIO_BYTES = 50 * 1024 * 1024
MAX_AUDIO_SECONDS = 600
SAMPLE_RATE = 24000
AUDIO_VERSION = 1


class MusicSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    asset: str | None = Field(None, pattern=r"^audio-[a-f0-9]{32}\.wav$")
    track: Literal["calm", "upbeat", "playful"] | None = None
    volume: float = Field(0.25, ge=0, le=1)
    fade_out: bool = True
    loop: bool = True

    @model_validator(mode="after")
    def one_source(self):
        if self.asset and self.track:
            raise ValueError("Choose your uploaded music or a bundled track, not both.")
        return self


class SoundSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    effects: bool = True
    effects_volume: float = Field(0.75, ge=0, le=1)
    music: MusicSettings = Field(default_factory=MusicSettings)


def music_tracks():
    return [{**t, "url": f"/api/studio/sounds/music/{t['id']}.wav"} for t in TRACKS]
