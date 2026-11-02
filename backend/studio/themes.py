"""Theme presets as plain data (colors, fonts, shapes). No Manim import.

Templates never hard-code colors: they read these tokens through ``kit.Theme``. The
brand kit (``RenderSettings.brand``) overrides the accent colors and the font.
"""

from __future__ import annotations

THEMES = {
    "clean": {
        "name": "Clean light",
        "dark": False,
        "bg": "#F6F5F2",
        "bg2": "#ECEAE4",
        "surface": "#FFFFFF",
        "text": "#16181D",
        "muted": "#6B6F78",
        "line": "#DAD7CF",
        "accent": ["#2563EB", "#F97316", "#10B981", "#E11D48", "#8B5CF6"],
        "on_accent": "#FFFFFF",
        "font": "Inter",
        "display_weight": "BOLD",
        "radius": 0.22,
        "case": "normal",
    },
    "midnight": {
        "name": "Midnight",
        "dark": True,
        "bg": "#0B1020",
        "bg2": "#18213D",
        "surface": "#161D33",
        "text": "#F3F5FA",
        "muted": "#9AA3B8",
        "line": "#2A3352",
        "accent": ["#7C9CFF", "#5EEAD4", "#FBBF24", "#F472B6", "#A78BFA"],
        "on_accent": "#0B1020",
        "font": "Inter",
        "display_weight": "BOLD",
        "radius": 0.22,
        "case": "normal",
    },
    "pop": {
        "name": "Bold pop",
        "dark": False,
        "bg": "#FFD84D",
        "bg2": "#FFC21A",
        "surface": "#FFFFFF",
        "text": "#111111",
        "muted": "#3D3A33",
        "line": "#111111",
        "accent": ["#FF3D7F", "#1E40FF", "#00B37E", "#111111", "#FF7A00"],
        "on_accent": "#FFFFFF",
        "font": "Inter",
        "display_weight": "HEAVY",
        "radius": 0.12,
        "case": "upper",
    },
    "newsroom": {
        "name": "Newsroom",
        "dark": False,
        "bg": "#FFFFFF",
        "bg2": "#F1F3F5",
        "surface": "#F1F3F5",
        "text": "#0F172A",
        "muted": "#475569",
        "line": "#CBD5E1",
        "accent": ["#B91C1C", "#1D4ED8", "#0F766E", "#B45309", "#0F172A"],
        "on_accent": "#FFFFFF",
        "font": "Inter",
        "display_weight": "BOLD",
        "radius": 0.04,
        "case": "normal",
    },
    "pastel": {
        "name": "Pastel",
        "dark": False,
        "bg": "#FDF3EC",
        "bg2": "#F6E3F0",
        "surface": "#FFFFFF",
        "text": "#3B3355",
        "muted": "#7A7192",
        "line": "#E9DCE4",
        "accent": ["#E86A92", "#4FB3A2", "#8C7AE6", "#F2A65A", "#5DA9E9"],
        "on_accent": "#FFFFFF",
        "font": "Inter",
        "display_weight": "BOLD",
        "radius": 0.36,
        "case": "normal",
    },
    "chalk": {
        "name": "Chalkboard",
        "dark": True,
        "bg": "#1D2A25",
        "bg2": "#263730",
        "surface": "#25352E",
        "text": "#F1F5EC",
        "muted": "#A9B8AE",
        "line": "#3A4D44",
        "accent": ["#FFE08A", "#9EE6CF", "#FF9E9E", "#B6C8FF", "#FFFFFF"],
        "on_accent": "#1D2A25",
        "font": "Inter",
        "display_weight": "BOLD",
        "radius": 0.18,
        "case": "normal",
    },
}

DEFAULT_THEME = "clean"

# The families the app ships in studio/assets/fonts. A brand may only choose one of these;
# anything else keeps the theme's font, so a name typed elsewhere never changes a render.
BUNDLED_FONTS = ("Inter", "JetBrains Mono")
_BUNDLED = {name.casefold(): name for name in BUNDLED_FONTS}
_BUNDLED.update({"inter studio": "Inter", "jetbrains mono studio": "JetBrains Mono"})


def bundled_font(name) -> str | None:
    """The bundled family for *name* (aliases included), or None when it is not bundled."""
    if not isinstance(name, str):
        return None
    return _BUNDLED.get(name.strip().casefold())


def theme_tokens(theme_id: str, brand=None) -> dict:
    """The theme's tokens with brand overrides applied (unknown ids fall back to the default)."""
    tokens = dict(THEMES.get(theme_id) or THEMES[DEFAULT_THEME])
    tokens["accent"] = list(tokens["accent"])
    if brand is not None:
        if getattr(brand, "accent", None):
            tokens["accent"][0] = brand.accent
        if getattr(brand, "accent2", None):
            tokens["accent"][1] = brand.accent2
        font = bundled_font(getattr(brand, "font", None))
        if font:
            tokens["font"] = font
    return tokens


def public_themes() -> list:
    """For the API: id, name, and the colors the UI uses for theme swatches."""
    return [
        {"id": key, "name": t["name"], "dark": t["dark"], "bg": t["bg"], "text": t["text"], "accent": t["accent"]}
        for key, t in THEMES.items()
    ]
