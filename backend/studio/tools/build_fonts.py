#!/usr/bin/env python
"""Build the static TrueType fonts bundled with the template studio.

Input : the OFL-licensed variable WOFF2 subsets shipped by ``@fontsource-variable/inter`` and
        ``@fontsource-variable/jetbrains-mono`` (frontend/node_modules, run ``npm install`` first).
Output: backend/studio/assets/fonts/InterStudio-<Weight>.ttf (400..900), JetBrainsMonoStudio-{Regular,Bold}.ttf
        and the two license texts. ``studio.kit.fonts`` registers every .ttf/.otf there with Pango.

For every weight each unicode-range subset is instanced from the variable ``wght`` axis to a static
font, the subsets are merged back into one font, and the name table / OS/2 are rewritten so the
family is exactly "Inter" with the right weight class.

    python backend/studio/tools/build_fonts.py                      # rebuild the bundled fonts
    python backend/studio/tools/build_fonts.py --family InterTest --out /tmp/fonts   # test build

Needs: fonttools, brotli (``pip install fonttools brotli``).

Notes (measured on Windows 11, manimpango 0.6.0 / Pango win32):

* A family that is ALSO installed system-wide shadows the bundled files: with the family named
  "Inter" and a system-installed variable Inter, Pango keeps using the system font (heavy weights
  then get Regular's advance widths and look cramped). Always check bundled fonts under a unique
  ``--family`` name; to make the bundle win on such machines, build it under another family
  (e.g. ``--family "Inter Studio"``) and map the theme font to it.
* Every file registered with ``manimpango.register_font`` adds ~1.5 s to each Pango font-map
  initialisation on Windows (first Text, list_fonts, and every new weight), whatever its size.

"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile

try:
    from fontTools import ttLib
    from fontTools.merge import Merger, Options
    from fontTools.ttLib.tables._n_a_m_e import NameRecord
    from fontTools.varLib import instancer
    __import__("brotli")  # needed by fontTools to read WOFF2
except ImportError as exc:  # pragma: no cover
    sys.exit(f"missing dependency ({exc}); run: pip install fonttools brotli")

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(STUDIO))
FONTSOURCE = os.path.join(REPO, "frontend", "node_modules", "@fontsource-variable")
DEFAULT_OUT = os.path.join(STUDIO, "assets", "fonts")

INTER_SUBSETS = ["latin", "latin-ext", "vietnamese", "greek", "greek-ext", "cyrillic", "cyrillic-ext"]
MONO_SUBSETS = ["latin", "latin-ext"]

# weight value -> style name
INTER_WEIGHTS = {400: "Regular", 500: "Medium", 600: "SemiBold", 700: "Bold", 800: "ExtraBold", 900: "Black"}
MONO_WEIGHTS = {400: "Regular", 700: "Bold"}

# Tables that make no sense in a static font (or that only add weight).
DROP_TABLES = ["STAT", "DSIG", "MVAR", "HVAR", "VVAR", "avar", "fvar", "gvar", "cvar", "hdmx", "LTSH", "VDMX"]


def source_files(package: str, prefix: str, subsets: list) -> list:
    folder = os.path.join(FONTSOURCE, package, "files")
    paths = [os.path.join(folder, f"{prefix}-{s}-wght-normal.woff2") for s in subsets]
    missing = [p for p in paths if not os.path.isfile(p)]
    if missing:
        sys.exit("missing font source files (run `npm install` in frontend/):\n  " + "\n  ".join(missing))
    return paths


def instance(path: str, weight: int, dest: str) -> None:
    """Static instance of a variable subset at *weight*, written to *dest* as plain TTF."""
    font = ttLib.TTFont(path)
    axes = {a.axisTag: a for a in font["fvar"].axes}
    location = {"wght": min(max(weight, axes["wght"].minValue), axes["wght"].maxValue)}
    for tag, axis in axes.items():
        if tag != "wght":  # opsz etc: pin at the default
            location[tag] = axis.defaultValue
    static = instancer.instantiateVariableFont(font, location, inplace=False)
    static.flavor = None
    static.save(dest)


def set_names(font: ttLib.TTFont, family: str, style: str, weight: int, source_names, flat_names: bool = False) -> None:
    """Rewrite the name table so Pango/GDI/fontconfig/DirectWrite all see family *family*.

    Regular and Bold use the classic 2-style layout (ID1 = family, ID2 = Regular|Bold).
    Other weights follow the usual static-font layout: ID1 = "<family> <style>", ID2 = Regular,
    plus the typographic family/subfamily (ID16/17) so DirectWrite and fontconfig group them
    under *family*.
    """
    ps_family = family.replace(" ", "")
    full = family if style == "Regular" else f"{family} {style}"
    if style == "Regular":
        n1, n2 = family, "Regular"
    elif style == "Bold":
        n1, n2 = family, "Bold"
    elif flat_names:
        n1, n2 = family, style
    else:
        n1, n2 = f"{family} {style}", "Regular"
    copyright_ = next((n.toUnicode() for n in source_names if n.nameID == 0), "")
    license_url = next((n.toUnicode() for n in source_names if n.nameID == 14), "https://openfontlicense.org")
    version = next((n.toUnicode() for n in source_names if n.nameID == 5), "Version 1.000")
    entries = {
        0: copyright_,
        1: n1,
        2: n2,
        3: f"{version.replace('Version ', '').split(';')[0]};{ps_family}-{style}",
        4: full,
        5: version.split(";")[0],
        6: f"{ps_family}-{style}",
        13: "This Font Software is licensed under the SIL Open Font License, Version 1.1.",
        14: license_url,
    }
    if (n1, n2) != (full, style):  # typographic names differ from the legacy ones
        entries[16] = family
        entries[17] = style
    name = font["name"]
    name.names = []
    for name_id, value in entries.items():
        if not value:
            continue
        for plat, enc, lang in ((3, 1, 0x409), (1, 0, 0)):
            rec = NameRecord()
            rec.nameID, rec.platformID, rec.platEncID, rec.langID = name_id, plat, enc, lang
            rec.string = value
            name.names.append(rec)
    name.names.sort(key=lambda r: (r.platformID, r.platEncID, r.langID, r.nameID))

    os2 = font["OS/2"]
    os2.usWeightClass = weight
    os2.usWidthClass = 5
    sel = os2.fsSelection & ~(1 << 0) & ~(1 << 5) & ~(1 << 6)  # not italic / bold / regular
    sel |= (1 << 5) if style == "Bold" else (1 << 6)
    sel |= 1 << 7  # USE_TYPO_METRICS
    os2.fsSelection = sel
    font["head"].macStyle = 1 if style == "Bold" else 0
    font["post"].formatType = 3.0  # no glyph names: smaller, and nothing reads them
    font["post"].extraNames = []
    font["post"].mapping = {}


def build_family(label: str, paths: list, weights: dict, family: str, out_dir: str, file_prefix: str,
                 flat_names: bool = False) -> list:
    written = []
    with tempfile.TemporaryDirectory() as tmp:
        for weight, style in weights.items():
            parts = []
            for i, src in enumerate(paths):
                dest = os.path.join(tmp, f"{file_prefix}-{style}-{i}.ttf")
                instance(src, weight, dest)
                parts.append(dest)
            merger = Merger(options=Options(drop_tables=DROP_TABLES, verbose=False, timing=False))
            merged = merger.merge(parts)
            # keep the legacy GDI `kern`-free output tidy
            merged.flavor = None
            source_names = ttLib.TTFont(paths[0])["name"].names
            set_names(merged, family, style, weight, source_names, flat_names)
            out = os.path.join(out_dir, f"{file_prefix}-{style}.ttf")
            merged.save(out)
            written.append(out)
            print(f"  {label} {weight:>3} {style:<10} -> {os.path.basename(out)} "
                  f"({os.path.getsize(out) / 1024:.0f} KB, {len(merged.getGlyphOrder())} glyphs)")
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=DEFAULT_OUT, help="output folder (default: backend/studio/assets/fonts)")
    ap.add_argument("--family", default="Inter Studio", help="family name to write (default: Inter Studio, so a system-installed Inter never shadows the bundled files)")
    ap.add_argument("--mono-family", default="JetBrains Mono Studio")
    ap.add_argument("--only", choices=["inter", "mono"], help="build just one family")
    ap.add_argument("--flat-names", action="store_true",
                    help="name every weight family=<family>, subfamily=<weight> (no typographic IDs)")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    total = 0
    if args.only in (None, "inter"):
        print(f'Inter -> family "{args.family}"')
        files = build_family("Inter", source_files("inter", "inter", INTER_SUBSETS), INTER_WEIGHTS,
                             args.family, args.out, args.family.replace(" ", ""), args.flat_names)
        total += sum(os.path.getsize(f) for f in files)
        shutil.copyfile(os.path.join(FONTSOURCE, "inter", "LICENSE"), os.path.join(args.out, "OFL-Inter.txt"))
    if args.only in (None, "mono"):
        print(f'JetBrains Mono -> family "{args.mono_family}"')
        files = build_family("Mono", source_files("jetbrains-mono", "jetbrains-mono", MONO_SUBSETS),
                             MONO_WEIGHTS, args.mono_family, args.out, args.mono_family.replace(" ", ""), args.flat_names)
        total += sum(os.path.getsize(f) for f in files)
        shutil.copyfile(os.path.join(FONTSOURCE, "jetbrains-mono", "LICENSE"),
                        os.path.join(args.out, "OFL-JetBrainsMono.txt"))
    print(f"done: {total / 1024 / 1024:.2f} MB of fonts in {args.out}")


if __name__ == "__main__":
    main()
