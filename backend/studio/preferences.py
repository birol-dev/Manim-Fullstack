"""Studio preferences that survive a restart, kept with the workspace.

The desktop app runs its WebView in private mode, so its browser storage is empty
at every launch. These few choices live in ``workspace/studio/preferences.json``
instead: a small JSON object with known keys, written atomically like the other
studio stores. A damaged or oversized file reads as empty (the caller falls back
to its own defaults); unknown keys are ignored on read and refused on write.

    store = PreferenceStore(workspace)
    store.read()                                  # {"appearance": "dark", ...}
    store.update({"sidebar_collapsed": True})     # merged object
"""

from __future__ import annotations

import json
import os
import re

from .registry import TemplateError

APPEARANCES = ("light", "dark", "system")
MAX_BYTES = 64 * 1024
MAX_RECENT_COLORS = 12
MAX_SEEN_EXPORTS = 200
MAX_FAVOURITE_DESIGNS = 200
MAX_EXPORT_ID = 64
_HEX = re.compile(r"^#?[0-9a-fA-F]{6}$")
_EXPORT_ID = re.compile(r"^[A-Za-z0-9_-]{1,%d}$" % MAX_EXPORT_ID)
_DESIGN_KEY = re.compile(r"^[a-z0-9_]+/[a-z0-9][a-z0-9_-]{0,63}$")


def _error(field: str, message: str) -> TemplateError:
    return TemplateError(message, [{"field": field, "message": message}])


def _appearance(value):
    if value not in APPEARANCES:
        raise _error("appearance", 'Use "light", "dark" or "system".')
    return value


def _boolean(field: str):
    def check(value):
        if not isinstance(value, bool):
            raise _error(field, "Use true or false.")
        return value

    return check


def _categories(value):
    return None if value is None else _boolean("template_categories_open")(value)


def _colors(value):
    if not isinstance(value, list):
        raise _error("recent_colors", "Use a list of colors.")
    if len(value) > MAX_RECENT_COLORS:
        raise _error("recent_colors", f"Use at most {MAX_RECENT_COLORS} colors.")
    colors = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not _HEX.match(item.strip()):
            raise _error(f"recent_colors.{index}", "Use a hex color like #2563EB.")
        colors.append("#" + item.strip().lstrip("#").upper())
    return colors


def _brand_name(value):
    if not isinstance(value, str):
        raise _error("brand_name", "Use text.")
    if len(value) > 80:
        raise _error("brand_name", "Use at most 80 characters.")
    return value


def _optional_text(field: str, limit: int):
    def check(value):
        if value is None:
            return None
        if not isinstance(value, str) or len(value) > limit:
            raise _error(field, f"Use text of at most {limit} characters, or null.")
        return value

    return check


def _optional_hex(field: str):
    def check(value):
        if value is None:
            return None
        if not isinstance(value, str) or not _HEX.match(value.strip()):
            raise _error(field, "Use a hex color like #2563EB, or null.")
        return "#" + value.strip().lstrip("#").upper()

    return check


BRAND_KIT_KEYS = ("accent", "accent2", "font", "logo")
MAX_BRAND_FONT = 60
MAX_BRAND_LOGO = 200


def _brand_text(field: str, limit: int):
    def check(value):
        if value is None:
            return None
        text = value.strip() if isinstance(value, str) else ""
        if not text or len(text) > limit:
            raise _error(field, f"Use text of at most {limit} characters, or null.")
        return text

    return check


def _brand_logo(value):
    if value is None:
        return None
    name = value.strip() if isinstance(value, str) else ""
    if (not name or len(name) > MAX_BRAND_LOGO or "/" in name or "\\" in name
            or name in (".", "..") or name.startswith(".")):
        raise _error("brand_kit.logo", "Use an image name from your pictures, or null.")
    return name


