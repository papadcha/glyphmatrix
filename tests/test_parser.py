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
    assert parsed.metadata_complete is True


def test_parse_font_file_extracts_foundry(tmp_path):
    font_path = build_test_font(tmp_path / "test.ttf", manufacturer="Acme Type Foundry")

    parsed = parse_font_file(font_path)

    assert parsed.foundry == "Acme Type Foundry"


def test_parse_font_file_foundry_defaults_to_none(tmp_path):
    font_path = build_test_font(tmp_path / "test.ttf")

    parsed = parse_font_file(font_path)

    assert parsed.foundry is None


def test_parse_font_file_extracts_family_class(tmp_path):
    sans_path = build_test_font(tmp_path / "sans.ttf", family_class=8 * 256 + 1)
    oldstyle_path = build_test_font(tmp_path / "oldstyle.ttf", family_class=1 * 256)

    assert parse_font_file(sans_path).family_class == "sans-serif"
    assert parse_font_file(oldstyle_path).family_class == "oldstyle-serif"


def test_parse_font_file_family_class_none_when_unset(tmp_path):
    font_path = build_test_font(tmp_path / "test.ttf")  # sFamilyClass defaults to 0

    parsed = parse_font_file(font_path)

    assert parsed.family_class is None


def test_parse_font_file_extracts_panose_class(tmp_path):
    sans_path = build_test_font(tmp_path / "sans.ttf", panose=(2, 11, 5, 3, 2, 2, 2, 2, 2, 4))
    flared_path = build_test_font(tmp_path / "flared.ttf", panose=(2, 14, 5, 3, 2, 2, 2, 2, 2, 4))

    assert parse_font_file(sans_path).panose_class == "normal-sans"
    assert parse_font_file(flared_path).panose_class == "flared"


def test_parse_font_file_panose_class_none_when_unset(tmp_path):
    font_path = build_test_font(tmp_path / "test.ttf")  # panose defaults to all-zero

    parsed = parse_font_file(font_path)

    assert parsed.panose_class is None


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


def test_parse_font_file_falls_back_for_unsupported_format(tmp_path):
    font_path = tmp_path / "OldFont.fon"
    font_path.write_bytes(b"\x00\x00\xff\xff" * 16)

    parsed = parse_font_file(font_path)

    assert parsed.family_name == "OldFont"
    assert parsed.style is None
    assert parsed.format == "fon"
    assert parsed.glyph_count == 0
    assert parsed.glyphs == []
    assert parsed.metadata_complete is False
    assert len(parsed.content_hash) == 64  # still hashed, so duplicates still work


def test_outline_hash_matches_when_glyph_shape_identical(tmp_path):
    version_a = build_test_font(tmp_path / "v1.ttf", family="Arial", style="Regular")
    version_b = build_test_font(tmp_path / "v4.ttf", family="Arial", style="Regular")

    parsed_a = parse_font_file(version_a)
    parsed_b = parse_font_file(version_b)

    hash_a = next(g.outline_hash for g in parsed_a.glyphs if g.glyph_name == "A")
    hash_b = next(g.outline_hash for g in parsed_b.glyphs if g.glyph_name == "A")

    assert hash_a == hash_b
