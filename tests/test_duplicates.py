import shutil

from glyphmatrix.core.database import connect, init_schema
from glyphmatrix.core.duplicates import find_duplicates
from glyphmatrix.core.ingest import ingest_directory

from .fontbuilder import build_test_font


def _conn():
    conn = connect(":memory:")
    init_schema(conn)
    return conn


def test_find_duplicates_groups_byte_identical_files(tmp_path):
    original = build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    subfolder = tmp_path / "subfolder"
    subfolder.mkdir()
    copy_path = subfolder / "Arial-Regular-copy.ttf"
    shutil.copy(original, copy_path)
    build_test_font(tmp_path / "Verdana-Regular.ttf", family="Verdana", style="Regular")

    conn = _conn()
    ingest_directory(conn, tmp_path)

    groups = find_duplicates(conn)

    assert len(groups) == 1
    assert len(groups[0]["files"]) == 2
    paths = {f["path"] for f in groups[0]["files"]}
    assert paths == {str(original), str(copy_path)}


def test_find_duplicates_empty_when_all_unique(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    build_test_font(tmp_path / "Arial-Bold.ttf", family="Arial", style="Bold")
    conn = _conn()
    ingest_directory(conn, tmp_path)

    assert find_duplicates(conn) == []


def test_find_duplicates_empty_library():
    conn = _conn()
    assert find_duplicates(conn) == []
