from glyphmatrix.core.database import connect, init_schema
from glyphmatrix.core.ingest import ingest_directory
from glyphmatrix.core.query import list_open_issues
from glyphmatrix.core.validator import validate_library

from .fontbuilder import build_test_font


def _conn():
    conn = connect(":memory:")
    init_schema(conn)
    return conn


def test_validate_library_reports_no_issues_for_healthy_files(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)

    summary = validate_library(conn)

    assert summary.checked == 1
    assert summary.issues_opened == 0
    assert list_open_issues(conn) == []


def test_validate_library_flags_missing_file(tmp_path):
    path = build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)
    path.unlink()

    summary = validate_library(conn)
    issues = list_open_issues(conn)

    assert summary.issues_opened == 1
    assert len(issues) == 1
    assert issues[0]["issue_type"] == "missing_file"
    assert issues[0]["severity"] == "error"
    assert issues[0]["family"] == "Arial"


def test_validate_library_resolves_missing_file_when_restored(tmp_path):
    path = build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)
    path.unlink()
    validate_library(conn)
    assert len(list_open_issues(conn)) == 1

    build_test_font(path, family="Arial", style="Regular")
    summary = validate_library(conn)

    assert summary.issues_resolved == 1
    assert list_open_issues(conn) == []


def test_validate_library_flags_corrupt_file(tmp_path):
    path = build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)
    path.write_bytes(b"not a font, just garbage bytes")

    summary = validate_library(conn)
    issues = list_open_issues(conn)

    assert summary.issues_opened == 1
    assert issues[0]["issue_type"] == "corrupt"
    assert "sfntVersion" in issues[0]["detail"] or issues[0]["detail"]


def test_validate_library_is_idempotent(tmp_path):
    path = build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)
    path.unlink()

    validate_library(conn)
    summary = validate_library(conn)

    assert summary.issues_opened == 0  # already-open issue isn't duplicated
    assert len(list_open_issues(conn)) == 1
