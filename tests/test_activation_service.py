from glyphmatrix.core.activation_service import (
    activate_family,
    activate_set,
    deactivate_family,
    deactivate_set,
)
from glyphmatrix.core.collections import add_face_to_collection, create_collection
from glyphmatrix.core.database import connect, init_schema
from glyphmatrix.core.ingest import ingest_directory
from glyphmatrix.core.query import find_face_id

from .fakes import FakeActivationProvider
from .fontbuilder import build_test_font


def _conn():
    conn = connect(":memory:")
    init_schema(conn)
    return conn


def test_activate_family_processes_all_files_and_records_state(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    build_test_font(tmp_path / "Arial-Bold.ttf", family="Arial", style="Bold")
    conn = _conn()
    ingest_directory(conn, tmp_path)
    provider = FakeActivationProvider()

    result = activate_family(conn, "Arial", provider=provider)

    assert len(result.processed) == 2
    assert result.errors == []
    assert set(provider.activated) == set(result.processed)

    states = conn.execute("SELECT state FROM activations").fetchall()
    assert [s["state"] for s in states] == ["active", "active"]


def test_activate_family_is_case_insensitive(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)

    result = activate_family(conn, "arial", provider=FakeActivationProvider())

    assert len(result.processed) == 1


def test_activate_family_unknown_family_returns_empty_result():
    conn = _conn()

    result = activate_family(conn, "Nonexistent", provider=FakeActivationProvider())

    assert result.processed == []
    assert result.errors == []


def test_activate_family_collects_per_file_errors(tmp_path):
    good = tmp_path / "Arial-Regular.ttf"
    bad = tmp_path / "Arial-Bold.ttf"
    build_test_font(good, family="Arial", style="Regular")
    build_test_font(bad, family="Arial", style="Bold")
    conn = _conn()
    ingest_directory(conn, tmp_path)
    provider = FakeActivationProvider(fail_paths=frozenset({str(bad)}))

    result = activate_family(conn, "Arial", provider=provider)

    assert result.processed == [str(good)]
    assert len(result.errors) == 1
    assert result.errors[0][0] == str(bad)
    assert "boom" in result.errors[0][1]

    row = conn.execute(
        "SELECT activations.state FROM activations "
        "JOIN font_files ON font_files.id = activations.font_file_id "
        "WHERE font_files.path = ?",
        (str(bad),),
    ).fetchone()
    assert row is None  # a failed activate must not be recorded as active


def test_deactivate_family_updates_state_to_installed(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)
    provider = FakeActivationProvider()
    activate_family(conn, "Arial", provider=provider)

    result = deactivate_family(conn, "Arial", provider=provider)

    assert len(result.processed) == 1
    states = conn.execute("SELECT state FROM activations").fetchall()
    assert [s["state"] for s in states] == ["installed"]


def test_activate_family_is_idempotent_against_the_provider(tmp_path):
    """Regression guard: Windows' AddFontResourceEx is reference-counted, so
    calling provider.activate() twice for an already-active file would need
    two matching deactivate() calls to fully undo. The service must skip the
    provider call (not just the DB write) when already active per our records."""
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)
    provider = FakeActivationProvider()

    activate_family(conn, "Arial", provider=provider)
    result = activate_family(conn, "Arial", provider=provider)

    assert len(provider.activated) == 1  # provider.activate() called only once
    assert len(result.processed) == 1  # still reported as processed/active


def test_deactivate_family_is_idempotent_against_the_provider(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)
    provider = FakeActivationProvider()

    result = deactivate_family(conn, "Arial", provider=provider)  # never activated

    assert provider.deactivated == []  # nothing to undo, provider not called
    assert len(result.processed) == 1


def _build_set(conn, tmp_path, set_name="Body Text"):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    build_test_font(tmp_path / "Verdana-Regular.ttf", family="Verdana", style="Regular")
    ingest_directory(conn, tmp_path)
    collection_id = create_collection(conn, set_name)
    for family, style in [("Arial", "Regular"), ("Verdana", "Regular")]:
        add_face_to_collection(conn, collection_id, find_face_id(conn, family, style))
    return collection_id


def test_activate_set_activates_every_face_in_the_collection(tmp_path):
    conn = _conn()
    _build_set(conn, tmp_path)
    provider = FakeActivationProvider()

    result = activate_set(conn, "Body Text", provider=provider)

    assert result is not None
    assert len(result.processed) == 2
    assert result.label == "Body Text"
    states = conn.execute("SELECT state FROM activations").fetchall()
    assert [s["state"] for s in states] == ["active", "active"]


def test_activate_set_is_case_insensitive(tmp_path):
    conn = _conn()
    _build_set(conn, tmp_path)

    result = activate_set(conn, "body text", provider=FakeActivationProvider())

    assert result is not None
    assert len(result.processed) == 2


def test_activate_set_unknown_set_returns_none(tmp_path):
    conn = _conn()

    assert activate_set(conn, "Nonexistent", provider=FakeActivationProvider()) is None


def test_activate_set_only_touches_its_own_faces(tmp_path):
    conn = _conn()
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    build_test_font(tmp_path / "Verdana-Regular.ttf", family="Verdana", style="Regular")
    ingest_directory(conn, tmp_path)
    collection_id = create_collection(conn, "Just Arial")
    add_face_to_collection(conn, collection_id, find_face_id(conn, "Arial", "Regular"))

    result = activate_set(conn, "Just Arial", provider=FakeActivationProvider())

    assert result is not None
    assert len(result.processed) == 1
    assert "Arial" in result.processed[0]


def test_deactivate_set_reverts_every_face(tmp_path):
    conn = _conn()
    _build_set(conn, tmp_path)
    provider = FakeActivationProvider()
    activate_set(conn, "Body Text", provider=provider)

    result = deactivate_set(conn, "Body Text", provider=provider)

    assert result is not None
    assert len(result.processed) == 2
    states = conn.execute("SELECT state FROM activations").fetchall()
    assert [s["state"] for s in states] == ["installed", "installed"]


def test_deactivate_set_unknown_set_returns_none(tmp_path):
    conn = _conn()

    assert deactivate_set(conn, "Nonexistent", provider=FakeActivationProvider()) is None


def test_activate_set_is_idempotent_against_the_provider(tmp_path):
    conn = _conn()
    _build_set(conn, tmp_path)
    provider = FakeActivationProvider()

    activate_set(conn, "Body Text", provider=provider)
    activate_set(conn, "Body Text", provider=provider)

    assert len(provider.activated) == 2  # not 4 — second call was a no-op per file
