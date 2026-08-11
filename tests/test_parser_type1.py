"""Type 1 (.pfb) parsing tests — use real font files from Downloads/Pfb/ as fixtures."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from glyphmatrix.core.parser import parse_font_file

PFB_DIR = Path(os.environ.get("GLYPHMATRIX_PFB_FIXTURES", "/home/papadcha/Downloads/Pfb"))

pytestmark = pytest.mark.skipif(
    not PFB_DIR.exists(),
    reason=f"Type 1 fixture directory not found: {PFB_DIR}",
)


def pfb(name: str) -> Path:
    return PFB_DIR / name


# ---------------------------------------------------------------------------
# Basic routing & format field
# ---------------------------------------------------------------------------

def test_pfb_format_field():
    parsed = parse_font_file(pfb("Lato-Regular.pfb"))
    assert parsed.format == "pfb"


def test_pfb_metadata_complete():
    parsed = parse_font_file(pfb("Lato-Regular.pfb"))
    assert parsed.metadata_complete is True


def test_pfb_content_hash_is_sha256_hex():
    parsed = parse_font_file(pfb("Lato-Regular.pfb"))
    assert len(parsed.content_hash) == 64
    assert all(c in "0123456789abcdef" for c in parsed.content_hash)


def test_pfb_is_not_variable():
    parsed = parse_font_file(pfb("Lato-Regular.pfb"))
    assert parsed.is_variable is False
    assert parsed.axes is None


# ---------------------------------------------------------------------------
# Lato-Regular
# ---------------------------------------------------------------------------

def test_lato_family():
    parsed = parse_font_file(pfb("Lato-Regular.pfb"))
    assert parsed.family_name == "Lato"


def test_lato_style():
    parsed = parse_font_file(pfb("Lato-Regular.pfb"))
    assert parsed.style == "Regular"


def test_lato_weight():
    parsed = parse_font_file(pfb("Lato-Regular.pfb"))
    assert parsed.weight == 400


def test_lato_glyph_count():
    parsed = parse_font_file(pfb("Lato-Regular.pfb"))
    assert parsed.glyph_count > 0


def test_lato_glyphs_have_outline_hash():
    parsed = parse_font_file(pfb("Lato-Regular.pfb"))
    for g in parsed.glyphs:
        assert len(g.outline_hash) == 64


def test_lato_filename():
    parsed = parse_font_file(pfb("Lato-Regular.pfb"))
    assert parsed.filename == "Lato-Regular.pfb"


# ---------------------------------------------------------------------------
# OpenSans-Regular
# ---------------------------------------------------------------------------

def test_opensans_family():
    parsed = parse_font_file(pfb("OpenSans-Regular.pfb"))
    assert parsed.family_name == "Open Sans"


def test_opensans_style_is_regular():
    parsed = parse_font_file(pfb("OpenSans-Regular.pfb"))
    assert parsed.style == "Regular"


def test_opensans_weight():
    parsed = parse_font_file(pfb("OpenSans-Regular.pfb"))
    assert parsed.weight == 400


def test_opensans_glyph_count_large():
    parsed = parse_font_file(pfb("OpenSans-Regular.pfb"))
    assert parsed.glyph_count > 500


# ---------------------------------------------------------------------------
# SourceCodePro-Regular
# ---------------------------------------------------------------------------

def test_sourcecodepro_family():
    parsed = parse_font_file(pfb("SourceCodePro-Regular.pfb"))
    assert parsed.family_name == "Source Code Pro"


def test_sourcecodepro_style():
    parsed = parse_font_file(pfb("SourceCodePro-Regular.pfb"))
    assert parsed.style == "Regular"


def test_sourcecodepro_weight():
    parsed = parse_font_file(pfb("SourceCodePro-Regular.pfb"))
    assert parsed.weight == 400


# ---------------------------------------------------------------------------
# NotoSansShavian-Regular — Shavian glyphs beyond 8-bit range → cp=None
# ---------------------------------------------------------------------------

def test_noto_shavian_family():
    parsed = parse_font_file(pfb("NotoSansShavian-Regular.pfb"))
    assert "Noto" in parsed.family_name


def test_noto_shavian_style():
    parsed = parse_font_file(pfb("NotoSansShavian-Regular.pfb"))
    assert parsed.style == "Regular"


def test_noto_shavian_codepoints_are_none():
    """Shavian block (U+10450+) is outside 8-bit encoding, so those glyph names get no codepoint."""
    parsed = parse_font_file(pfb("NotoSansShavian-Regular.pfb"))
    shavian = [g for g in parsed.glyphs if g.glyph_name.startswith("u104")]
    assert len(shavian) > 0, "expected Shavian glyphs in fixture"
    assert all(g.unicode_codepoint is None for g in shavian)


# ---------------------------------------------------------------------------
# Glyph-level invariants across all fixtures
# ---------------------------------------------------------------------------

ALL_PFB = ["Lato-Regular.pfb", "OpenSans-Regular.pfb", "SourceCodePro-Regular.pfb",
           "NotoSansShavian-Regular.pfb", "slick.pfb"]


@pytest.mark.parametrize("name", ALL_PFB)
def test_all_glyphs_have_glyph_name(name):
    parsed = parse_font_file(pfb(name))
    assert all(g.glyph_name for g in parsed.glyphs)


@pytest.mark.parametrize("name", ALL_PFB)
def test_no_duplicate_glyph_names(name):
    parsed = parse_font_file(pfb(name))
    names = [g.glyph_name for g in parsed.glyphs]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("name", ALL_PFB)
def test_glyph_count_matches_glyphs_list(name):
    parsed = parse_font_file(pfb(name))
    assert parsed.glyph_count >= len(parsed.glyphs)


@pytest.mark.parametrize("name", ALL_PFB)
def test_metadata_complete_for_all(name):
    parsed = parse_font_file(pfb(name))
    assert parsed.metadata_complete is True
