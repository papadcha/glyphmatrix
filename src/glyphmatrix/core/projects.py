from __future__ import annotations

import sqlite3
from pathlib import Path

from glyphmatrix.core.collections import find_collection_id


def set_project(conn: sqlite3.Connection, directory: str, collection_name: str) -> None:
    """Associate a directory with a collection. Replaces any existing mapping."""
    collection_id = find_collection_id(conn, collection_name)
    if collection_id is None:
        raise ValueError(f"no such collection: {collection_name!r}")
    path = str(Path(directory).resolve())
    conn.execute(
        """
        INSERT INTO projects (path, collection_id) VALUES (?, ?)
        ON CONFLICT(path) DO UPDATE SET collection_id = excluded.collection_id
        """,
        (path, collection_id),
    )
    conn.commit()


def unset_project(conn: sqlite3.Connection, directory: str) -> bool:
    """Remove the mapping for a directory. Returns True if a mapping existed."""
    path = str(Path(directory).resolve())
    cur = conn.execute("DELETE FROM projects WHERE path = ?", (path,))
    conn.commit()
    return cur.rowcount > 0


def list_projects(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT projects.path, collections.name AS collection
        FROM projects
        JOIN collections ON collections.id = projects.collection_id
        ORDER BY projects.path
        """
    ).fetchall()
    return [dict(r) for r in rows]


def find_project_collection(conn: sqlite3.Connection, directory: str) -> str | None:
    """Return the collection name for the nearest ancestor directory that has a
    project mapping, or None. Walks up from `directory` to the filesystem root."""
    current = Path(directory).resolve()
    while True:
        row = conn.execute(
            """
            SELECT collections.name FROM projects
            JOIN collections ON collections.id = projects.collection_id
            WHERE projects.path = ?
            """,
            (str(current),),
        ).fetchone()
        if row is not None:
            return row["name"]
        parent = current.parent
        if parent == current:
            return None
        current = parent
