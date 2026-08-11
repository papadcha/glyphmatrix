import pytest

from glyphmatrix.core.collections import (
    FAVORITES_COLLECTION_NAME,
    add_face_to_collection,
    create_collection,
    create_smart_collection,
    find_collection_id,
    get_or_create_favorites_collection,
    list_collection_face_ids,
    list_collection_faces,
    list_collections,
    remove_face_from_collection,
)
from glyphmatrix.core.database import connect, init_schema
from glyphmatrix.core.ingest import ingest_directory
from glyphmatrix.core.query import find_face_id

from .fontbuilder import build_test_font


def _conn():
    conn = connect(":memory:")
    init_schema(conn)
    return conn


def _ingested_face_id(conn, tmp_path, family="Arial", style="Regular"):
    build_test_font(tmp_path / f"{family}-{style}.ttf", family=family, style=style)
    ingest_directory(conn, tmp_path)
    return find_face_id(conn, family, style)


def test_create_collection_and_lookup():
    conn = _conn()
    collection_id = create_collection(conn, "Work Fonts")

    assert find_collection_id(conn, "work fonts") == collection_id  # case-insensitive


def test_create_collection_rejects_duplicate_name():
    conn = _conn()
    create_collection(conn, "Work Fonts")

    with pytest.raises(ValueError):
        create_collection(conn, "work fonts")


def test_create_collection_with_missing_parent_raises():
    conn = _conn()

    with pytest.raises(ValueError):
        create_collection(conn, "Sub", parent_name="Nonexistent")


def test_create_collection_with_parent():
    conn = _conn()
    create_collection(conn, "Parent")
    create_collection(conn, "Child", parent_name="Parent")

    collections = {c["name"]: c["parent_name"] for c in list_collections(conn)}
    assert collections == {"Parent": None, "Child": "Parent"}


def test_add_and_remove_face_from_collection(tmp_path):
    conn = _conn()
    face_id = _ingested_face_id(conn, tmp_path)
    collection_id = create_collection(conn, "Favorites")

    add_face_to_collection(conn, collection_id, face_id)
    assert list_collection_faces(conn, collection_id) == [{"family": "Arial", "style": "Regular"}]

    # adding twice is a no-op, not an error
    add_face_to_collection(conn, collection_id, face_id)
    assert len(list_collection_faces(conn, collection_id)) == 1

    assert remove_face_from_collection(conn, collection_id, face_id) is True
    assert list_collection_faces(conn, collection_id) == []
    assert remove_face_from_collection(conn, collection_id, face_id) is False


def test_list_collections_reports_face_count(tmp_path):
    conn = _conn()
    face_id = _ingested_face_id(conn, tmp_path)
    collection_id = create_collection(conn, "Favorites")
    add_face_to_collection(conn, collection_id, face_id)

    collections = {c["name"]: c["face_count"] for c in list_collections(conn)}
    assert collections == {"Favorites": 1}


def test_get_or_create_favorites_collection_creates_once():
    conn = _conn()

    first = get_or_create_favorites_collection(conn)
    second = get_or_create_favorites_collection(conn)

    assert first == second
    assert find_collection_id(conn, FAVORITES_COLLECTION_NAME) == first


def test_get_or_create_favorites_collection_reuses_manually_created_one():
    conn = _conn()
    manual_id = create_collection(conn, FAVORITES_COLLECTION_NAME)

    assert get_or_create_favorites_collection(conn) == manual_id


def test_create_smart_collection_and_list_faces(tmp_path):
    conn = _conn()
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    build_test_font(tmp_path / "Arial-Bold.ttf", family="Arial", style="Bold")
    ingest_directory(conn, tmp_path)

    create_smart_collection(conn, "Bold Faces", "style:Bold")

    faces = list_collection_faces(conn, find_collection_id(conn, "Bold Faces"))
    assert faces == [{"family": "Arial", "style": "Bold"}]


def test_smart_collection_membership_updates_as_library_changes(tmp_path):
    conn = _conn()
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    ingest_directory(conn, tmp_path)
    create_smart_collection(conn, "Bold Faces", "style:Bold")
    collection_id = find_collection_id(conn, "Bold Faces")
    assert list_collection_faces(conn, collection_id) == []

    build_test_font(tmp_path / "Arial-Bold.ttf", family="Arial", style="Bold")
    ingest_directory(conn, tmp_path)

    assert list_collection_faces(conn, collection_id) == [{"family": "Arial", "style": "Bold"}]


def test_create_smart_collection_rejects_bad_query():
    conn = _conn()
    with pytest.raises(ValueError):
        create_smart_collection(conn, "Broken", "nonsense:value")
    assert find_collection_id(conn, "Broken") is None  # never created


def test_cannot_manually_add_face_to_smart_collection(tmp_path):
    conn = _conn()
    face_id = _ingested_face_id(conn, tmp_path)
    create_smart_collection(conn, "Bold Faces", "style:Bold")
    collection_id = find_collection_id(conn, "Bold Faces")

    with pytest.raises(ValueError):
        add_face_to_collection(conn, collection_id, face_id)


def test_cannot_manually_remove_face_from_smart_collection(tmp_path):
    conn = _conn()
    create_smart_collection(conn, "Bold Faces", "style:Bold")
    collection_id = find_collection_id(conn, "Bold Faces")

    with pytest.raises(ValueError):
        remove_face_from_collection(conn, collection_id, 1)


def test_list_collections_shows_computed_face_count_for_smart_collections(tmp_path):
    conn = _conn()
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    build_test_font(tmp_path / "Verdana-Regular.ttf", family="Verdana", style="Regular")
    ingest_directory(conn, tmp_path)
    create_smart_collection(conn, "All Regular", "style:Regular")

    entry = next(c for c in list_collections(conn) if c["name"] == "All Regular")
    assert entry["is_smart"] is True
    assert entry["face_count"] == 2


def test_list_collection_face_ids_works_for_smart_collections(tmp_path):
    conn = _conn()
    face_id = _ingested_face_id(conn, tmp_path)  # Arial Regular
    create_smart_collection(conn, "All Regular", "style:Regular")
    collection_id = find_collection_id(conn, "All Regular")

    assert list_collection_face_ids(conn, collection_id) == [face_id]
