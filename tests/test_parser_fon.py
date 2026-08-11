"""Windows FON (NE-format raster) parsing tests — real fixtures from Downloads/fon/."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from glyphmatrix.core.parser import parse_font_file

FON_DIR = Path(os.environ.get("GLYPHMATRIX_FON_FIXTURES", "/home/papadcha/Downloads/fon"))

pytestmark = pytest.mark.skipif(
    not FON_DIR.exists(),
    reason=f"FON fixture directory not found: {FON_DIR}",
)


def fix(name: str) -> Path:
    return FON_DIR / name


# ---------------------------------------------------------------------------
# Format / invariants
# ---------------------------------------------------------------------------

def test_fon_format_field():
    assert parse_font_file(fix("DOSLIKE.FON")).format == "fon"


def test_fon_metadata_complete():
    assert parse_font_file(fix("DOSLIKE.FON")).metadata_complete is True


def test_fon_not_variable():
    p = parse_font_file(fix("DOSLIKE.FON"))
    assert p.is_variable is False
    assert p.axes is None


def test_fon_content_hash_sha256():
    p = parse_font_file(fix("DOSLIKE.FON"))
    assert len(p.content_hash) == 64
    assert all(c in "0123456789abcdef" for c in p.content_hash)


def test_fon_glyphs_list_empty():
    """Per-glyph bitmap data not extracted; metadata_complete=True but glyphs=[]."""
    assert parse_font_file(fix("DOSLIKE.FON")).glyphs == []


# ---------------------------------------------------------------------------
# DOSLIKE.FON — 3 embedded sizes, all same face name + copyright
# ---------------------------------------------------------------------------

def test_doslike_family():
    assert parse_font_file(fix("DOSLIKE.FON")).family_name == "DOSLike"


def test_doslike_style():
    assert parse_font_file(fix("DOSLIKE.FON")).style == "Regular"


def test_doslike_weight():
    assert parse_font_file(fix("DOSLIKE.FON")).weight == 400


def test_doslike_glyph_count():
    # Max across 3 embedded sizes (one size starts at char 1, giving 255 chars)
    assert parse_font_file(fix("DOSLIKE.FON")).glyph_count == 255


def test_doslike_license():
    p = parse_font_file(fix("DOSLIKE.FON"))
    assert p.license is not None
    assert "Sieber" in p.license or "Freeware" in p.license


# ---------------------------------------------------------------------------
# fixed8.fon — 1 embedded size
# ---------------------------------------------------------------------------

def test_fixed8_family():
    assert parse_font_file(fix("fixed8.fon")).family_name == "Fixed Sans Serif"


def test_fixed8_style():
    assert parse_font_file(fix("fixed8.fon")).style == "Regular"


def test_fixed8_weight():
    assert parse_font_file(fix("fixed8.fon")).weight == 400


def test_fixed8_glyph_count():
    assert parse_font_file(fix("fixed8.fon")).glyph_count == 225


def test_fixed8_license():
    assert parse_font_file(fix("fixed8.fon")).license is not None


# ---------------------------------------------------------------------------
# CGMONO.FON — 4 embedded sizes, no copyright text
# ---------------------------------------------------------------------------

def test_cgmono_family():
    assert parse_font_file(fix("CGMONO.FON")).family_name == "CG Mono"


def test_cgmono_style():
    assert parse_font_file(fix("CGMONO.FON")).style == "Regular"


def test_cgmono_weight():
    assert parse_font_file(fix("CGMONO.FON")).weight == 400


def test_cgmono_glyph_count():
    assert parse_font_file(fix("CGMONO.FON")).glyph_count == 225


def test_cgmono_license_none():
    assert parse_font_file(fix("CGMONO.FON")).license is None


# ---------------------------------------------------------------------------
# Cross-file invariants
# ---------------------------------------------------------------------------

ALL_FON = ["DOSLIKE.FON", "fixed8.fon", "CGMONO.FON"]


@pytest.mark.parametrize("name", ALL_FON)
def test_all_fon_metadata_complete(name):
    assert parse_font_file(fix(name)).metadata_complete is True


@pytest.mark.parametrize("name", ALL_FON)
def test_all_fon_glyph_count_positive(name):
    assert parse_font_file(fix(name)).glyph_count > 0


@pytest.mark.parametrize("name", ALL_FON)
def test_all_fon_family_nonempty(name):
    assert parse_font_file(fix(name)).family_name


@pytest.mark.parametrize("name", ALL_FON)
def test_all_fon_style_nonempty(name):
    assert parse_font_file(fix(name)).style


@pytest.mark.parametrize("name", ALL_FON)
def test_all_fon_weight_set(name):
    assert parse_font_file(fix(name)).weight is not None
