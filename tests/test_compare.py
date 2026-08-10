from glyphmatrix.core.compare import compare_font_files
from glyphmatrix.core.database import connect, init_schema
from glyphmatrix.core.ingest import ingest_directory
from glyphmatrix.core.query import find_font_file

from .fontbuilder import build_test_font


def _conn():
    conn = connect(":memory:")
    init_schema(conn)
    return conn


def test_compare_font_files_direct_glyph_rows():
    conn = _conn()
    conn.execute("INSERT INTO families (id, name) VALUES (1, 'Arial')")
    conn.execute("INSERT INTO font_faces (id, family_id, style) VALUES (1, 1, 'Regular')")
    conn.execute(
        "INSERT INTO font_files (id, font_face_id, path, filename, content_hash, source) "
        "VALUES (1, 1, 'a.ttf', 'a.ttf', 'h1', 'user'), "
        "(2, 1, 'b.ttf', 'b.ttf', 'h2', 'user')"
    )
    # A: glyph shared+unchanged, glyph removed in B, delta changed shape
    conn.execute(
        "INSERT INTO font_glyphs (font_file_id, glyph_name, outline_hash) VALUES "
        "(1, 'A', 'hashA'), (1, 'delta', 'hash_delta_v1'), (1, 'onlyA', 'x')"
    )
    conn.execute(
        "INSERT INTO font_glyphs (font_file_id, glyph_name, outline_hash) VALUES "
        "(2, 'A', 'hashA'), (2, 'delta', 'hash_delta_v4'), (2, 'onlyB', 'y')"
    )

    diff = compare_font_files(conn, 1, 2)

    assert diff.only_in_a == ["onlyA"]
    assert diff.only_in_b == ["onlyB"]
    assert diff.changed == ["delta"]
    assert diff.unchanged_count == 1  # glyph "A"


def test_compare_identical_files_reports_no_diff():
    conn = _conn()
    conn.execute("INSERT INTO families (id, name) VALUES (1, 'Arial')")
    conn.execute("INSERT INTO font_faces (id, family_id, style) VALUES (1, 1, 'Regular')")
    conn.execute(
        "INSERT INTO font_files (id, font_face_id, path, filename, content_hash, source) "
        "VALUES (1, 1, 'a.ttf', 'a.ttf', 'h1', 'user'), (2, 1, 'b.ttf', 'b.ttf', 'h1', 'user')"
    )
    conn.execute(
        "INSERT INTO font_glyphs (font_file_id, glyph_name, outline_hash) VALUES "
        "(1, 'A', 'hashA'), (2, 'A', 'hashA')"
    )

    diff = compare_font_files(conn, 1, 2)

    assert diff.only_in_a == []
    assert diff.only_in_b == []
    assert diff.changed == []
    assert diff.unchanged_count == 1


def test_compare_via_ingested_versions(tmp_path):
    build_test_font(
        tmp_path / "Arial-Regular-v1.ttf",
        family="Arial",
        style="Regular",
        version="1.000",
        a_glyph_size=500,
    )
    build_test_font(
        tmp_path / "Arial-Regular-v4.ttf",
        family="Arial",
        style="Regular",
        version="4.000",
        a_glyph_size=500,
        extra_glyph=True,
    )
    conn = _conn()
    ingest_directory(conn, tmp_path)

    file_a = find_font_file(conn, "arial", "Regular", "1.000")
    file_b = find_font_file(conn, "arial", "Regular", "4.000")
    assert file_a is not None and file_b is not None

    diff = compare_font_files(conn, file_a["id"], file_b["id"])

    assert diff.only_in_a == []
    assert diff.only_in_b == ["B"]
    assert diff.changed == []  # same a_glyph_size => "A" outline identical
    assert diff.unchanged_count == 2  # ".notdef" and "A"
