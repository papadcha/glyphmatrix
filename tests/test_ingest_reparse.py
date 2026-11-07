"""Rescans must not leave empty font_faces behind when the parser's output
changes for a file whose content didn't (the orphan face bug), and
--reparse must update the existing face rather than create a new one."""
import dataclasses
import shutil

from click.testing import CliRunner

from glyphmatrix.cli.main import fontctl
from glyphmatrix.core import ingest
from glyphmatrix.core.collections import add_face_to_collection, create_collection
from glyphmatrix.core.database import connect, init_schema
from glyphmatrix.core.ingest import ingest_directory
from glyphmatrix.core.parser import parse_font_file
from glyphmatrix.core.tags import add_tags, list_tags_for_face, remove_tag

from .fontbuilder import build_test_font


def _conn():
    conn = connect(":memory:")
    init_schema(conn)
    return conn


def _parser_now_says(monkeypatch, **changes):
    """Stand-in for a parser change: the same files now parse differently."""
    monkeypatch.setattr(
        ingest, "parse_font_file", lambda p: dataclasses.replace(parse_font_file(p), **changes)
    )


def _faces(conn):
    return conn.execute("SELECT id, style, weight FROM font_faces ORDER BY id").fetchall()


def _empty_faces(conn):
    return conn.execute(
        "SELECT COUNT(*) AS n FROM font_faces WHERE id NOT IN (SELECT font_face_id FROM font_files)"
    ).fetchone()["n"]


def _face_of(conn, filename):
    return conn.execute(
        "SELECT font_face_id FROM font_files WHERE filename = ?", (filename,)
    ).fetchone()["font_face_id"]


def test_rescan_after_parser_change_creates_no_orphan_face(tmp_path, monkeypatch):
    build_test_font(tmp_path / "Foo-Regular.ttf", family="Foo", style="Regular", weight=400)
    conn = _conn()
    ingest_directory(conn, tmp_path)
    before = [tuple(r) for r in _faces(conn)]
    assert [r[1:] for r in before] == [("Regular", 400)]

    _parser_now_says(monkeypatch, weight=900)
    result = ingest_directory(conn, tmp_path)

    assert [tuple(r) for r in _faces(conn)] == before  # no new face, old one kept as is
    assert _empty_faces(conn) == 0
    assert result.files_changed == 0 and result.files_reparsed == 0


def test_reparse_updates_existing_face_in_place(tmp_path, monkeypatch):
    build_test_font(tmp_path / "Foo-Regular.ttf", family="Foo", style="Regular", weight=400)
    conn = _conn()
    ingest_directory(conn, tmp_path)
    face_id = _face_of(conn, "Foo-Regular.ttf")
    assert [tuple(r) for r in _faces(conn)] == [(face_id, "Regular", 400)]
    add_tags(conn, face_id, ["display"])
    add_face_to_collection(conn, create_collection(conn, "Posters"), face_id)

    _parser_now_says(monkeypatch, weight=900)
    result = ingest_directory(conn, tmp_path, reparse=True)

    assert [tuple(r) for r in _faces(conn)] == [(face_id, "Regular", 900)]
    assert _face_of(conn, "Foo-Regular.ttf") == face_id
    assert "display" in list_tags_for_face(conn, face_id)
    assert conn.execute("SELECT font_face_id FROM collection_faces").fetchone()[0] == face_id
    assert result.files_reparsed == 1 and result.files_added == 0 and result.files_changed == 0


def test_reparse_on_new_file_ingests_normally(tmp_path):
    conn = _conn()
    build_test_font(tmp_path / "Foo-Regular.ttf", family="Foo", style="Regular")
    ingest_directory(conn, tmp_path)

    build_test_font(tmp_path / "Foo-Bold.ttf", family="Foo", style="Bold", weight=700)
    result = ingest_directory(conn, tmp_path, reparse=True)

    assert result.files_added == 1
    assert result.files_reparsed == 1  # the already-known Regular
    assert sorted((r["style"], r["weight"]) for r in _faces(conn)) == [("Bold", 700), ("Regular", 400)]
    glyphs = conn.execute(
        "SELECT COUNT(*) AS n FROM font_glyphs JOIN font_files ON font_files.id = font_file_id "
        "WHERE filename = 'Foo-Bold.ttf'"
    ).fetchone()["n"]
    assert glyphs == 2


