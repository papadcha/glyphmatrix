from __future__ import annotations

import sqlite3


def find_package_id(conn: sqlite3.Connection, name: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM packages WHERE name = ? COLLATE NOCASE ORDER BY id", (name,)
    ).fetchone()
    return row["id"] if row is not None else None


def create_package(
    conn: sqlite3.Connection, name: str, vendor: str | None = None, notes: str | None = None
) -> int:
    if find_package_id(conn, name) is not None:
        raise ValueError(f"package already exists: {name}")

    cur = conn.execute(
        "INSERT INTO packages (name, vendor, notes) VALUES (?, ?, ?)", (name, vendor, notes)
    )
    conn.commit()
    return cur.lastrowid


def add_file_to_package(conn: sqlite3.Connection, package_id: int, font_file_id: int) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO package_files (package_id, font_file_id) VALUES (?, ?)",
        (package_id, font_file_id),
    )
    conn.commit()


def remove_file_from_package(
    conn: sqlite3.Connection, package_id: int, font_file_id: int
) -> bool:
    cur = conn.execute(
        "DELETE FROM package_files WHERE package_id = ? AND font_file_id = ?",
        (package_id, font_file_id),
    )
    conn.commit()
    return cur.rowcount > 0


def list_packages(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT packages.name, packages.vendor,
               COUNT(DISTINCT package_files.font_file_id) AS file_count,
               COUNT(DISTINCT package_documents.id) AS document_count
        FROM packages
        LEFT JOIN package_files ON package_files.package_id = packages.id
        LEFT JOIN package_documents ON package_documents.package_id = packages.id
        GROUP BY packages.id
        ORDER BY packages.name COLLATE NOCASE
        """
    ).fetchall()
    return [dict(row) for row in rows]


def list_package_files(conn: sqlite3.Connection, package_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT families.name AS family, font_faces.style, font_files.filename, font_files.path
        FROM package_files
        JOIN font_files ON font_files.id = package_files.font_file_id
        JOIN font_faces ON font_faces.id = font_files.font_face_id
        JOIN families ON families.id = font_faces.family_id
        WHERE package_files.package_id = ?
        ORDER BY families.name COLLATE NOCASE, font_faces.style
        """,
        (package_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def add_document(
    conn: sqlite3.Connection, package_id: int, path: str, description: str | None = None
) -> int:
    cur = conn.execute(
        "INSERT INTO package_documents (package_id, path, description) VALUES (?, ?, ?)",
        (package_id, path, description),
    )
    conn.commit()
    return cur.lastrowid


def remove_document(conn: sqlite3.Connection, package_id: int, path: str) -> bool:
    cur = conn.execute(
        "DELETE FROM package_documents WHERE package_id = ? AND path = ?", (package_id, path)
    )
    conn.commit()
    return cur.rowcount > 0


def list_documents(conn: sqlite3.Connection, package_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT path, description FROM package_documents WHERE package_id = ? ORDER BY path",
        (package_id,),
    ).fetchall()
    return [dict(row) for row in rows]
