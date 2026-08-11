"""BDF and PCF bitmap font parsing tests — use real fixtures from Downloads/pcf/."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from glyphmatrix.core.parser import parse_font_file

PCF_DIR = Path(os.environ.get("GLYPHMATRIX_PCF_FIXTURES", "/home/papadcha/Downloads/pcf"))

pytestmark = pytest.mark.skipif(
    not PCF_DIR.exists(),
    reason=f"Bitmap fixture directory not found: {PCF_DIR}",
)


def fix(name: str) -> Path:
    return PCF_DIR / name


# ---------------------------------------------------------------------------
# BDF — format field and shared invariants
# ---------------------------------------------------------------------------

def test_bdf_format_field():
    assert parse_font_file(fix("5th-element.bdf")).format == "bdf"


def test_bdf_metadata_complete():
    assert parse_font_file(fix("5th-element.bdf")).metadata_complete is True


def test_bdf_not_variable():
    p = parse_font_file(fix("5th-element.bdf"))
    assert p.is_variable is False
    assert p.axes is None


def test_bdf_content_hash_sha256():
    p = parse_font_file(fix("5th-element.bdf"))
    assert len(p.content_hash) == 64
    assert all(c in "0123456789abcdef" for c in p.content_hash)


# ---------------------------------------------------------------------------
# 5th-element.bdf — iso8859-1, codepoints available
# ---------------------------------------------------------------------------

def test_5thelement_family():
    assert parse_font_file(fix("5th-element.bdf")).family_name == "5thElement"


def test_5thelement_foundry():
    assert parse_font_file(fix("5th-element.bdf")).foundry == "aaron"


def test_5thelement_style():
    assert parse_font_file(fix("5th-element.bdf")).style == "Regular"


def test_5thelement_weight():
    assert parse_font_file(fix("5th-element.bdf")).weight == 500  # "Medium" → 500


def test_5thelement_glyph_count():
    assert parse_font_file(fix("5th-element.bdf")).glyph_count == 95


def test_5thelement_glyphs_have_codepoints():
    """iso8859-1 maps 1:1 to Unicode, so all non-negative encodings get a codepoint."""
    p = parse_font_file(fix("5th-element.bdf"))
    assert all(g.unicode_codepoint is not None for g in p.glyphs)


def test_5thelement_glyphs_have_outline_hash():
    p = parse_font_file(fix("5th-element.bdf"))
    for g in p.glyphs:
        assert len(g.outline_hash) == 64


def test_5thelement_contour_count_is_zero():
    p = parse_font_file(fix("5th-element.bdf"))
    assert all(g.contour_count == 0 for g in p.glyphs)


# ---------------------------------------------------------------------------
# haxor-medium-10.bdf — iso8859-2, codepoints NOT mapped (non-latin-1)
# ---------------------------------------------------------------------------

def test_haxor_family():
    assert parse_font_file(fix("haxor-medium-10.bdf")).family_name == "Haxor"


def test_haxor_style():
    assert parse_font_file(fix("haxor-medium-10.bdf")).style == "Regular"


def test_haxor_glyph_count():
    assert parse_font_file(fix("haxor-medium-10.bdf")).glyph_count == 199


def test_haxor_codepoints_none():
    """iso8859-2 upper half doesn't map to Unicode directly — all codepoints should be None."""
    p = parse_font_file(fix("haxor-medium-10.bdf"))
    assert all(g.unicode_codepoint is None for g in p.glyphs)


# ---------------------------------------------------------------------------
# lokaltog-fixed-10b-iso10646.bdf — Unicode charset, bold weight
# ---------------------------------------------------------------------------

def test_lokaltog_family():
    assert parse_font_file(fix("lokaltog-fixed-10b-iso10646.bdf")).family_name == "fixed"


def test_lokaltog_foundry():
    assert parse_font_file(fix("lokaltog-fixed-10b-iso10646.bdf")).foundry == "lokaltog"


def test_lokaltog_style():
    assert parse_font_file(fix("lokaltog-fixed-10b-iso10646.bdf")).style == "Bold"


def test_lokaltog_weight():
    assert parse_font_file(fix("lokaltog-fixed-10b-iso10646.bdf")).weight == 700


def test_lokaltog_glyph_count():
    assert parse_font_file(fix("lokaltog-fixed-10b-iso10646.bdf")).glyph_count == 220


def test_lokaltog_has_unicode_codepoints():
    """iso10646 charset → encoding values are Unicode codepoints directly."""
    p = parse_font_file(fix("lokaltog-fixed-10b-iso10646.bdf"))
    with_cp = [g for g in p.glyphs if g.unicode_codepoint is not None]
    assert len(with_cp) > 100


def test_lokaltog_license():
    assert parse_font_file(fix("lokaltog-fixed-10b-iso10646.bdf")).license == "Created by Lokaltog"


