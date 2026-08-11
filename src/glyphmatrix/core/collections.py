from __future__ import annotations

import sqlite3

from glyphmatrix.core.smart_collections import evaluate_smart_query

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


def _is_smart(conn: sqlite3.Connection, collection_id: int) -> tuple[bool, str | None]:
    row = conn.execute(
        "SELECT is_smart, smart_query FROM collections WHERE id = ?", (collection_id,)
    ).fetchone()
    if row is None:
        return False, None
    return bool(row["is_smart"]), row["smart_query"]


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


def create_smart_collection(
    conn: sqlite3.Connection, name: str, query: str, parent_name: str | None = None
) -> int:
    """A smart collection's membership is computed from `query` every time
    it's read (list_collection_faces/list_collection_face_ids), never
    stored in collection_faces — it can't be, since matches change as the
    library changes. Validates the query eagerly so a typo fails at
    creation time, not the first time something tries to read it."""
    evaluate_smart_query(conn, query)

    if find_collection_id(conn, name) is not None:
        raise ValueError(f"collection already exists: {name}")

    parent_id = None
    if parent_name is not None:
        parent_id = find_collection_id(conn, parent_name)
        if parent_id is None:
            raise ValueError(f"no such collection: {parent_name}")

    cur = conn.execute(
        "INSERT INTO collections (name, parent_id, is_smart, smart_query) VALUES (?, ?, 1, ?)",
        (name, parent_id, query),
    )
    conn.commit()
    return cur.lastrowid


def add_face_to_collection(conn: sqlite3.Connection, collection_id: int, font_face_id: int) -> None:
    is_smart, _ = _is_smart(conn, collection_id)
    if is_smart:
        raise ValueError("cannot manually add faces to a smart collection — its membership is computed from its query")
    conn.execute(
        "INSERT OR IGNORE INTO collection_faces (collection_id, font_face_id) VALUES (?, ?)",
        (collection_id, font_face_id),
    )
    conn.commit()


def remove_face_from_collection(
    conn: sqlite3.Connection, collection_id: int, font_face_id: int
) -> bool:
    is_smart, _ = _is_smart(conn, collection_id)
    if is_smart:
        raise ValueError("cannot manually remove faces from a smart collection — its membership is computed from its query")
    cur = conn.execute(
        "DELETE FROM collection_faces WHERE collection_id = ? AND font_face_id = ?",
        (collection_id, font_face_id),
    )
    conn.commit()
    return cur.rowcount > 0


def list_collections(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT collections.id, collections.name, parent.name AS parent_name,
               collections.is_smart, collections.smart_query,
               COUNT(collection_faces.font_face_id) AS face_count
        FROM collections
        LEFT JOIN collections AS parent ON parent.id = collections.parent_id
        LEFT JOIN collection_faces ON collection_faces.collection_id = collections.id
        GROUP BY collections.id
        ORDER BY collections.name COLLATE NOCASE
        """
    ).fetchall()

    result = []
    for row in rows:
        is_smart = bool(row["is_smart"])
        face_count = (
            len(evaluate_smart_query(conn, row["smart_query"]))
            if is_smart and row["smart_query"]
            else row["face_count"]
        )
        result.append(
            {
                "name": row["name"],
                "parent_name": row["parent_name"],
                "is_smart": is_smart,
                "face_count": face_count,
            }
        )
    return result


def get_or_create_favorites_collection(conn: sqlite3.Connection) -> int:
    collection_id = find_collection_id(conn, FAVORITES_COLLECTION_NAME)
    if collection_id is not None:
        return collection_id
    return create_collection(conn, FAVORITES_COLLECTION_NAME)


def list_collection_face_ids(conn: sqlite3.Connection, collection_id: int) -> list[int]:
    is_smart, smart_query = _is_smart(conn, collection_id)
    if is_smart and smart_query:
        return [row["face_id"] for row in evaluate_smart_query(conn, smart_query)]

    rows = conn.execute(
        "SELECT font_face_id FROM collection_faces WHERE collection_id = ?", (collection_id,)
    ).fetchall()
    return [row["font_face_id"] for row in rows]


def list_collection_faces(conn: sqlite3.Connection, collection_id: int) -> list[dict]:
    is_smart, smart_query = _is_smart(conn, collection_id)
    if is_smart and smart_query:
        return [{"family": r["family"], "style": r["style"]} for r in evaluate_smart_query(conn, smart_query)]

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
