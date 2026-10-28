"""Errors the studio service raises, each with the HTTP status the REST API answers with.

Bad input is ``registry.TemplateError`` (422, with field-level ``errors``); everything
else is a ``StudioError``. Both carry plain messages meant for people and agents.
"""

from __future__ import annotations


class StudioError(Exception):
    status = 500


class NotFoundError(StudioError):
    status = 404


class BusyError(StudioError):
    """Too many exports waiting."""

    status = 429


class RenderError(StudioError):
    """The template failed while rendering (a bug in it, or input its layout can't take)."""

    status = 500

    def __init__(self, message: str, traceback: str = ""):
        super().__init__(message)
        self.traceback = traceback


class RenderTimeout(RenderError):
    status = 504


class RendererUnavailable(StudioError):
    """The preview worker can't start (Manim missing or broken)."""

    status = 503
