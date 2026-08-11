from __future__ import annotations

import platform as platform_module
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone

from glyphmatrix.core.activation import ActivationProvider
from glyphmatrix.core.collections import find_collection_id, list_collection_face_ids
from glyphmatrix.platforms.linux import LinuxActivationProvider
from glyphmatrix.platforms.macos import MacOSActivationProvider
from glyphmatrix.platforms.windows import WindowsActivationProvider


@dataclass
class ActivationResult:
    label: str
    processed: list[str] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)


def get_provider() -> ActivationProvider:
    system = platform_module.system()
    if system == "Darwin":
        return MacOSActivationProvider()
    if system == "Windows":
        return WindowsActivationProvider()
    if system == "Linux":
        return LinuxActivationProvider()
    raise RuntimeError(f"unsupported platform: {system}")


def _family_file_rows(conn: sqlite3.Connection, family_name: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT font_files.id, font_files.path
        FROM font_files
        JOIN font_faces ON font_faces.id = font_files.font_face_id
        JOIN families ON families.id = font_faces.family_id
        WHERE families.name = ? COLLATE NOCASE
        """,
        (family_name,),
    ).fetchall()


def _face_file_rows(conn: sqlite3.Connection, font_face_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, path FROM font_files WHERE font_face_id = ?", (font_face_id,)
    ).fetchall()


def _set_file_rows(conn: sqlite3.Connection, collection_id: int) -> list[sqlite3.Row]:
    rows: list[sqlite3.Row] = []
    for face_id in list_collection_face_ids(conn, collection_id):
        rows.extend(_face_file_rows(conn, face_id))
    return rows


def _mark_active(conn: sqlite3.Connection, font_file_id: int, platform_name: str, now: str) -> None:
    existing = conn.execute(
        "SELECT id FROM activations WHERE font_file_id = ? AND platform = ?",
        (font_file_id, platform_name),
    ).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO activations (font_file_id, platform, state, activated_at) "
            "VALUES (?, ?, 'active', ?)",
            (font_file_id, platform_name, now),
        )
    else:
        conn.execute(
            "UPDATE activations SET state = 'active', activated_at = ? WHERE id = ?",
            (now, existing["id"]),
        )


def _mark_installed(conn: sqlite3.Connection, font_file_id: int, platform_name: str, now: str) -> None:
    existing = conn.execute(
        "SELECT id FROM activations WHERE font_file_id = ? AND platform = ?",
        (font_file_id, platform_name),
    ).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO activations (font_file_id, platform, state, deactivated_at) "
            "VALUES (?, ?, 'installed', ?)",
            (font_file_id, platform_name, now),
        )
    else:
        conn.execute(
            "UPDATE activations SET state = 'installed', deactivated_at = ? WHERE id = ?",
            (now, existing["id"]),
        )


def _current_state(conn: sqlite3.Connection, font_file_id: int, platform_name: str) -> str | None:
    row = conn.execute(
        "SELECT state FROM activations WHERE font_file_id = ? AND platform = ?",
        (font_file_id, platform_name),
    ).fetchone()
    return row["state"] if row is not None else None


def _apply_activation(
    conn: sqlite3.Connection,
    file_rows: list[sqlite3.Row],
    provider: ActivationProvider,
    platform_name: str,
    now: str,
    activating: bool,
) -> tuple[list[str], list[tuple[str, str]]]:
    """Shared per-file loop behind activate_family/activate_set and their
    deactivate counterparts. Skips the OS call — not just the DB write —
    whenever our own records already say the file is in the target state:
    not just an optimization, since Windows' AddFontResourceEx is
    reference-counted and calling it twice needs two matching Remove
    calls to fully undo. The activations table is the one cross-invocation
    source of truth for "did we already do this.\""""
    processed: list[str] = []
    errors: list[tuple[str, str]] = []

    for row in file_rows:
        already_there = _current_state(conn, row["id"], platform_name) == "active"
        if activating == already_there:
            processed.append(row["path"])
            continue
        try:
            if activating:
                provider.activate(row["path"])
                _mark_active(conn, row["id"], platform_name, now)
            else:
                provider.deactivate(row["path"])
                _mark_installed(conn, row["id"], platform_name, now)
            processed.append(row["path"])
        except Exception as exc:
            errors.append((row["path"], str(exc)))

    return processed, errors


def activate_family(
    conn: sqlite3.Connection, family_name: str, provider: ActivationProvider | None = None
) -> ActivationResult:
    provider = provider or get_provider()
    platform_name = platform_module.system().lower()
    now = datetime.now(timezone.utc).isoformat()

    processed, errors = _apply_activation(
        conn, _family_file_rows(conn, family_name), provider, platform_name, now, activating=True
    )
    conn.commit()
    return ActivationResult(label=family_name, processed=processed, errors=errors)


def deactivate_family(
    conn: sqlite3.Connection, family_name: str, provider: ActivationProvider | None = None
) -> ActivationResult:
    provider = provider or get_provider()
    platform_name = platform_module.system().lower()
    now = datetime.now(timezone.utc).isoformat()

    processed, errors = _apply_activation(
        conn, _family_file_rows(conn, family_name), provider, platform_name, now, activating=False
    )
    conn.commit()
    return ActivationResult(label=family_name, processed=processed, errors=errors)


def activate_set(
    conn: sqlite3.Connection, set_name: str, provider: ActivationProvider | None = None
) -> ActivationResult | None:
    """None if no collection by that name exists — distinct from a valid,
    empty result, so the CLI can tell "no such set" from "set has no fonts.\""""
    collection_id = find_collection_id(conn, set_name)
    if collection_id is None:
        return None

    provider = provider or get_provider()
    platform_name = platform_module.system().lower()
    now = datetime.now(timezone.utc).isoformat()

    processed, errors = _apply_activation(
        conn, _set_file_rows(conn, collection_id), provider, platform_name, now, activating=True
    )
    conn.commit()
    return ActivationResult(label=set_name, processed=processed, errors=errors)


def deactivate_set(
    conn: sqlite3.Connection, set_name: str, provider: ActivationProvider | None = None
) -> ActivationResult | None:
    collection_id = find_collection_id(conn, set_name)
    if collection_id is None:
        return None

    provider = provider or get_provider()
    platform_name = platform_module.system().lower()
    now = datetime.now(timezone.utc).isoformat()

    processed, errors = _apply_activation(
        conn, _set_file_rows(conn, collection_id), provider, platform_name, now, activating=False
    )
    conn.commit()
    return ActivationResult(label=set_name, processed=processed, errors=errors)
