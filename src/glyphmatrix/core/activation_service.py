from __future__ import annotations

import platform as platform_module
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone

from glyphmatrix.core.activation import ActivationProvider
from glyphmatrix.platforms.linux import LinuxActivationProvider
from glyphmatrix.platforms.macos import MacOSActivationProvider
from glyphmatrix.platforms.windows import WindowsActivationProvider


@dataclass
class ActivationResult:
    family: str
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


def activate_family(
    conn: sqlite3.Connection, family_name: str, provider: ActivationProvider | None = None
) -> ActivationResult:
    provider = provider or get_provider()
    platform_name = platform_module.system().lower()
    now = datetime.now(timezone.utc).isoformat()
    result = ActivationResult(family=family_name)

    for row in _family_file_rows(conn, family_name):
        try:
            provider.activate(row["path"])
            _mark_active(conn, row["id"], platform_name, now)
            result.processed.append(row["path"])
        except Exception as exc:
            result.errors.append((row["path"], str(exc)))

    conn.commit()
    return result


def deactivate_family(
    conn: sqlite3.Connection, family_name: str, provider: ActivationProvider | None = None
) -> ActivationResult:
    provider = provider or get_provider()
    platform_name = platform_module.system().lower()
    now = datetime.now(timezone.utc).isoformat()
    result = ActivationResult(family=family_name)

    for row in _family_file_rows(conn, family_name):
        try:
            provider.deactivate(row["path"])
            _mark_installed(conn, row["id"], platform_name, now)
            result.processed.append(row["path"])
        except Exception as exc:
            result.errors.append((row["path"], str(exc)))

    conn.commit()
    return result
