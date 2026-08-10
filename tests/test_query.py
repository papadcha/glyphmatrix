from glyphmatrix.core.database import connect, init_schema
from glyphmatrix.core.ingest import ingest_directory
from glyphmatrix.core.query import find_face_id, get_family_detail, list_faces, search_library
from glyphmatrix.core.tags import add_tags

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


def test_search_library_matches_family_name(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    build_test_font(tmp_path / "Verdana-Regular.ttf", family="Verdana", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)

    results = search_library(conn, "aria")

    assert len(results) == 1
    assert results[0]["family"] == "Arial"


def test_search_library_matches_style(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    build_test_font(tmp_path / "Arial-Bold.ttf", family="Arial", style="Bold")
    conn = _conn()
    ingest_directory(conn, tmp_path)

    results = search_library(conn, "bold")

    assert len(results) == 1
    assert results[0]["style"] == "Bold"


def test_search_library_matches_tags(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)
    face_id = find_face_id(conn, "Arial", "Regular")
    add_tags(conn, face_id, ["grotesque"])

    results = search_library(conn, "grotesque")

    assert len(results) == 1
    assert results[0]["family"] == "Arial"


def test_search_library_is_case_insensitive_and_no_duplicates(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)
    face_id = find_face_id(conn, "Arial", "Regular")
    add_tags(conn, face_id, ["sans", "grotesque"])  # two tags, both irrelevant to this query

    results = search_library(conn, "ARIAL")

    assert len(results) == 1  # not duplicated despite two tag rows


def test_search_library_no_matches():
    conn = _conn()
    assert search_library(conn, "nonexistent") == []
