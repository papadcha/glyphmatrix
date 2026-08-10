from glyphmatrix.core.database import connect, init_schema
from glyphmatrix.core.ingest import ingest_directory
from glyphmatrix.core.query import find_face_id
from glyphmatrix.core.tags import add_tags, find_faces_by_tag, list_all_tags, list_tags_for_face, remove_tag

from .fontbuilder import build_test_font


def _conn():
    conn = connect(":memory:")
    init_schema(conn)
    return conn


def _ingested_face_id(conn, tmp_path, family="Arial", style="Regular"):
    build_test_font(tmp_path / f"{family}-{style}.ttf", family=family, style=style)
    ingest_directory(conn, tmp_path)
    return find_face_id(conn, family, style)


def test_add_tags_applies_new_and_skips_duplicates(tmp_path):
    conn = _conn()
    face_id = _ingested_face_id(conn, tmp_path)

    applied = add_tags(conn, face_id, ["Sans", "grotesque"])
    assert applied == ["Sans", "grotesque"]

    applied_again = add_tags(conn, face_id, ["sans", "neutral"])  # "sans" ~ "Sans", case-insensitive
    assert applied_again == ["neutral"]

    assert set(list_tags_for_face(conn, face_id)) == {"Sans", "grotesque", "neutral"}


def test_add_tags_ignores_blank_entries(tmp_path):
    conn = _conn()
    face_id = _ingested_face_id(conn, tmp_path)

    applied = add_tags(conn, face_id, ["sans", "  ", ""])
    assert applied == ["sans"]


def test_remove_tag(tmp_path):
    conn = _conn()
    face_id = _ingested_face_id(conn, tmp_path)
    add_tags(conn, face_id, ["sans"])

    assert remove_tag(conn, face_id, "SANS") is True  # case-insensitive
    assert list_tags_for_face(conn, face_id) == []
    assert remove_tag(conn, face_id, "sans") is False  # already gone


def test_list_all_tags_counts_faces(tmp_path):
    conn = _conn()
    face_a = _ingested_face_id(conn, tmp_path, family="Arial", style="Regular")
    face_b = _ingested_face_id(conn, tmp_path, family="Verdana", style="Regular")
    add_tags(conn, face_a, ["sans"])
    add_tags(conn, face_b, ["sans", "wide"])

    tags = {t["name"]: t["face_count"] for t in list_all_tags(conn)}
    assert tags == {"sans": 2, "wide": 1}


def test_find_faces_by_tag(tmp_path):
    conn = _conn()
    face_a = _ingested_face_id(conn, tmp_path, family="Arial", style="Regular")
    add_tags(conn, face_a, ["sans"])

    results = find_faces_by_tag(conn, "SANS")
    assert results == [{"family": "Arial", "style": "Regular"}]
    assert find_faces_by_tag(conn, "nope") == []
