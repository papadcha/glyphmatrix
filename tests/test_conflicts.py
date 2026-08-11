import shutil

from glyphmatrix.core.conflicts import list_conflicts
from glyphmatrix.core.database import connect, init_schema
from glyphmatrix.core.ingest import ingest_directory

from .fontbuilder import build_test_font


def _conn():
    conn = connect(":memory:")
    init_schema(conn)
    return conn


def test_list_conflicts_finds_different_files_claiming_same_face(tmp_path):
    subfolder = tmp_path / "microsoft"
    subfolder.mkdir()
    build_test_font(subfolder / "Arial-Regular.ttf", family="Arial", style="Regular", a_glyph_size=700)
    other = tmp_path / "other-foundry"
    other.mkdir()
    build_test_font(other / "Arial-Alt.ttf", family="Arial", style="Regular", a_glyph_size=500)
    conn = _conn()
    ingest_directory(conn, tmp_path)

    conflicts = list_conflicts(conn)

    assert len(conflicts) == 1
    assert conflicts[0]["family"] == "Arial"
    assert conflicts[0]["style"] == "Regular"
    assert len(conflicts[0]["files"]) == 2


def test_list_conflicts_ignores_byte_identical_duplicates(tmp_path):
    original = tmp_path / "Arial-Regular.ttf"
    build_test_font(original, family="Arial", style="Regular")
    shutil.copy(original, tmp_path / "Arial-Regular-copy.ttf")
    conn = _conn()
    ingest_directory(conn, tmp_path)

    assert list_conflicts(conn) == []  # same content — that's duplicates.py's job, not a conflict


def test_list_conflicts_ignores_faces_with_a_single_file(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    build_test_font(tmp_path / "Arial-Bold.ttf", family="Arial", style="Bold")
    conn = _conn()
    ingest_directory(conn, tmp_path)

    assert list_conflicts(conn) == []


def test_list_conflicts_empty_library():
    conn = _conn()
    assert list_conflicts(conn) == []
