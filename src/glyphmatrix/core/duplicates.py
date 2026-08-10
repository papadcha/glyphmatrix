from __future__ import annotations

import sqlite3


def find_duplicates(conn: sqlite3.Connection) -> list[dict]:
    """Group font_files by content_hash — catches byte-identical files only.
    Distinct from core/compare.py, which diffs different *versions* of the
    same face (different content_hash, possibly different/changed glyphs)."""
    rows = conn.execute(
        """
        SELECT font_files.content_hash, font_files.path,
               families.name AS family, font_faces.style
        FROM font_files
        JOIN font_faces ON font_faces.id = font_files.font_face_id
        JOIN families ON families.id = font_faces.family_id
        ORDER BY font_files.content_hash, font_files.path
        """
    ).fetchall()

    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["content_hash"], []).append(dict(row))

    return [
        {"content_hash": content_hash, "files": files}
        for content_hash, files in groups.items()
        if len(files) > 1
    ]
