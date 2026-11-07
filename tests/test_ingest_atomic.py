from glyphmatrix.core import ingest as ingest_mod
from glyphmatrix.core.database import connect, init_schema
from glyphmatrix.core.ingest import ingest_directory

from .fontbuilder import build_test_font


def _library_state(conn):
    families = sorted(r[0] for r in conn.execute("SELECT name FROM families"))
    styles = sorted(r[0] for r in conn.execute("SELECT style FROM font_faces"))
    return families, styles


def test_failed_ingest_of_a_changed_file_leaves_the_library_as_it_was(tmp_path, monkeypatch):
    root = tmp_path / "fonts"
    root.mkdir()
    path = root / "f.ttf"
    build_test_font(path, family="Alpha", style="Regular")
    conn = connect(tmp_path / "lib.db")
    init_schema(conn)
    ingest_directory(conn, root)
    build_test_font(path, family="Beta", style="Bold", extra_glyph=True)   # same path, new content

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(ingest_mod, "ingest_font_file", boom)
    run = ingest_directory(conn, root)
    monkeypatch.undo()

    assert run.errors == 1
    assert _library_state(conn) == (["Alpha"], ["Regular"])        # nothing half-applied
    conn.commit()
    assert _library_state(conn) == (["Alpha"], ["Regular"])        # and nothing committed later

    healed = ingest_directory(conn, root)                          # the next scan picks the change up
    assert healed.errors == 0
    assert _library_state(conn) == (["Beta"], ["Bold"])


def test_one_failing_file_does_not_undo_the_others(tmp_path, monkeypatch):
    root = tmp_path / "fonts"
    root.mkdir()
    build_test_font(root / "a.ttf", family="Alpha", style="Regular")
    build_test_font(root / "b.ttf", family="Bravo", style="Regular", extra_glyph=True)
    conn = connect(tmp_path / "lib.db")
    init_schema(conn)
    real = ingest_mod.ingest_font_file

    def fail_for_bravo(conn_, face_id, parsed, *args, **kwargs):
        if parsed.family_name == "Bravo":
            raise RuntimeError("boom")
        return real(conn_, face_id, parsed, *args, **kwargs)

    monkeypatch.setattr(ingest_mod, "ingest_font_file", fail_for_bravo)
    run = ingest_directory(conn, root)

    assert (run.files_added, run.errors) == (1, 1)
    assert _library_state(conn)[0] == ["Alpha"]
