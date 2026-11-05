from __future__ import annotations

from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen


def build_test_font(
    out_path: str | Path,
    family: str = "Test Sans",
    style: str = "Regular",
    a_glyph_size: int = 700,
    extra_glyph: bool = False,
    version: str | None = None,
    manufacturer: str | None = None,
    family_class: int | None = None,
    extra_codepoints: dict[int, str] | None = None,
    opentype_features: str | None = None,
    panose: tuple[int, ...] | None = None,
    weight: int | None = None,
    vendor_id: str | None = None,
    copyright: str | None = None,
) -> Path:
    """Build a minimal valid TTF for parser tests: .notdef + A (square outline
    of a_glyph_size), optionally + B, mapped via cmap. extra_codepoints adds
    further glyphs (e.g. {0x3B4: "delta"} for Greek) each with the same
    square outline as B, for tests needing glyphs outside the Latin script."""
    glyph_order = [".notdef", "A"]
    cmap = {65: "A"}
    if extra_glyph:
        glyph_order.append("B")
        cmap[66] = "B"
    for cp, name in (extra_codepoints or {}).items():
        glyph_order.append(name)
        cmap[cp] = name

    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap(cmap)

    pen = TTGlyphPen(None)
    pen.moveTo((0, 0))
    pen.lineTo((0, a_glyph_size))
    pen.lineTo((a_glyph_size, a_glyph_size))
    pen.lineTo((a_glyph_size, 0))
    pen.closePath()
    glyphs = {".notdef": TTGlyphPen(None).glyph(), "A": pen.glyph()}

    if extra_glyph:
        pen_b = TTGlyphPen(None)
        pen_b.moveTo((0, 0))
        pen_b.lineTo((0, 400))
        pen_b.lineTo((400, 400))
        pen_b.lineTo((400, 0))
        pen_b.closePath()
        glyphs["B"] = pen_b.glyph()

    for name in (extra_codepoints or {}).values():
        pen_extra = TTGlyphPen(None)
        pen_extra.moveTo((0, 0))
        pen_extra.lineTo((0, 300))
        pen_extra.lineTo((300, 300))
        pen_extra.lineTo((300, 0))
        pen_extra.closePath()
        glyphs[name] = pen_extra.glyph()

    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({name: (600, 0) for name in glyph_order})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    name_strings = {"familyName": family, "styleName": style}
    if version is not None:
        name_strings["version"] = version
    if manufacturer is not None:
        name_strings["manufacturer"] = manufacturer
    if copyright is not None:
        name_strings["copyright"] = copyright
    fb.setupNameTable(name_strings)
    os2_kwargs = {"sTypoAscender": 800, "sTypoDescender": -200, "usWinAscent": 800, "usWinDescent": 200}
    if family_class is not None:
        os2_kwargs["sFamilyClass"] = family_class
    if weight is not None:
        os2_kwargs["usWeightClass"] = weight
    if vendor_id is not None:
        os2_kwargs["achVendID"] = vendor_id
    fb.setupOS2(**os2_kwargs)
    fb.setupPost()
    if panose is not None:
        fields = (
            "bFamilyType", "bSerifStyle", "bWeight", "bProportion", "bContrast",
            "bStrokeVariation", "bArmStyle", "bLetterForm", "bMidline", "bXHeight",
        )
        for field, value in zip(fields, panose):
            setattr(fb.font["OS/2"].panose, field, value)
    if opentype_features is not None:
        fb.addOpenTypeFeatures(opentype_features)

    out_path = Path(out_path)
    fb.font.save(out_path)
    return out_path
