from glyphmatrix.core.database import connect, init_schema
from glyphmatrix.core.glyph_inspector import find_glyphs, glyph_summary
from glyphmatrix.core.ingest import ingest_directory
from glyphmatrix.core.query import find_face_id, find_first_font_file_for_face

from .fontbuilder import build_test_font


def _conn():
    conn = connect(":memory:")
    init_schema(conn)
    return conn


def _ingested_font_file_id(conn, tmp_path, **kwargs):
    build_test_font(tmp_path / "test.ttf", **kwargs)
    ingest_directory(conn, tmp_path)
    face_id = find_face_id(conn, kwargs.get("family", "Test Sans"), kwargs.get("style", "Regular"))
    return find_first_font_file_for_face(conn, face_id)["id"]


def test_glyph_summary_reports_count_and_ranges(tmp_path):
    conn = _conn()
    font_file_id = _ingested_font_file_id(conn, tmp_path, extra_glyph=True)  # .notdef, A, B

    summary = glyph_summary(conn, font_file_id)

    assert summary["glyph_count"] == 3
    assert summary["min_codepoint"] == 65  # 'A'
    assert summary["max_codepoint"] == 66  # 'B'
    assert summary["mapped_count"] == 2  # .notdef has no codepoint
    assert summary["min_contours"] == 0  # .notdef is empty
    assert summary["max_contours"] == 1


def test_glyph_summary_empty_when_no_glyphs():
    conn = _conn()
    summary = glyph_summary(conn, font_file_id=999)
    assert summary["glyph_count"] == 0
    assert summary["min_codepoint"] is None


def test_find_glyphs_by_codepoint(tmp_path):
    conn = _conn()
    font_file_id = _ingested_font_file_id(conn, tmp_path, extra_glyph=True)

    matches = find_glyphs(conn, font_file_id, codepoint=65)

    assert len(matches) == 1
    assert matches[0]["glyph_name"] == "A"


def test_find_glyphs_by_exact_name(tmp_path):
    conn = _conn()
    font_file_id = _ingested_font_file_id(conn, tmp_path, extra_glyph=True)

    matches = find_glyphs(conn, font_file_id, glyph_name=".notdef")

    assert len(matches) == 1
    assert matches[0]["unicode_codepoint"] is None
    assert matches[0]["contour_count"] == 0


def test_find_glyphs_by_name_search(tmp_path):
    conn = _conn()
    font_file_id = _ingested_font_file_id(conn, tmp_path, extra_glyph=True)

    matches = find_glyphs(conn, font_file_id, name_search="not")

    assert [m["glyph_name"] for m in matches] == [".notdef"]


def test_find_glyphs_no_match_returns_empty(tmp_path):
    conn = _conn()
    font_file_id = _ingested_font_file_id(conn, tmp_path)

    assert find_glyphs(conn, font_file_id, codepoint=9999) == []


def test_find_glyphs_scoped_to_font_file(tmp_path):
    conn = _conn()
    folder_a = tmp_path / "a"
    folder_a.mkdir()
    folder_b = tmp_path / "b"
    folder_b.mkdir()
    build_test_font(folder_a / "Arial-Regular.ttf", family="Arial", style="Regular")
    build_test_font(folder_b / "Verdana-Regular.ttf", family="Verdana", style="Regular")
    ingest_directory(conn, tmp_path)
    arial_face = find_face_id(conn, "Arial", "Regular")
    arial_file_id = find_first_font_file_for_face(conn, arial_face)["id"]

    matches = find_glyphs(conn, arial_file_id, codepoint=65)

    assert len(matches) == 1  # not doubled up with Verdana's own "A" glyph
