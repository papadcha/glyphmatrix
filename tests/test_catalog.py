from __future__ import annotations

import pytest

from glyphmatrix.core.catalog import export_catalog
from glyphmatrix.core.database import connect, init_schema
from glyphmatrix.core.ingest import ingest_directory

from .fontbuilder import build_test_font


def _conn():
    conn = connect(":memory:")
    init_schema(conn)
    return conn


def test_export_catalog_creates_pdf(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    build_test_font(tmp_path / "Arial-Bold.ttf", family="Arial", style="Bold")
    conn = _conn()
    ingest_directory(conn, tmp_path)
    out = tmp_path / "catalog.pdf"

    result = export_catalog(conn, out)

    assert result == out
    assert out.exists()
    assert out.stat().st_size > 0
    assert out.read_bytes()[:4] == b"%PDF"


def test_export_catalog_multiple_families(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    build_test_font(tmp_path / "Verdana-Regular.ttf", family="Verdana", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)

    out = export_catalog(conn, tmp_path / "catalog.pdf")

    assert out.exists()
    assert out.stat().st_size > 0


def test_export_catalog_family_filter(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    build_test_font(tmp_path / "Verdana-Regular.ttf", family="Verdana", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)

    out = export_catalog(conn, tmp_path / "catalog.pdf", families=["Arial"])

    assert out.exists()


def test_export_catalog_unknown_family_skipped(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)

    out = export_catalog(conn, tmp_path / "catalog.pdf", families=["Arial", "DoesNotExist"])

    assert out.exists()


def test_export_catalog_empty_library_raises(tmp_path):
    conn = _conn()

    with pytest.raises(ValueError, match="no families"):
        export_catalog(conn, tmp_path / "catalog.pdf")


def test_export_catalog_creates_parent_dir(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)
    out = tmp_path / "subdir" / "catalog.pdf"

    export_catalog(conn, out)

    assert out.exists()


def test_export_catalog_custom_text(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)

    out = export_catalog(conn, tmp_path / "catalog.pdf", preview_text="Hello World")

    assert out.exists()
