from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from glyphmatrix.core.collections import create_collection
from glyphmatrix.core.database import connect, init_schema
from glyphmatrix.core.doc_fonts import extract_font_names, match_library_families
from glyphmatrix.core.ingest import ingest_directory
from glyphmatrix.core.projects import find_project_collection, list_projects, set_project, unset_project

from .fontbuilder import build_test_font


def _conn():
    conn = connect(":memory:")
    init_schema(conn)
    return conn


# ── projects CRUD ──────────────────────────────────────────────────────────────

def test_set_project_and_list(tmp_path):
    conn = _conn()
    create_collection(conn, "Body Text")
    set_project(conn, str(tmp_path), "Body Text")
    mappings = list_projects(conn)
    assert len(mappings) == 1
    assert mappings[0]["collection"] == "Body Text"


def test_set_project_replaces_existing(tmp_path):
    conn = _conn()
    create_collection(conn, "A")
    create_collection(conn, "B")
    set_project(conn, str(tmp_path), "A")
    set_project(conn, str(tmp_path), "B")
    mappings = list_projects(conn)
    assert len(mappings) == 1
    assert mappings[0]["collection"] == "B"


def test_set_project_unknown_collection_raises(tmp_path):
    conn = _conn()
    with pytest.raises(ValueError, match="no such collection"):
        set_project(conn, str(tmp_path), "DoesNotExist")


def test_unset_project_removes_mapping(tmp_path):
    conn = _conn()
    create_collection(conn, "A")
    set_project(conn, str(tmp_path), "A")
    assert unset_project(conn, str(tmp_path)) is True
    assert list_projects(conn) == []


def test_unset_project_returns_false_when_not_set(tmp_path):
    conn = _conn()
    assert unset_project(conn, str(tmp_path)) is False


def test_find_project_collection_exact_match(tmp_path):
    conn = _conn()
    create_collection(conn, "Design")
    set_project(conn, str(tmp_path), "Design")
    assert find_project_collection(conn, str(tmp_path)) == "Design"


def test_find_project_collection_walks_up(tmp_path):
    conn = _conn()
    create_collection(conn, "Design")
    set_project(conn, str(tmp_path), "Design")
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    assert find_project_collection(conn, str(deep)) == "Design"


def test_find_project_collection_not_found(tmp_path):
    conn = _conn()
    deep = tmp_path / "sub"
    deep.mkdir()
    assert find_project_collection(conn, str(deep)) is None


def test_find_project_collection_nearest_ancestor_wins(tmp_path):
    conn = _conn()
    create_collection(conn, "Root")
    create_collection(conn, "Sub")
    sub = tmp_path / "sub"
    sub.mkdir()
    set_project(conn, str(tmp_path), "Root")
    set_project(conn, str(sub), "Sub")
    deep = sub / "deeper"
    deep.mkdir()
    assert find_project_collection(conn, str(deep)) == "Sub"


# ── doc_fonts extraction ───────────────────────────────────────────────────────

def _make_docx(path: Path, fonts: list[str]) -> Path:
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    inner = "\n".join(f'<w:font w:name="{f}"/>' for f in fonts)
    xml = f'<?xml version="1.0"?><w:fonts xmlns:w="{ns}">{inner}</w:fonts>'
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/fontTable.xml", xml)
    return path


def _make_odt(path: Path, fonts: list[str]) -> Path:
    sns = "urn:oasis:names:tc:opendocument:xmlns:style:1.0"
    svg = "urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0"
    inner = "\n".join(f'<style:font-face style:name="{f}" svg:font-family="{f}"/>' for f in fonts)
    xml = f'<?xml version="1.0"?><office:document-content xmlns:style="{sns}" xmlns:svg="{svg}" xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0">{inner}</office:document-content>'
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("content.xml", xml)
    return path


def _make_pdf(path: Path, fonts: list[str]) -> Path:
    content = b""
    for f in fonts:
        content += f"/BaseFont /{f}\n".encode()
    path.write_bytes(content)
    return path


def test_extract_font_names_docx(tmp_path):
    doc = _make_docx(tmp_path / "test.docx", ["Arial", "Times New Roman"])
    names = extract_font_names(doc)
    assert "Arial" in names
    assert "Times New Roman" in names


def test_extract_font_names_odt(tmp_path):
    doc = _make_odt(tmp_path / "test.odt", ["DejaVu Sans", "Roboto"])
    names = extract_font_names(doc)
    assert "DejaVu Sans" in names
    assert "Roboto" in names


def test_extract_font_names_pdf(tmp_path):
    doc = _make_pdf(tmp_path / "test.pdf", ["Helvetica", "ABCDEF+TimesRoman"])
    names = extract_font_names(doc)
    assert "Helvetica" in names
    assert "TimesRoman" in names  # subset prefix stripped
    assert "ABCDEF+TimesRoman" not in names


def test_extract_font_names_unsupported_format(tmp_path):
    with pytest.raises(ValueError, match="unsupported"):
        extract_font_names(tmp_path / "test.xlsx")


def test_match_library_families(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    build_test_font(tmp_path / "Verdana-Regular.ttf", family="Verdana", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)

    matched, unmatched = match_library_families(conn, {"Arial", "Helvetica", "ArialMT"})
    assert "Arial" in matched
    assert "Verdana" not in matched
    assert "Helvetica" in unmatched


def test_match_library_families_empty(tmp_path):
    conn = _conn()
    matched, unmatched = match_library_families(conn, {"Helvetica"})
    assert matched == []
    assert "Helvetica" in unmatched
