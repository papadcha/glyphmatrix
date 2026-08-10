from glyphmatrix.core.database import connect, init_schema
from glyphmatrix.core.ingest import ingest_directory

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
