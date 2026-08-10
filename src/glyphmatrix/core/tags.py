from __future__ import annotations

import sqlite3


def add_tags(conn: sqlite3.Connection, font_face_id: int, tag_names: list[str]) -> list[str]:
    """Tag a face with each name. Returns the tags actually applied — ones
    already on the face are skipped rather than duplicated."""
    applied = []
    for raw_name in tag_names:
        name = raw_name.strip()
        if not name:
            continue

        tag_row = conn.execute(
            "SELECT id FROM tags WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        if tag_row is None:
            cur = conn.execute("INSERT INTO tags (name) VALUES (?)", (name,))
            tag_id = cur.lastrowid
        else:
            tag_id = tag_row["id"]

        existing = conn.execute(
            "SELECT 1 FROM font_tags WHERE font_face_id = ? AND tag_id = ?",
            (font_face_id, tag_id),
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO font_tags (font_face_id, tag_id) VALUES (?, ?)",
                (font_face_id, tag_id),
            )
            applied.append(name)

    conn.commit()
    return applied


def remove_tag(conn: sqlite3.Connection, font_face_id: int, tag_name: str) -> bool:
    tag_row = conn.execute(
        "SELECT id FROM tags WHERE name = ? COLLATE NOCASE", (tag_name,)
    ).fetchone()
    if tag_row is None:
        return False
    cur = conn.execute(
        "DELETE FROM font_tags WHERE font_face_id = ? AND tag_id = ?",
        (font_face_id, tag_row["id"]),
    )
    conn.commit()
    return cur.rowcount > 0


def list_tags_for_face(conn: sqlite3.Connection, font_face_id: int) -> list[str]:
    rows = conn.execute(
        """
        SELECT tags.name FROM tags
        JOIN font_tags ON font_tags.tag_id = tags.id
        WHERE font_tags.font_face_id = ?
        ORDER BY tags.name COLLATE NOCASE
        """,
        (font_face_id,),
    ).fetchall()
    return [row["name"] for row in rows]


def list_all_tags(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT tags.name, COUNT(font_tags.font_face_id) AS face_count
        FROM tags
        LEFT JOIN font_tags ON font_tags.tag_id = tags.id
        GROUP BY tags.id
        ORDER BY tags.name COLLATE NOCASE
        """
    ).fetchall()
    return [dict(row) for row in rows]


def find_faces_by_tag(conn: sqlite3.Connection, tag_name: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT families.name AS family, font_faces.style
        FROM font_tags
        JOIN tags ON tags.id = font_tags.tag_id
        JOIN font_faces ON font_faces.id = font_tags.font_face_id
        JOIN families ON families.id = font_faces.family_id
        WHERE tags.name = ? COLLATE NOCASE
        ORDER BY families.name COLLATE NOCASE, font_faces.style
        """,
        (tag_name,),
    ).fetchall()
    return [dict(row) for row in rows]
