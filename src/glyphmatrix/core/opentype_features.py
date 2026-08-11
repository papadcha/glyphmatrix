from __future__ import annotations

import re
from pathlib import Path

from fontTools.ttLib import TTFont

# Human-readable names for standard OpenType layout feature tags (the
# registered tags are as objective/spec-defined as OS/2.sFamilyClass — not
# guessed). Not exhaustive; unlisted tags fall back to the raw tag itself
# rather than a made-up label. Source: OpenType feature tag registry.
_FEATURE_NAMES = {
    "aalt": "Access All Alternates",
    "afrc": "Alternative Fractions",
    "c2sc": "Small Capitals From Capitals",
    "calt": "Contextual Alternates",
    "case": "Case-Sensitive Forms",
    "ccmp": "Glyph Composition/Decomposition",
    "cpsp": "Capital Spacing",
    "curs": "Cursive Positioning",
    "dlig": "Discretionary Ligatures",
    "dnom": "Denominators",
    "fina": "Terminal Forms",
    "frac": "Fractions",
    "halt": "Alternate Half Widths",
    "hkna": "Horizontal Kana Alternates",
    "hlig": "Historical Ligatures",
    "init": "Initial Forms",
    "isol": "Isolated Forms",
    "ital": "Italics",
    "kern": "Kerning",
    "liga": "Standard Ligatures",
    "lnum": "Lining Figures",
    "locl": "Localized Forms",
    "mark": "Mark Positioning",
    "medi": "Medial Forms",
    "mkmk": "Mark-to-Mark Positioning",
    "numr": "Numerators",
    "onum": "Oldstyle Figures",
    "ordn": "Ordinals",
    "palt": "Proportional Alternate Widths",
    "pnum": "Proportional Figures",
    "rclt": "Required Contextual Alternates",
    "rlig": "Required Ligatures",
    "ruby": "Ruby Notation Forms",
    "salt": "Stylistic Alternates",
    "smcp": "Small Capitals",
    "subs": "Subscript",
    "sups": "Superscript",
    "swsh": "Swash",
    "titl": "Titling",
    "tnum": "Tabular Figures",
    "unic": "Unicase",
    "valt": "Alternate Vertical Metrics",
    "vert": "Vertical Writing",
    "vhal": "Alternate Vertical Half Metrics",
    "vkna": "Vertical Kana Alternates",
    "vrt2": "Vertical Alternates and Rotation",
    "zero": "Slashed Zero",
}

_STYLISTIC_SET = re.compile(r"^ss(\d{2})$")
_CHARACTER_VARIANT = re.compile(r"^cv(\d{2})$")


def _feature_name(tag: str) -> str:
    if tag in _FEATURE_NAMES:
        return _FEATURE_NAMES[tag]
    if m := _STYLISTIC_SET.match(tag):
        return f"Stylistic Set {int(m.group(1))}"
    if m := _CHARACTER_VARIANT.match(tag):
        return f"Character Variant {int(m.group(1))}"
    return tag


def list_features(path: str | Path) -> list[dict]:
    """Reads GSUB/GPOS FeatureList tags straight from the file (not stored in
    the DB — same on-demand pattern as preview/glyph rendering, since these
    tables aren't part of font_glyphs and most fonts don't have them at all).
    A feature can appear in both GSUB and GPOS (e.g. "locl"); merged into one
    row per tag with both tables listed."""
    tags_to_tables: dict[str, set[str]] = {}
    with TTFont(path, lazy=True) as font:
        for table_tag in ("GSUB", "GPOS"):
            if table_tag not in font:
                continue
            feature_list = font[table_tag].table.FeatureList
            if feature_list is None:
                continue
            for record in feature_list.FeatureRecord:
                tags_to_tables.setdefault(record.FeatureTag, set()).add(table_tag)

    return [
        {"tag": tag, "name": _feature_name(tag), "tables": sorted(tables)}
        for tag, tables in sorted(tags_to_tables.items())
    ]
