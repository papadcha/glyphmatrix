from __future__ import annotations

import sqlite3
from pathlib import Path


def backup_database(conn: sqlite3.Connection, dest_path: str | Path) -> Path:
    """Snapshot the live database to dest_path using SQLite's online backup
    API — safe to run against an in-use connection, unlike a raw file copy."""
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(dest_path) as dest_conn:
        conn.backup(dest_conn)
    return dest_path


def restore_database(source_path: str | Path, dest_path: str | Path) -> Path:
    """Overwrite dest_path with the full contents of source_path. dest_path
    need not exist yet; if it does, its prior contents are discarded."""
    source_path = Path(source_path)
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source_path) as source_conn, sqlite3.connect(dest_path) as dest_conn:
        source_conn.backup(dest_conn)
    return dest_path
