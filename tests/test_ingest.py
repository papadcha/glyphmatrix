import shutil

from glyphmatrix.core.database import connect, init_schema
from glyphmatrix.core.duplicates import find_duplicates
from glyphmatrix.core.ingest import ingest_directory
from glyphmatrix.core.query import find_face_id
from glyphmatrix.core.tags import list_tags_for_face

from .fontbuilder import build_test_font


def _conn():
    conn = connect(":memory:")
    init_schema(conn)
    return conn


def test_ingest_directory_adds_new_files(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    build_test_font(tmp_path / "Arial-Bold.ttf", family="Arial", style="Bold")
    conn = _conn()

    result = ingest_directory(conn, tmp_path)

    assert result.files_scanned == 2
    assert result.files_added == 2
    assert result.files_changed == 0
    assert result.errors == 0

    families = conn.execute("SELECT name FROM families").fetchall()
    assert [f["name"] for f in families] == ["Arial"]

    faces = conn.execute("SELECT style FROM font_faces ORDER BY style").fetchall()
    assert [f["style"] for f in faces] == ["Bold", "Regular"]

    glyph_rows = conn.execute("SELECT COUNT(*) AS n FROM font_glyphs").fetchone()
    assert glyph_rows["n"] == 4  # 2 glyphs x 2 files


def test_ingest_directory_stores_foundry(tmp_path):
    build_test_font(
        tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular", manufacturer="Monotype"
    )
    conn = _conn()

    ingest_directory(conn, tmp_path)

    row = conn.execute("SELECT foundry FROM families WHERE name = 'Arial'").fetchone()
    assert row["foundry"] == "Monotype"


def test_ingest_directory_auto_tags_family_class(tmp_path):
    build_test_font(
        tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular", family_class=8 * 256 + 1
    )
    conn = _conn()

    ingest_directory(conn, tmp_path)

    face_id = find_face_id(conn, "Arial", "Regular")
    assert "sans-serif" in list_tags_for_face(conn, face_id)


def test_ingest_directory_no_family_class_tag_when_unclassified(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()

    ingest_directory(conn, tmp_path)

    face_id = find_face_id(conn, "Arial", "Regular")
    assert list_tags_for_face(conn, face_id) == []


def test_ingest_directory_auto_tags_panose_class(tmp_path):
    build_test_font(
        tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular",
        panose=(2, 14, 5, 3, 2, 2, 2, 2, 2, 4),
    )
    conn = _conn()

    ingest_directory(conn, tmp_path)

    face_id = find_face_id(conn, "Arial", "Regular")
    assert "flared" in list_tags_for_face(conn, face_id)


def test_ingest_directory_no_panose_tag_when_unset(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()

    ingest_directory(conn, tmp_path)

    face_id = find_face_id(conn, "Arial", "Regular")
    assert list_tags_for_face(conn, face_id) == []


def test_ingest_directory_tracks_unsupported_formats_and_flags_them(tmp_path):
    (tmp_path / "OldFont.bdf").write_bytes(b"STARTFONT 2.1\nFONT -misc-fixed\n")
    conn = _conn()

    result = ingest_directory(conn, tmp_path)

    assert result.files_scanned == 1
    assert result.files_added == 1
    assert result.errors == 0

    family = conn.execute("SELECT name FROM families").fetchone()
    assert family["name"] == "OldFont"

    issue = conn.execute(
        "SELECT severity, issue_type, resolved_at FROM validation_issues"
    ).fetchone()
    assert issue["issue_type"] == "unsupported_format"
    assert issue["severity"] == "info"
    assert issue["resolved_at"] is None


def test_ingest_directory_duplicate_detection_works_for_unsupported_formats(tmp_path):
    original = tmp_path / "OldFont.bdf"
    original.write_bytes(b"identical placeholder bytes")
    shutil.copy(original, tmp_path / "OldFont-copy.bdf")
    conn = _conn()

    ingest_directory(conn, tmp_path)

    groups = find_duplicates(conn)
    assert len(groups) == 1
    assert len(groups[0]["files"]) == 2


def test_ingest_directory_is_idempotent_when_unchanged(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()

    ingest_directory(conn, tmp_path)
    result = ingest_directory(conn, tmp_path)

    assert result.files_scanned == 1
    assert result.files_added == 0
    assert result.files_changed == 0

    family_count = conn.execute("SELECT COUNT(*) AS n FROM families").fetchone()["n"]
    assert family_count == 1


def test_ingest_directory_detects_changed_content(tmp_path):
    path = build_test_font(tmp_path / "Arial-Regular.ttf", a_glyph_size=500)
    conn = _conn()
    ingest_directory(conn, tmp_path)

    build_test_font(path, a_glyph_size=700)
    result = ingest_directory(conn, tmp_path)

    assert result.files_changed == 1
    assert result.files_added == 0

    file_row = conn.execute("SELECT id, content_hash FROM font_files").fetchone()
    glyph_count = conn.execute(
        "SELECT COUNT(*) AS n FROM font_glyphs WHERE font_file_id = ?", (file_row["id"],)
    ).fetchone()["n"]
    assert glyph_count == 2  # replaced, not duplicated

    scan_runs = conn.execute("SELECT files_changed FROM scan_runs ORDER BY id").fetchall()
    assert [r["files_changed"] for r in scan_runs] == [0, 1]
