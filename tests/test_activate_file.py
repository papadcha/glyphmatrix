from __future__ import annotations

import platform
from datetime import datetime, timedelta, timezone

from glyphmatrix.core.activation_service import activate_family, activate_file, deactivate_file
from glyphmatrix.core.database import connect, init_schema
from glyphmatrix.core.ingest import ingest_directory

from .fakes import FakeActivationProvider
from .fontbuilder import build_test_font


def _conn():
    conn = connect(":memory:")
    init_schema(conn)
    return conn


def _active_paths(conn):
    return [
        row["path"]
        for row in conn.execute(
            "SELECT font_files.path FROM font_files JOIN activations "
            "ON activations.font_file_id = font_files.id WHERE activations.state = 'active'"
        )
    ]


def test_activate_file_activates_a_specific_file(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    build_test_font(tmp_path / "Arial-Bold.ttf", family="Arial", style="Bold")
    conn = _conn()
    ingest_directory(conn, tmp_path)
    path = str(tmp_path / "Arial-Regular.ttf")
    provider = FakeActivationProvider()

    result = activate_file(conn, path, provider=provider)

    assert result.processed == [path]
    assert result.errors == []
    assert provider.activated == [path]
    assert _active_paths(conn) == [path]


def test_activate_file_unknown_path_returns_error():
    conn = _conn()

    result = activate_file(conn, "/nonexistent/font.ttf", provider=FakeActivationProvider())

    assert result.processed == []
    assert len(result.errors) == 1
    assert "not found in library" in result.errors[0][1]


def test_activate_file_is_idempotent_against_the_provider(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)
    path = str(tmp_path / "Arial-Regular.ttf")
    provider = FakeActivationProvider()

    activate_file(conn, path, provider=provider)
    result = activate_file(conn, path, provider=provider)

    assert len(provider.activated) == 1  # OS not re-touched
    assert result.processed == [path]
    assert result.errors == []


def test_activate_file_refuses_disabled_file(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)
    path = str(tmp_path / "Arial-Regular.ttf")
    provider = FakeActivationProvider()
    conn.execute(
        "INSERT INTO activations (font_file_id, platform, state, deactivated_at) "
        "SELECT id, ?, 'disabled', datetime('now') FROM font_files WHERE path = ?",
        (platform.system().lower(), path),
    )
    conn.commit()

    result = activate_file(conn, path, provider=provider)

    assert result.processed == []
    assert "disabled" in result.errors[0][1]
    assert provider.activated == []


def test_activate_file_resolves_conflict_by_swapping(tmp_path):
    """The key use case: two files claim the same face. activate_family picks
    the first (lowest id) and refuses the second. activate_file lets the user
    explicitly promote the second by deactivating the first for them."""
    folder_a = tmp_path / "a"
    folder_a.mkdir()
    folder_b = tmp_path / "b"
    folder_b.mkdir()
    file_a = str(build_test_font(
        folder_a / "Arial-Regular.ttf", family="Arial", style="Regular", a_glyph_size=700
    ))
    file_b = str(build_test_font(
        folder_b / "Arial-Regular.ttf", family="Arial", style="Regular", a_glyph_size=500
    ))
    conn = _conn()
    ingest_directory(conn, tmp_path)
    provider = FakeActivationProvider()
    activate_family(conn, "Arial", provider=provider)
    # After activate_family, exactly one of the two is active (the winner)
    assert len(_active_paths(conn)) == 1
    winner = _active_paths(conn)[0]
    loser = file_b if winner == file_a else file_a

    # activate_file on the loser should swap: deactivate winner, activate loser
    result = activate_file(conn, loser, provider=provider)

    assert result.processed == [loser]
    assert result.errors == []
    assert _active_paths(conn) == [loser]
    assert winner not in _active_paths(conn)
    assert loser in provider.activated
    assert winner in provider.deactivated


def test_activate_file_sets_expiry(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)
    path = str(tmp_path / "Arial-Regular.ttf")
    before = datetime.now(timezone.utc)

    activate_file(conn, path, provider=FakeActivationProvider(), duration="30m")

    row = conn.execute("SELECT expires_at FROM activations").fetchone()
    expires_at = datetime.fromisoformat(row["expires_at"])
    assert before + timedelta(minutes=29) < expires_at < before + timedelta(minutes=31)


def test_deactivate_file_deactivates_active_file(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)
    path = str(tmp_path / "Arial-Regular.ttf")
    provider = FakeActivationProvider()
    activate_file(conn, path, provider=provider)

    result = deactivate_file(conn, path, provider=provider)

    assert result.processed == [path]
    assert result.errors == []
    assert provider.deactivated == [path]
    state = conn.execute("SELECT state FROM activations").fetchone()["state"]
    assert state == "installed"


def test_deactivate_file_is_noop_when_not_active(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    conn = _conn()
    ingest_directory(conn, tmp_path)
    path = str(tmp_path / "Arial-Regular.ttf")
    provider = FakeActivationProvider()

    result = deactivate_file(conn, path, provider=provider)

    assert result.processed == [path]
    assert result.errors == []
    assert provider.deactivated == []


def test_deactivate_file_unknown_path_returns_error():
    conn = _conn()

    result = deactivate_file(conn, "/nonexistent/font.ttf", provider=FakeActivationProvider())

    assert result.processed == []
    assert len(result.errors) == 1
    assert "not found in library" in result.errors[0][1]
