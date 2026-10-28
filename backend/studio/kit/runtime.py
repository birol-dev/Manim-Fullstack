"""The render job a scene reads, and the frame setup every studio render needs.

A job is JSON: ``{"template", "params", "settings", "mode", "assets_dir", "output"}``.
Subprocess renders (exports) get it from the file named by ``COMPOSER_JOB``; the warm
preview worker sets it in-process with ``set_job`` before it builds each scene.

``mode`` is ``video`` (a normal render), ``poster`` (write one still to ``output``) or
``storyboard`` (write a contact sheet of the frame after each animation to ``output``).
"""

from __future__ import annotations

import json
import os
from typing import Optional

from manim import config

from ..formats import frame_size

JOB_ENV = "COMPOSER_JOB"
MODES = ("video", "poster", "storyboard")

_job: Optional[dict] = None


def set_job(job: Optional[dict]) -> None:
    global _job
    _job = job


def current_job() -> dict:
    if _job is not None:
        return _job
    path = os.environ.get(JOB_ENV)
    if not path:
        raise RuntimeError(f"No render job: set {JOB_ENV} to a job JSON file.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def apply_frame(cfg=config) -> None:
    """Size the frame to the pixel aspect, short side 8 units (see studio.formats)."""
    width, height = frame_size(cfg.pixel_width, cfg.pixel_height)
    cfg.frame_width = width
    cfg.frame_height = height
