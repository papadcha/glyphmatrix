import pytest

from glyphmatrix.core.database import connect, init_schema
from glyphmatrix.core.ingest import ingest_directory
from glyphmatrix.core.packages import (
    add_document,
    add_file_to_package,
    create_package,
    find_package_id,
    list_documents,
    list_package_files,
    list_packages,
    remove_document,
    remove_file_from_package,
)
from glyphmatrix.core.query import find_first_font_file_for_face, find_face_id

from .fontbuilder import build_test_font


def _conn():
    conn = connect(":memory:")
    init_schema(conn)
    return conn


def _ingested_font_file_id(conn, tmp_path, family="Arial", style="Regular"):
    build_test_font(tmp_path / f"{family}-{style}.ttf", family=family, style=style)
    ingest_directory(conn, tmp_path)
    face_id = find_face_id(conn, family, style)
    return find_first_font_file_for_face(conn, face_id)["id"]


def test_create_package_and_lookup():
    conn = _conn()
    package_id = create_package(conn, "Adobe Font Folio 11", vendor="Adobe")

    assert find_package_id(conn, "adobe font folio 11") == package_id  # case-insensitive


def test_create_package_rejects_duplicate_name():
    conn = _conn()
    create_package(conn, "Adobe Font Folio 11")

    with pytest.raises(ValueError):
        create_package(conn, "adobe font folio 11")


def test_add_and_remove_file_from_package(tmp_path):
    conn = _conn()
    font_file_id = _ingested_font_file_id(conn, tmp_path)
    package_id = create_package(conn, "Adobe Font Folio 11")

    add_file_to_package(conn, package_id, font_file_id)
    files = list_package_files(conn, package_id)
    assert len(files) == 1
    assert files[0]["family"] == "Arial"
    assert files[0]["style"] == "Regular"
    assert files[0]["filename"] == "Arial-Regular.ttf"

    # adding twice is a no-op, not an error
    add_file_to_package(conn, package_id, font_file_id)
    assert len(list_package_files(conn, package_id)) == 1

    assert remove_file_from_package(conn, package_id, font_file_id) is True
    assert list_package_files(conn, package_id) == []
    assert remove_file_from_package(conn, package_id, font_file_id) is False


def test_list_packages_reports_counts(tmp_path):
    conn = _conn()
    font_file_id = _ingested_font_file_id(conn, tmp_path)
    package_id = create_package(conn, "Adobe Font Folio 11", vendor="Adobe")
    add_file_to_package(conn, package_id, font_file_id)
    add_document(conn, package_id, "readme.pdf")

    packages = list_packages(conn)
    assert packages == [
        {"name": "Adobe Font Folio 11", "vendor": "Adobe", "file_count": 1, "document_count": 1}
    ]


def test_add_list_remove_documents():
    conn = _conn()
    package_id = create_package(conn, "Adobe Font Folio 11")

    add_document(conn, package_id, "license.pdf", description="EULA")
    add_document(conn, package_id, "readme.txt")

    docs = list_documents(conn, package_id)
    assert docs == [
        {"path": "license.pdf", "description": "EULA"},
        {"path": "readme.txt", "description": None},
    ]

    assert remove_document(conn, package_id, "license.pdf") is True
    assert [d["path"] for d in list_documents(conn, package_id)] == ["readme.txt"]
    assert remove_document(conn, package_id, "license.pdf") is False
