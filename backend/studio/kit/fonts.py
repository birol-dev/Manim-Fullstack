"""Bundled fonts (studio/assets/fonts) and the fallback when a family is missing."""

from __future__ import annotations

import os
import sys
from functools import lru_cache

FONTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "fonts")

# Pango's Win32 backend reloads every private font for every Text. Its Fontconfig
# backend shares the font map and reads our bundle directly. Set this before any
# studio text layouts are created (including the worker's warm-up).
if sys.platform == "win32":
    os.environ.setdefault("PANGOCAIRO_BACKEND", "fc")
    os.environ.setdefault("FONTCONFIG_FILE", os.path.join(FONTS_DIR, "fonts.conf"))

# Used when the theme's family is neither bundled nor installed.
PLATFORM_FALLBACK = {"win32": "Segoe UI", "darwin": "Helvetica Neue"}.get(sys.platform, "DejaVu Sans")


def _register(path: str) -> bool:
    """Make one font file available to Pango in this process.

    Fontconfig registration avoids Win32's per-layout private font reload.
    """
    import manimpango

    if sys.platform == "win32" and os.environ.get("PANGOCAIRO_BACKEND") == "fc":
        return bool(manimpango.fc_register_font(path))
    return bool(manimpango.register_font(path))


@lru_cache(maxsize=1)
def register_bundled() -> tuple:
    """Register every .ttf/.otf in the fonts folder with Pango (once per process)."""
    registered = []
    if os.path.isdir(FONTS_DIR):
        for name in sorted(os.listdir(FONTS_DIR)):
            if name.lower().endswith((".ttf", ".otf")):
                if _register(os.path.join(FONTS_DIR, name)):
                    registered.append(name)
    return tuple(registered)


@lru_cache(maxsize=1)
def available_families() -> frozenset:
    import manimpango

    register_bundled()
    return frozenset(manimpango.list_fonts())


@lru_cache(maxsize=32)
def resolve(family: str) -> str:
    """*family* if Pango can find it, else the platform's sans-serif."""
    families = available_families()
    # Unique names keep an installed variable Inter from shadowing our static weights.
    bundled = {"inter": "Inter Studio", "jetbrains mono": "JetBrains Mono Studio"}.get(family.lower())
    if bundled in families:
        return bundled
    if family in families:
        return family
    lowered = {f.lower(): f for f in families}
    return lowered.get(family.lower(), PLATFORM_FALLBACK)
