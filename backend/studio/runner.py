"""The one file Manim renders for every template export (static: no generated code).

    COMPOSER_JOB=/path/job.json manim -r 1080,1920 --fps 30 backend/studio/runner.py StudioRender

Reads the job, sizes the frame for the pixel aspect, imports the template's scene and
declares ``StudioRender`` here, because Manim only picks up scene classes defined in the
file it was given.
"""

import importlib
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from studio.kit import runtime  # noqa: E402
from studio.registry import get_template  # noqa: E402

_job = runtime.current_job()
_spec = get_template(_job["template"])  # refuses ids that aren't installed templates
runtime.apply_frame()
_Template = importlib.import_module(f"studio.templates.{_spec.id}.scene").Template


class StudioRender(_Template):
    pass
