from glyphmatrix.core.parser import parse_font_file

from .fontbuilder import build_test_font


def test_parse_font_file_extracts_family_and_style(tmp_path):
    font_path = build_test_font(tmp_path / "test.ttf", family="Test Sans", style="Bold")

    parsed = parse_font_file(font_path)

    assert parsed.family_name == "Test Sans"
    assert parsed.style == "Bold"
    assert parsed.format == "ttf"
    assert parsed.filename == "test.ttf"
    assert parsed.is_variable is False
    assert parsed.glyph_count == 2
    assert len(parsed.content_hash) == 64


def test_parse_font_file_extracts_foundry(tmp_path):
    font_path = build_test_font(tmp_path / "test.ttf", manufacturer="Acme Type Foundry")

    parsed = parse_font_file(font_path)

    assert parsed.foundry == "Acme Type Foundry"


def test_parse_font_file_foundry_defaults_to_none(tmp_path):
    font_path = build_test_font(tmp_path / "test.ttf")

    parsed = parse_font_file(font_path)

    assert parsed.foundry is None


def test_parse_font_file_extracts_glyph_metadata(tmp_path):
    font_path = build_test_font(tmp_path / "test.ttf", extra_glyph=True)

    parsed = parse_font_file(font_path)

    by_name = {g.glyph_name: g for g in parsed.glyphs}
    assert set(by_name) == {".notdef", "A", "B"}

    a = by_name["A"]
    assert a.unicode_codepoint == 65
    assert a.contour_count == 1
    assert a.advance_width == 600

    notdef = by_name[".notdef"]
    assert notdef.unicode_codepoint is None
    assert notdef.contour_count == 0


def test_outline_hash_differs_when_glyph_shape_changes(tmp_path):
    small = build_test_font(tmp_path / "small.ttf", a_glyph_size=500)
    large = build_test_font(tmp_path / "large.ttf", a_glyph_size=700)

    parsed_small = parse_font_file(small)
    parsed_large = parse_font_file(large)

    hash_small = next(g.outline_hash for g in parsed_small.glyphs if g.glyph_name == "A")
    hash_large = next(g.outline_hash for g in parsed_large.glyphs if g.glyph_name == "A")

    assert hash_small != hash_large


def test_outline_hash_matches_when_glyph_shape_identical(tmp_path):
    version_a = build_test_font(tmp_path / "v1.ttf", family="Arial", style="Regular")
    version_b = build_test_font(tmp_path / "v4.ttf", family="Arial", style="Regular")

    parsed_a = parse_font_file(version_a)
    parsed_b = parse_font_file(version_b)

    hash_a = next(g.outline_hash for g in parsed_a.glyphs if g.glyph_name == "A")
    hash_b = next(g.outline_hash for g in parsed_b.glyphs if g.glyph_name == "A")

    assert hash_a == hash_b