def _brand_kit(value):
    """The saved brand kit: any of accent, accent2, font and logo; null clears one."""
    if not isinstance(value, dict):
        raise _error("brand_kit", "Use an object with accent, accent2, font and logo.")
    unknown = [key for key in value if key not in BRAND_KIT_KEYS]
    if unknown:
        raise _error(f"brand_kit.{unknown[0]}", "Unknown brand setting.")
    checks = {
        "accent": _optional_hex("brand_kit.accent"),
        "accent2": _optional_hex("brand_kit.accent2"),
        "font": _brand_text("brand_kit.font", MAX_BRAND_FONT),
        "logo": _brand_logo,
    }
    return {key: check(value[key]) for key, check in checks.items() if key in value}


def _seen(value):
    if not isinstance(value, list):
        raise _error("seen_exports", "Use a list of export ids.")
    if len(value) > MAX_SEEN_EXPORTS:
        raise _error("seen_exports", f"Use at most {MAX_SEEN_EXPORTS} export ids.")
    seen = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not _EXPORT_ID.match(item):
            raise _error(f"seen_exports.{index}", "Use an export id from this workspace.")
        seen.append(item)
    return seen


def _favourites(value):
    """Design cards marked with a heart: template id / preset id, newest first, no duplicates."""
    if not isinstance(value, list):
        raise _error("favourite_designs", "Use a list of designs.")
    if len(value) > MAX_FAVOURITE_DESIGNS:
        raise _error("favourite_designs", f"Use at most {MAX_FAVOURITE_DESIGNS} designs.")
    keys = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not _DESIGN_KEY.match(item):
            raise _error(f"favourite_designs.{index}", "Use a design from this gallery.")
        if item not in keys:
            keys.append(item)
    return keys


# Known keys and how to check them. New preferences are one entry here (and one
# in the frontend's Preferences type); old files keep working.
SCHEMA = {
    "appearance": _appearance,
    "sidebar_collapsed": _boolean("sidebar_collapsed"),
    "template_categories_open": _categories,
    "recent_colors": _colors,
    "seen_exports": _seen,
    "favourite_designs": _favourites,
    "onboarding_done": _boolean("onboarding_done"),
    "brand_name": _brand_name,
    "brand_color": _optional_hex("brand_color"),
    "brand_kit": _brand_kit,
    "default_format": _optional_text("default_format", 32),
    "default_theme": _optional_text("default_theme", 64),
    "update_check": _boolean("update_check"),
}
PREFERENCE_KEYS = tuple(SCHEMA)


class PreferenceStore:
    """Reads and merges the preferences file; bad content never blocks the studio."""

    def __init__(self, workspace: str):
        self.path = os.path.join(workspace, "studio", "preferences.json")

    def read(self) -> dict:
        """The stored preferences (only known, valid keys); empty when missing or damaged."""
        try:
            with open(self.path, encoding="utf-8") as source:
                raw = source.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                return {}
            data = json.loads(raw)
        except (OSError, ValueError):
            return {}
        return self._known(data) if isinstance(data, dict) else {}

    @staticmethod
    def _known(data: dict) -> dict:
        values = {}
        for key, validate in SCHEMA.items():
            if key not in data:
                continue
            try:
                values[key] = validate(data[key])
            except TemplateError:
                continue
        return values

    def update(self, changes) -> dict:
        """Merge *changes* into the file and return the merged object (422-style errors if invalid)."""
        if not isinstance(changes, dict):
            raise _error("body", "Send a JSON object.")
        errors, values = [], {}
        for key, value in changes.items():
            validate = SCHEMA.get(key)
            if validate is None:
                errors.append({"field": key, "message": "Unknown preference."})
                continue
            try:
                values[key] = validate(value)
            except TemplateError as exc:
                errors.extend(exc.errors)
        if errors:
            raise TemplateError("Invalid preferences.", errors)
        if not values:
            return self.read()
        import file_ops

        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with file_ops.locked(self.path):
            merged = {**self.read(), **values}
            data = json.dumps(merged, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
            if len(data) > MAX_BYTES:
                raise _error("body", f"Preferences are too large ({len(data)} bytes; "
                                     f"the limit is {MAX_BYTES} bytes).")
            file_ops.atomic_write(self.path, data)
        return merged
