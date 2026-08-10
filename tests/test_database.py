import sqlite3

import pytest

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
    "font_glyphs",
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


def test_font_files_path_unique_constraint():
    conn = connect(":memory:")
    init_schema(conn)
    conn.execute("INSERT INTO families (name) VALUES ('Inter')")
    conn.execute("INSERT INTO font_faces (family_id, style) VALUES (1, 'Regular')")
    conn.execute(
        "INSERT INTO font_files (font_face_id, path, filename, content_hash, source) "
        "VALUES (1, 'C:/fonts/Inter-Regular.ttf', 'Inter-Regular.ttf', 'hash1', 'user')"
    )

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO font_files (font_face_id, path, filename, content_hash, source) "
            "VALUES (1, 'C:/fonts/Inter-Regular.ttf', 'Inter-Regular.ttf', 'hash2', 'user')"
        )


def test_collections_name_unique_constraint_case_insensitive():
    conn = connect(":memory:")
    init_schema(conn)
    conn.execute("INSERT INTO collections (name) VALUES ('Favorites')")

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO collections (name) VALUES ('favorites')")


def test_activations_unique_per_file_and_platform():
    conn = connect(":memory:")
    init_schema(conn)
    conn.execute("INSERT INTO families (name) VALUES ('Inter')")
    conn.execute("INSERT INTO font_faces (family_id, style) VALUES (1, 'Regular')")
    conn.execute(
        "INSERT INTO font_files (font_face_id, path, filename, content_hash, source) "
        "VALUES (1, 'C:/fonts/Inter-Regular.ttf', 'Inter-Regular.ttf', 'hash1', 'user')"
    )
    conn.execute(
        "INSERT INTO activations (font_file_id, platform, state) VALUES (1, 'windows', 'active')"
    )

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO activations (font_file_id, platform, state) VALUES (1, 'windows', 'installed')"
        )
