from datetime import datetime, timedelta, timezone

import pytest

from glyphmatrix.core.activation_service import (
    activate_family,
    activate_set,
    deactivate_expired,
    deactivate_family,
    deactivate_set,
    disable_family,
    enable_family,
    parse_duration,
    restore_active_state,
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


def test_disable_family_marks_state_disabled(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)

    result = disable_family(conn, "Arial", provider=FakeActivationProvider())

    assert len(result.processed) == 1
    assert result.errors == []
    states = conn.execute("SELECT state FROM activations").fetchall()
    assert [s["state"] for s in states] == ["disabled"]


def test_disable_family_deactivates_first_if_currently_active(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)
    provider = FakeActivationProvider()
    activate_family(conn, "Arial", provider=provider)

    disable_family(conn, "Arial", provider=provider)

    assert provider.deactivated == provider.activated  # was turned off before disabling
    states = conn.execute("SELECT state FROM activations").fetchall()
    assert [s["state"] for s in states] == ["disabled"]


def test_activate_family_refuses_a_disabled_font(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)
    provider = FakeActivationProvider()
    disable_family(conn, "Arial", provider=provider)

    result = activate_family(conn, "Arial", provider=provider)

    assert result.processed == []
    assert len(result.errors) == 1
    assert "disabled" in result.errors[0][1]
    assert provider.activated == []  # never even reached the OS call
    states = conn.execute("SELECT state FROM activations").fetchall()
    assert [s["state"] for s in states] == ["disabled"]  # unchanged


def test_enable_family_clears_disabled_state(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)
    provider = FakeActivationProvider()
    disable_family(conn, "Arial", provider=provider)

    enable_family(conn, "Arial")
    result = activate_family(conn, "Arial", provider=provider)

    assert len(result.processed) == 1
    assert result.errors == []
    assert provider.activated == [str(tmp_path / "Arial-Regular.ttf")]


def test_enable_family_is_noop_when_not_disabled(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)

    result = enable_family(conn, "Arial")

    assert len(result.processed) == 1
    row = conn.execute("SELECT state FROM activations").fetchone()
    assert row is None  # never touched, since it was never disabled


def test_parse_duration_valid_formats():
    assert parse_duration("30m") == timedelta(minutes=30)
    assert parse_duration("2h") == timedelta(hours=2)
    assert parse_duration("1d") == timedelta(days=1)
    assert parse_duration("90s") == timedelta(seconds=90)
    assert parse_duration(" 2H ") == timedelta(hours=2)  # whitespace/case tolerant


@pytest.mark.parametrize("bad", ["", "30", "m", "30 m", "1.5h", "-5m", "30x"])
def test_parse_duration_rejects_invalid_formats(bad):
    with pytest.raises(ValueError):
        parse_duration(bad)


def test_activate_family_with_duration_sets_expiry(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)
    before = datetime.now(timezone.utc)

    activate_family(conn, "Arial", provider=FakeActivationProvider(), duration="30m")

    row = conn.execute("SELECT expires_at FROM activations").fetchone()
    expires_at = datetime.fromisoformat(row["expires_at"])
    assert before + timedelta(minutes=29) < expires_at < before + timedelta(minutes=31)


def test_activate_family_without_duration_leaves_expiry_null(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)

    activate_family(conn, "Arial", provider=FakeActivationProvider())

    row = conn.execute("SELECT expires_at FROM activations").fetchone()
    assert row["expires_at"] is None


def test_activate_family_invalid_duration_raises(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)

    with pytest.raises(ValueError):
        activate_family(conn, "Arial", provider=FakeActivationProvider(), duration="not-a-duration")


def test_reactivating_an_active_font_refreshes_expiry_without_reprovider_call(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)
    provider = FakeActivationProvider()
    activate_family(conn, "Arial", provider=provider, duration="30m")

    activate_family(conn, "Arial", provider=provider, duration="2h")

    assert len(provider.activated) == 1  # OS not re-touched, reference-count-safe
    row = conn.execute("SELECT expires_at FROM activations").fetchone()
    expires_at = datetime.fromisoformat(row["expires_at"])
    assert expires_at > datetime.now(timezone.utc) + timedelta(minutes=90)


def test_deactivate_expired_deactivates_only_past_expiry(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    build_test_font(tmp_path / "Verdana-Regular.ttf", family="Verdana", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)
    provider = FakeActivationProvider()
    activate_family(conn, "Arial", provider=provider, duration="30m")
    activate_family(conn, "Verdana", provider=provider, duration="30m")

    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    conn.execute(
        "UPDATE activations SET expires_at = ? WHERE font_file_id = "
        "(SELECT id FROM font_files WHERE path LIKE '%Arial%')",
        (past,),
    )
    conn.commit()

    result = deactivate_expired(conn, provider=provider)

    assert len(result.processed) == 1
    assert "Arial" in result.processed[0]
    arial_state = conn.execute(
        "SELECT activations.state FROM activations JOIN font_files "
        "ON font_files.id = activations.font_file_id WHERE font_files.path LIKE '%Arial%'"
    ).fetchone()["state"]
    verdana_state = conn.execute(
        "SELECT activations.state FROM activations JOIN font_files "
        "ON font_files.id = activations.font_file_id WHERE font_files.path LIKE '%Verdana%'"
    ).fetchone()["state"]
    assert arial_state == "installed"
    assert verdana_state == "active"  # not expired yet, left alone


def test_deactivate_expired_ignores_permanent_activations(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)
    provider = FakeActivationProvider()
    activate_family(conn, "Arial", provider=provider)  # no duration => permanent

    result = deactivate_expired(conn, provider=provider)

    assert result.processed == []
    state = conn.execute("SELECT state FROM activations").fetchone()["state"]
    assert state == "active"


def test_restore_active_state_reapplies_even_though_db_already_says_active(tmp_path):
    """This is the whole point of the function: on Windows, a reboot wipes
    AddFontResourceEx registration but not our DB, so the normal
    "already active, skip the OS call" idempotency check would wrongly
    leave the font un-registered after login. restore_active_state must
    call the provider regardless of what the DB already says."""
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)
    provider = FakeActivationProvider()
    activate_family(conn, "Arial", provider=provider)
    assert len(provider.activated) == 1

    result = restore_active_state(conn, provider=provider)

    assert len(provider.activated) == 2  # called again, unlike activate_family's skip
    assert len(result.processed) == 1


def test_restore_active_state_ignores_non_active_fonts(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    build_test_font(tmp_path / "Verdana-Regular.ttf", family="Verdana", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)
    provider = FakeActivationProvider()
    activate_family(conn, "Arial", provider=provider)
    disable_family(conn, "Verdana", provider=provider)  # never activated, now disabled

    result = restore_active_state(conn, provider=provider)

    assert len(result.processed) == 1
    assert "Arial" in result.processed[0]


def test_restore_active_state_never_activated_is_a_noop(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)
    provider = FakeActivationProvider()

    result = restore_active_state(conn, provider=provider)

    assert result.processed == []
    assert provider.activated == []


def test_restore_active_state_preserves_expiry(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)
    provider = FakeActivationProvider()
    activate_family(conn, "Arial", provider=provider, duration="2h")
    original_expiry = conn.execute("SELECT expires_at FROM activations").fetchone()["expires_at"]

    restore_active_state(conn, provider=provider)

    restored_expiry = conn.execute("SELECT expires_at FROM activations").fetchone()["expires_at"]
    assert restored_expiry == original_expiry


def test_restore_active_state_collects_per_file_errors(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)
    path = str(tmp_path / "Arial-Regular.ttf")
    provider = FakeActivationProvider()
    activate_family(conn, "Arial", provider=provider)

    failing_provider = FakeActivationProvider(fail_paths=frozenset({path}))
    result = restore_active_state(conn, provider=failing_provider)

    assert result.processed == []
    assert len(result.errors) == 1
    assert result.errors[0][0] == path
