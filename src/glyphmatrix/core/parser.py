from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont

# CSS-ish label per OS/2.usWidthClass (1-9). None if usWidthClass is absent/unknown.
_WIDTH_CLASSES = {
    1: "ultra-condensed",
    2: "extra-condensed",
    3: "condensed",
    4: "semi-condensed",
    5: "normal",
    6: "semi-expanded",
    7: "expanded",
    8: "extra-expanded",
    9: "ultra-expanded",
}

# High byte of OS/2.sFamilyClass (the "IBM font class"), per the OpenType
# spec — a classification type designers embed in the font, not inferred.
# Missing classes (0, 6, 11, 13) are either "No Classification" or reserved;
# left unmapped on purpose rather than guessed.
_FAMILY_CLASSES = {
    1: "oldstyle-serif",
    2: "transitional-serif",
    3: "modern-serif",
    4: "clarendon-serif",
    5: "slab-serif",
    7: "freeform-serif",
    8: "sans-serif",
    9: "ornamental",
    10: "script",
    12: "symbolic",
    14: "miscellaneous",
}


@dataclass
class ParsedGlyph:
    glyph_name: str
    unicode_codepoint: int | None
    contour_count: int
    advance_width: int | None
    outline_hash: str


@dataclass
class ParsedFont:
    family_name: str
    foundry: str | None
    style: str | None
    weight: int | None
    width: str | None
    is_variable: bool
    axes: dict | None
    path: Path
    filename: str
    format: str
    content_hash: str
    version: str | None
    license: str | None
    glyph_count: int
    glyphs: list[ParsedGlyph]
    family_class: str | None = None
    metadata_complete: bool = True


# SFNT (TrueType/OpenType) is the only family fully parsed today. Other
# scanned formats (Type 1, legacy bitmap) still get a font_files row —
# content_hash works the same regardless of format, so duplicate detection
# and basic visibility work — but no family/style/glyph metadata.
_SFNT_FORMATS = {"ttf", "otf", "ttc", "woff", "woff2"}


def _parse_unsupported(path: Path, content_hash: str) -> ParsedFont:
    return ParsedFont(
        family_name=path.stem,
        foundry=None,
        style=None,
        weight=None,
        width=None,
        is_variable=False,
        axes=None,
        path=path,
        filename=path.name,
        format=path.suffix.lower().lstrip("."),
        content_hash=content_hash,
        version=None,
        license=None,
        glyph_count=0,
        glyphs=[],
        metadata_complete=False,
    )


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_glyphs(font: TTFont) -> list[ParsedGlyph]:
    glyph_set = font.getGlyphSet()
    hmtx = font["hmtx"].metrics if "hmtx" in font else {}
    reverse_cmap: dict[str, set[int]] = font["cmap"].buildReversed() if "cmap" in font else {}

    glyphs = []
    for glyph_name in font.getGlyphOrder():
        pen = RecordingPen()
        glyph_set[glyph_name].draw(pen)
        contour_count = sum(1 for op, _ in pen.value if op == "moveTo")
        outline_hash = hashlib.sha256(repr(pen.value).encode("utf-8")).hexdigest()
        advance_width = hmtx[glyph_name][0] if glyph_name in hmtx else None
        codepoints = reverse_cmap.get(glyph_name)
        unicode_codepoint = min(codepoints) if codepoints else None
        glyphs.append(
            ParsedGlyph(
                glyph_name=glyph_name,
                unicode_codepoint=unicode_codepoint,
                contour_count=contour_count,
                advance_width=advance_width,
                outline_hash=outline_hash,
            )
        )
    return glyphs


def parse_font_file(path: str | Path) -> ParsedFont:
    path = Path(path)
    content_hash = _hash_file(path)
    fmt = path.suffix.lower().lstrip(".")

    if fmt not in _SFNT_FORMATS:
        return _parse_unsupported(path, content_hash)

    with TTFont(path, lazy=True) as font:
        name_table = font["name"]
        family_name = name_table.getBestFamilyName() or path.stem
        foundry = name_table.getDebugName(8)  # nameID 8: Manufacturer
        style = name_table.getBestSubFamilyName()
        version = name_table.getDebugName(5)
        license_desc = name_table.getDebugName(13)

        weight = None
        width = None
        family_class = None
        if "OS/2" in font:
            os2 = font["OS/2"]
            weight = getattr(os2, "usWeightClass", None)
            width = _WIDTH_CLASSES.get(getattr(os2, "usWidthClass", None))
            class_id = getattr(os2, "sFamilyClass", 0) >> 8
            family_class = _FAMILY_CLASSES.get(class_id)

        is_variable = "fvar" in font
        axes = None
        if is_variable:
            axes = {axis.axisTag: [axis.minValue, axis.maxValue] for axis in font["fvar"].axes}

        glyphs = _parse_glyphs(font)

    return ParsedFont(
        family_name=family_name,
        foundry=foundry,
        style=style,
        weight=weight,
        width=width,
        is_variable=is_variable,
        axes=axes,
        path=path,
        filename=path.name,
        format=fmt,
        content_hash=content_hash,
        version=version,
        license=license_desc,
        glyph_count=len(glyphs),
        glyphs=glyphs,
        family_class=family_class,
    )