# ---------------------------------------------------------------------------
# pico-8raize-19.bdf — WinRoman charset, version field present
# ---------------------------------------------------------------------------

def test_pico_family():
    assert parse_font_file(fix("pico-8raize-19.bdf")).family_name == "PICO8 Raize"


def test_pico_style():
    assert parse_font_file(fix("pico-8raize-19.bdf")).style == "Regular"


def test_pico_glyph_count():
    assert parse_font_file(fix("pico-8raize-19.bdf")).glyph_count == 256


def test_pico_version():
    assert parse_font_file(fix("pico-8raize-19.bdf")).version == "001.000"


def test_pico_codepoints_none():
    """WinRoman charset is not Unicode — codepoints should be None."""
    p = parse_font_file(fix("pico-8raize-19.bdf"))
    assert all(g.unicode_codepoint is None for g in p.glyphs)


# ---------------------------------------------------------------------------
# PCF — format field and shared invariants
# ---------------------------------------------------------------------------

def test_pcf_format_field():
    assert parse_font_file(fix("5th-element.pcf")).format == "pcf"


def test_pcf_metadata_complete():
    assert parse_font_file(fix("5th-element.pcf")).metadata_complete is True


def test_pcf_not_variable():
    p = parse_font_file(fix("5th-element.pcf"))
    assert p.is_variable is False
    assert p.axes is None


def test_pcf_content_hash_sha256():
    p = parse_font_file(fix("5th-element.pcf"))
    assert len(p.content_hash) == 64


# ---------------------------------------------------------------------------
# PCF metadata — same families/weights/styles as matching BDF
# ---------------------------------------------------------------------------

ALL_PAIRS = [
    ("5th-element", "5thElement", "aaron", "Regular", 500, 95),
    ("haxor-medium-10", "Haxor", "ucw.cz", "Regular", 500, 199),
    ("lokaltog-fixed-10b-iso10646", "fixed", "lokaltog", "Bold", 700, 220),
    ("pico-8raize-19", "PICO8 Raize", "FontForge", "Regular", None, 256),
]


@pytest.mark.parametrize("base,family,foundry,style,weight,count", ALL_PAIRS)
def test_pcf_family(base, family, foundry, style, weight, count):
    assert parse_font_file(fix(f"{base}.pcf")).family_name == family


@pytest.mark.parametrize("base,family,foundry,style,weight,count", ALL_PAIRS)
def test_pcf_foundry(base, family, foundry, style, weight, count):
    assert parse_font_file(fix(f"{base}.pcf")).foundry == foundry


@pytest.mark.parametrize("base,family,foundry,style,weight,count", ALL_PAIRS)
def test_pcf_style(base, family, foundry, style, weight, count):
    assert parse_font_file(fix(f"{base}.pcf")).style == style


@pytest.mark.parametrize("base,family,foundry,style,weight,count", ALL_PAIRS)
def test_pcf_glyph_count(base, family, foundry, style, weight, count):
    assert parse_font_file(fix(f"{base}.pcf")).glyph_count == count


def test_pcf_glyphs_list_empty():
    """PCF parser does not produce per-glyph entries (BITMAPS table not parsed)."""
    assert parse_font_file(fix("5th-element.pcf")).glyphs == []


def test_pcf_lokaltog_license():
    assert parse_font_file(fix("lokaltog-fixed-10b-iso10646.pcf")).license == "Created by Lokaltog"


def test_pcf_pico_version():
    assert parse_font_file(fix("pico-8raize-19.pcf")).version == "001.000"


# ---------------------------------------------------------------------------
# BDF/PCF consistency: same family/style/weight from both files of a pair
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("base", ["5th-element", "haxor-medium-10",
                                   "lokaltog-fixed-10b-iso10646", "pico-8raize-19"])
def test_bdf_pcf_family_match(base):
    bdf = parse_font_file(fix(f"{base}.bdf"))
    pcf = parse_font_file(fix(f"{base}.pcf"))
    assert bdf.family_name == pcf.family_name


@pytest.mark.parametrize("base", ["5th-element", "haxor-medium-10",
                                   "lokaltog-fixed-10b-iso10646", "pico-8raize-19"])
def test_bdf_pcf_style_match(base):
    bdf = parse_font_file(fix(f"{base}.bdf"))
    pcf = parse_font_file(fix(f"{base}.pcf"))
    assert bdf.style == pcf.style


@pytest.mark.parametrize("base", ["5th-element", "haxor-medium-10",
                                   "lokaltog-fixed-10b-iso10646", "pico-8raize-19"])
def test_bdf_pcf_glyph_count_match(base):
    bdf = parse_font_file(fix(f"{base}.bdf"))
    pcf = parse_font_file(fix(f"{base}.pcf"))
    assert bdf.glyph_count == pcf.glyph_count
