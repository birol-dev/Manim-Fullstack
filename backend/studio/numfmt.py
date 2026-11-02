"""Locale-aware number formatting for templates. No Manim import."""

from __future__ import annotations

import math

# (thousands separator, decimal separator)
_SEPARATORS = {
    "en": (",", "."), "ja": (",", "."), "zh": (",", "."), "ko": (",", "."), "he": (",", "."),
    "tr": (".", ","), "de": (".", ","), "es": (".", ","), "it": (".", ","), "pt": (".", ","),
    "nl": (".", ","), "id": (".", ","), "da": (".", ","), "el": (".", ","),
    "fr": (" ", ","), "ru": (" ", ","), "pl": (" ", ","), "cs": (" ", ","),
    "sv": (" ", ","), "nb": (" ", ","), "fi": (" ", ","), "uk": (" ", ","),
}
_COMPACT = {"en": ("K", "M", "B"), "tr": ("B", "Mn", "Mr"), "de": ("Tsd.", "Mio.", "Mrd.")}


def separators(locale: str) -> tuple:
    return _SEPARATORS.get((locale or "en").split("-")[0], (",", "."))


def format_number(value: float, *, decimals: int = 0, locale: str = "en", prefix: str = "", suffix: str = "",
                  compact: bool = False, sign: bool = False) -> str:
    """``format_number(1234.5, decimals=1, locale="tr", suffix=" ₺")`` -> ``"1.234,5 ₺"``.

    ``compact`` writes 12.300 as 12.3K (per-locale suffixes); ``sign`` adds "+" to positives.
    """
    thousands, point = separators(locale)
    unit = ""
    if compact and abs(value) >= 1000:
        letters = _COMPACT.get((locale or "en").split("-")[0], _COMPACT["en"])
        for power, letter in ((9, letters[2]), (6, letters[1]), (3, letters[0])):
            if abs(value) >= 10 ** power:
                value, unit = value / 10 ** power, letter
                break
        if decimals == 0 and abs(value) < 100:
            decimals = 1
    negative = value < 0
    rounded = round(abs(value), decimals)
    whole = int(math.floor(rounded))
    frac = rounded - whole
    digits = f"{whole:,}".replace(",", thousands)
    if decimals > 0:
        frac_digits = f"{frac:.{decimals}f}"[2:]
        if compact and unit:
            frac_digits = frac_digits.rstrip("0")
        if frac_digits:
            digits += point + frac_digits
    lead = "-" if negative else ("+" if sign and value > 0 else "")
    return f"{lead}{prefix}{digits}{unit}{suffix}"
