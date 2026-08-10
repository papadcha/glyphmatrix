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
) -> Path:
    """Build a minimal valid TTF for parser tests: .notdef + A (square outline
    of a_glyph_size), optionally + B, mapped via cmap."""
    glyph_order = [".notdef", "A"]
    cmap = {65: "A"}
    if extra_glyph:
        glyph_order.append("B")
        cmap[66] = "B"

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

    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({name: (600, 0) for name in glyph_order})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    name_strings = {"familyName": family, "styleName": style}
    if version is not None:
        name_strings["version"] = version
    fb.setupNameTable(name_strings)
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    fb.setupPost()

    out_path = Path(out_path)
    fb.font.save(out_path)
    return out_path
