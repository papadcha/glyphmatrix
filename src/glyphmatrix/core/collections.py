from __future__ import annotations

import sqlite3

# Favorites is sugar over collections, not a separate concept: a reserved
# collection name that `fontctl favorite`/`unfavorite`/`favorites` manage
# automatically. `fontctl collection show Favorites` works on the exact
# same data.
FAVORITES_COLLECTION_NAME = "Favorites"


def find_collection_id(conn: sqlite3.Connection, name: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM collections WHERE name = ? COLLATE NOCASE ORDER BY id", (name,)
    ).fetchone()
    return row["id"] if row is not None else None


def create_collection(conn: sqlite3.Connection, name: str, parent_name: str | None = None) -> int:
    if find_collection_id(conn, name) is not None:
        raise ValueError(f"collection already exists: {name}")

    parent_id = None
    if parent_name is not None:
        parent_id = find_collection_id(conn, parent_name)
        if parent_id is None:
            raise ValueError(f"no such collection: {parent_name}")

    cur = conn.execute("INSERT INTO collections (name, parent_id) VALUES (?, ?)", (name, parent_id))
    conn.commit()
    return cur.lastrowid


def add_face_to_collection(conn: sqlite3.Connection, collection_id: int, font_face_id: int) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO collection_faces (collection_id, font_face_id) VALUES (?, ?)",
        (collection_id, font_face_id),
    )
    conn.commit()


def remove_face_from_collection(
    conn: sqlite3.Connection, collection_id: int, font_face_id: int
) -> bool:
    cur = conn.execute(
        "DELETE FROM collection_faces WHERE collection_id = ? AND font_face_id = ?",
        (collection_id, font_face_id),
    )
    conn.commit()
    return cur.rowcount > 0


def list_collections(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT collections.name, parent.name AS parent_name,
               COUNT(collection_faces.font_face_id) AS face_count
        FROM collections
        LEFT JOIN collections AS parent ON parent.id = collections.parent_id
        LEFT JOIN collection_faces ON collection_faces.collection_id = collections.id
        GROUP BY collections.id
        ORDER BY collections.name COLLATE NOCASE
        """
    ).fetchall()
    return [dict(row) for row in rows]


def get_or_create_favorites_collection(conn: sqlite3.Connection) -> int:
    collection_id = find_collection_id(conn, FAVORITES_COLLECTION_NAME)
    if collection_id is not None:
        return collection_id
    return create_collection(conn, FAVORITES_COLLECTION_NAME)


def list_collection_face_ids(conn: sqlite3.Connection, collection_id: int) -> list[int]:
    rows = conn.execute(
        "SELECT font_face_id FROM collection_faces WHERE collection_id = ?", (collection_id,)
    ).fetchall()
    return [row["font_face_id"] for row in rows]


def list_collection_faces(conn: sqlite3.Connection, collection_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT families.name AS family, font_faces.style
        FROM collection_faces
        JOIN font_faces ON font_faces.id = collection_faces.font_face_id
        JOIN families ON families.id = font_faces.family_id
        WHERE collection_faces.collection_id = ?
        ORDER BY families.name COLLATE NOCASE, font_faces.style
        """,
        (collection_id,),
    ).fetchall()
    return [dict(row) for row in rows]
