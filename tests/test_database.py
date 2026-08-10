import sqlite3

from glyphmatrix.core.database import connect, init_schema

EXPECTED_TABLES = {
    "families",
    "font_faces",
    "font_files",
    "activations",
    "tags",
    "font_tags",
    "collections",
    "collection_faces",
    "validation_issues",
    "scan_runs",
}


def test_init_schema_creates_expected_tables():
    conn = connect(":memory:")
    init_schema(conn)
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    assert EXPECTED_TABLES.issubset({row["name"] for row in rows})


def test_font_files_source_check_constraint():
    conn = connect(":memory:")
    init_schema(conn)
    conn.execute(
        "INSERT INTO families (name) VALUES ('Inter')"
    )
    conn.execute(
        "INSERT INTO font_faces (family_id, style) VALUES (1, 'Regular')"
    )
    try:
        conn.execute(
            "INSERT INTO font_files (font_face_id, path, filename, content_hash, source) "
            "VALUES (1, 'C:/fonts/Inter-Regular.ttf', 'Inter-Regular.ttf', 'abc123', 'not_a_real_source')"
        )
        assert False, "expected CHECK constraint to reject invalid source"
    except sqlite3.IntegrityError:
        pass