def test_reparse_merges_into_face_that_already_has_the_new_values(tmp_path, monkeypatch):
    # Old copy says 400, newer copy of the same face already says 900: after
    # reparse both share the 900 face and the old face's tags move with it.
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    build_test_font(tmp_path / "a" / "Old.ttf", family="Foo", style="Regular", weight=400)
    build_test_font(tmp_path / "b" / "New.ttf", family="Foo", style="Regular", weight=900, a_glyph_size=600)
    conn = _conn()
    ingest_directory(conn, tmp_path)
    old_face, new_face = _face_of(conn, "Old.ttf"), _face_of(conn, "New.ttf")
    assert old_face != new_face
    add_tags(conn, old_face, ["favourite"])

    _parser_now_says(monkeypatch, weight=900)
    ingest_directory(conn, tmp_path, reparse=True)

    assert [r["id"] for r in _faces(conn)] == [new_face]
    assert _face_of(conn, "Old.ttf") == new_face
    assert "favourite" in list_tags_for_face(conn, new_face)


def test_reparse_moves_only_the_file_when_face_is_shared(tmp_path, monkeypatch):
    # Two files on one face; the parser now reads only one of them differently.
    path = build_test_font(tmp_path / "One.ttf", family="Foo", style="Regular", weight=400)
    shutil.copy(path, tmp_path / "Two.ttf")
    conn = _conn()
    ingest_directory(conn, tmp_path)
    shared = _face_of(conn, "One.ttf")
    assert _face_of(conn, "Two.ttf") == shared and len(_faces(conn)) == 1

    def parser(p):
        parsed = parse_font_file(p)
        return dataclasses.replace(parsed, weight=900) if p.name == "One.ttf" else parsed

    monkeypatch.setattr(ingest, "parse_font_file", parser)
    ingest_directory(conn, tmp_path, reparse=True)

    assert _face_of(conn, "Two.ttf") == shared
    assert conn.execute("SELECT weight FROM font_faces WHERE id = ?", (shared,)).fetchone()[0] == 400
    moved = _face_of(conn, "One.ttf")
    assert conn.execute("SELECT weight FROM font_faces WHERE id = ?", (moved,)).fetchone()[0] == 900
    assert _empty_faces(conn) == 0


def test_changed_content_updates_sole_face_in_place(tmp_path):
    path = build_test_font(tmp_path / "Foo.ttf", family="Foo", style="Regular", weight=400)
    conn = _conn()
    ingest_directory(conn, tmp_path)
    face_id = _face_of(conn, "Foo.ttf")
    assert [tuple(r) for r in _faces(conn)] == [(face_id, "Regular", 400)]

    build_test_font(path, family="Foo", style="Regular", weight=900)
    ingest_directory(conn, tmp_path)

    assert [tuple(r) for r in _faces(conn)] == [(face_id, "Regular", 900)]


def test_reparse_removes_family_left_empty(tmp_path, monkeypatch):
    build_test_font(tmp_path / "Foo.ttf", family="Foo")
    conn = _conn()
    ingest_directory(conn, tmp_path)

    _parser_now_says(monkeypatch, family_name="Foo Pro")
    ingest_directory(conn, tmp_path, reparse=True)

    assert [r["name"] for r in conn.execute("SELECT name FROM families")] == ["Foo Pro"]


def test_cli_scan_reparse_flag(tmp_path):
    (tmp_path / "fonts").mkdir()
    build_test_font(tmp_path / "fonts" / "Foo.ttf", family="Foo")
    db_path = tmp_path / "library.db"
    runner = CliRunner()
    runner.invoke(fontctl, ["--db", str(db_path), "scan", str(tmp_path / "fonts")])

    plain = runner.invoke(fontctl, ["--db", str(db_path), "scan", str(tmp_path / "fonts")])
    result = runner.invoke(fontctl, ["--db", str(db_path), "scan", "--reparse", str(tmp_path / "fonts")])

    assert "reparsed" not in plain.output
    assert result.exit_code == 0, result.output
    assert "reparsed 1" in result.output


def test_reparse_adds_umbrella_tag_to_library_scanned_before_it(tmp_path):
    build_test_font(tmp_path / "Times.ttf", family="Times", style="Regular", family_class=2 * 256)
    conn = _conn()
    ingest_directory(conn, tmp_path)
    face_id = _face_of(conn, "Times.ttf")
    remove_tag(conn, face_id, "serif")  # as tagged by a version without umbrella tags

    ingest_directory(conn, tmp_path)
    assert "serif" not in list_tags_for_face(conn, face_id)  # unchanged file: left alone

    ingest_directory(conn, tmp_path, reparse=True)
    assert "serif" in list_tags_for_face(conn, face_id)
