import pytest

from glyphmatrix.core.database import connect, init_schema
from glyphmatrix.core.ingest import ingest_directory
from glyphmatrix.core.language_coverage import check_script, resolve_script_query, script_breakdown
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


def test_script_breakdown_latin_only(tmp_path):
    conn = _conn()
    font_file_id = _ingested_font_file_id(conn, tmp_path, extra_glyph=True)  # A, B

    breakdown = script_breakdown(conn, font_file_id)

    assert breakdown == [{"script": "Latn", "name": "Latin", "glyph_count": 2}]


def test_script_breakdown_multiple_scripts(tmp_path):
    conn = _conn()
    font_file_id = _ingested_font_file_id(
        conn, tmp_path, extra_codepoints={0x3B4: "delta", 0x430: "cyra"}  # Greek delta, Cyrillic а
    )

    breakdown = script_breakdown(conn, font_file_id)

    by_script = {row["script"]: row["glyph_count"] for row in breakdown}
    assert by_script == {"Latn": 1, "Grek": 1, "Cyrl": 1}
    assert breakdown[0]["glyph_count"] >= breakdown[-1]["glyph_count"]  # sorted desc


def test_script_breakdown_empty_when_no_glyphs():
    conn = _conn()
    assert script_breakdown(conn, font_file_id=999) == []


def test_check_script_by_code(tmp_path):
    conn = _conn()
    font_file_id = _ingested_font_file_id(conn, tmp_path, extra_codepoints={0x3B4: "delta"})

    result = check_script(conn, font_file_id, "Grek")

    assert result == {"script": "Grek", "name": "Greek", "supported": True, "glyph_count": 1}


def test_check_script_by_name_case_insensitive(tmp_path):
    conn = _conn()
    font_file_id = _ingested_font_file_id(conn, tmp_path, extra_codepoints={0x3B4: "delta"})

    result = check_script(conn, font_file_id, "greek")

    assert result["script"] == "Grek"
    assert result["supported"] is True


def test_check_script_not_supported(tmp_path):
    conn = _conn()
    font_file_id = _ingested_font_file_id(conn, tmp_path)  # Latin only

    result = check_script(conn, font_file_id, "Cyrillic")

    assert result == {"script": "Cyrl", "name": "Cyrillic", "supported": False, "glyph_count": 0}


def test_resolve_script_query_rejects_language_name():
    with pytest.raises(ValueError, match="unrecognized script"):
        resolve_script_query("Vietnamese")


def test_resolve_script_query_rejects_garbage():
    with pytest.raises(ValueError):
        resolve_script_query("not-a-script")
