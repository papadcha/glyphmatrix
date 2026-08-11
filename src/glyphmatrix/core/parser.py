from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from fontTools.pens.recordingPen import RecordingPen
from fontTools.t1Lib import T1Font
from fontTools.ttLib import TTFont

from glyphmatrix.core.panose import classify_panose

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
    panose_class: str | None = None
    metadata_complete: bool = True


# SFNT (TrueType/OpenType) is the only family fully parsed today. Other
# scanned formats (Type 1, legacy bitmap) still get a font_files row —
# content_hash works the same regardless of format, so duplicate detection
# and basic visibility work — but no family/style/glyph metadata.
_SFNT_FORMATS = {"ttf", "otf", "ttc", "woff", "woff2"}
_T1_FORMATS = {"pfb", "pfa"}

_T1_WEIGHT_NUMERIC: dict[str, int] = {
    "thin": 100, "hairline": 100,
    "extralight": 200, "extra light": 200, "ultralight": 200, "ultra light": 200,
    "light": 300,
    "book": 400, "regular": 400, "roman": 400, "normal": 400,
    "medium": 500,
    "semibold": 600, "semi bold": 600, "demibold": 600, "demi bold": 600, "demi": 600,
    "bold": 700,
    "extrabold": 800, "extra bold": 800,
    "black": 900, "heavy": 900, "ultra": 900,
}


_T1_REGULAR_WEIGHTS = {"book", "regular", "roman", "normal"}


def _t1_style(family: str, fullname: str | None, weight_str: str, italic_angle: float) -> str:
    style = ""
    if fullname:
        style = fullname.replace(family, "").strip(" -")
    if not style:
        ws_lower = weight_str.lower()
        style = "Regular" if ws_lower in _T1_REGULAR_WEIGHTS else (weight_str or "Regular")
    if italic_angle and "italic" not in style.lower():
        style = (style + " Italic").strip()
    return style or "Regular"


def _t1_advance_width(glyph) -> int | None:
    try:
        glyph.decompile()
        prog = glyph.program
        for i, tok in enumerate(prog):
            if tok == "hsbw" and i >= 2:
                return int(prog[i - 1])
            if tok == "sbw" and i >= 4:
                return int(prog[i - 2])
    except Exception:
        pass
    return None


def _parse_type1_glyphs(t1font: T1Font) -> tuple[list[ParsedGlyph], int]:
    enc = t1font.font.get("Encoding", [])
    reverse_enc: dict[str, int] = {}
    if isinstance(enc, list):
        for idx, name in enumerate(enc):
            if name and name != ".notdef" and name not in reverse_enc:
                reverse_enc[name] = idx

    glyphs: list[ParsedGlyph] = []
    glyph_set = t1font.getGlyphSet()
    for glyph_name, glyph_obj in glyph_set.items():
        try:
            pen = RecordingPen()
            glyph_obj.draw(pen)
            contour_count = sum(1 for op, _ in pen.value if op == "moveTo")
            outline_hash = hashlib.sha256(repr(pen.value).encode()).hexdigest()
            advance = _t1_advance_width(glyph_obj)
            codepoint = reverse_enc.get(glyph_name)
        except Exception:
            continue
        glyphs.append(
            ParsedGlyph(
                glyph_name=glyph_name,
                unicode_codepoint=codepoint,
                contour_count=contour_count,
                advance_width=advance,
                outline_hash=outline_hash,
            )
        )
    return glyphs, len(glyph_set)


def _parse_type1(path: Path, content_hash: str) -> ParsedFont:
    t1 = T1Font(str(path))
    t1.parse()
    fi = t1.font.get("FontInfo", {})

    family_name = fi.get("FamilyName") or path.stem
    full_name = fi.get("FullName")
    weight_str = fi.get("Weight") or ""
    italic_angle = fi.get("ItalicAngle") or 0
    style = _t1_style(family_name, full_name, weight_str, italic_angle)
    weight_num = _T1_WEIGHT_NUMERIC.get(weight_str.lower())
    version = fi.get("version") or fi.get("Version")
    if version:
        version = version.split(";")[0].strip()
    license_text = fi.get("Notice")

    glyphs, total = _parse_type1_glyphs(t1)

    return ParsedFont(
        family_name=family_name,
        foundry=None,
        style=style,
        weight=weight_num,
        width=None,
        is_variable=False,
        axes=None,
        path=path,
        filename=path.name,
        format=path.suffix.lower().lstrip("."),
        content_hash=content_hash,
        version=version,
        license=license_text,
        glyph_count=total,
        glyphs=glyphs,
        metadata_complete=True,
    )


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

    if fmt in _T1_FORMATS:
        return _parse_type1(path, content_hash)
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
        panose_class = None
        if "OS/2" in font:
            os2 = font["OS/2"]
            weight = getattr(os2, "usWeightClass", None)
            width = _WIDTH_CLASSES.get(getattr(os2, "usWidthClass", None))
            class_id = getattr(os2, "sFamilyClass", 0) >> 8
            family_class = _FAMILY_CLASSES.get(class_id)
            panose = getattr(os2, "panose", None)
            if panose is not None:
                panose_bytes = (
                    panose.bFamilyType, panose.bSerifStyle, panose.bWeight,
                    panose.bProportion, panose.bContrast, panose.bStrokeVariation,
                    panose.bArmStyle, panose.bLetterForm, panose.bMidline, panose.bXHeight,
                )
                panose_class = classify_panose(panose_bytes)

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
        panose_class=panose_class,
    )
