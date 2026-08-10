from glyphmatrix.core.database import connect, init_schema
from glyphmatrix.core.ingest import ingest_directory
from glyphmatrix.core.query import get_family_detail, list_faces

from .fontbuilder import build_test_font


def _conn():
    conn = connect(":memory:")
    init_schema(conn)
    return conn


def test_list_faces_returns_one_row_per_face(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    build_test_font(tmp_path / "Arial-Bold.ttf", family="Arial", style="Bold")
    conn = _conn()
    ingest_directory(conn, tmp_path)

    faces = list_faces(conn)

    assert len(faces) == 2
    styles = {f["style"] for f in faces}
    assert styles == {"Regular", "Bold"}
    assert all(f["family"] == "Arial" for f in faces)
    assert all(f["file_count"] == 1 for f in faces)


def test_list_faces_empty_library():
    conn = _conn()
    assert list_faces(conn) == []


def test_get_family_detail_includes_files(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)

    detail = get_family_detail(conn, "Arial")

    assert detail["family"] == "Arial"
    assert len(detail["faces"]) == 1
    face = detail["faces"][0]
    assert face["style"] == "Regular"
    assert len(face["files"]) == 1
    assert face["files"][0]["filename"] == "Arial-Regular.ttf"
    assert face["files"][0]["glyph_count"] == 2


def test_get_family_detail_is_case_insensitive(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)

    assert get_family_detail(conn, "arial") is not None
    assert get_family_detail(conn, "ARIAL") is not None


def test_get_family_detail_missing_family_returns_none():
    conn = _conn()
    assert get_family_detail(conn, "Nonexistent") is None
