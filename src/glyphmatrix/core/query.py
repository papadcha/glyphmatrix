from __future__ import annotations

import sqlite3


def list_faces(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT families.name AS family, font_faces.style, font_faces.weight,
               font_faces.width, font_faces.is_variable,
               COUNT(font_files.id) AS file_count
        FROM font_faces
        JOIN families ON families.id = font_faces.family_id
        LEFT JOIN font_files ON font_files.font_face_id = font_faces.id
        GROUP BY font_faces.id
        ORDER BY families.name COLLATE NOCASE, font_faces.weight, font_faces.style
        """
    ).fetchall()
    return [
        {
            "family": row["family"],
            "style": row["style"],
            "weight": row["weight"],
            "width": row["width"],
            "is_variable": bool(row["is_variable"]),
            "file_count": row["file_count"],
        }
        for row in rows
    ]


def get_family_detail(conn: sqlite3.Connection, family_name: str) -> dict | None:
    family_row = conn.execute(
        "SELECT id, name, foundry FROM families WHERE name = ? COLLATE NOCASE",
        (family_name,),
    ).fetchone()
    if family_row is None:
        return None

    faces = conn.execute(
        "SELECT id, style, weight, width, is_variable FROM font_faces "
        "WHERE family_id = ? ORDER BY weight, style",
        (family_row["id"],),
    ).fetchall()

    result_faces = []
    for face in faces:
        files = conn.execute(
            "SELECT path, filename, format, content_hash, source, version, license, "
            "glyph_count FROM font_files WHERE font_face_id = ? ORDER BY filename",
            (face["id"],),
        ).fetchall()
        result_faces.append(
            {
                "style": face["style"],
                "weight": face["weight"],
                "width": face["width"],
                "is_variable": bool(face["is_variable"]),
                "files": [dict(f) for f in files],
            }
        )

    return {
        "family": family_row["name"],
        "foundry": family_row["foundry"],
        "faces": result_faces,
    }


def list_open_issues(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT validation_issues.severity, validation_issues.issue_type,
               validation_issues.detail, validation_issues.detected_at,
               families.name AS family, font_faces.style, font_files.path
        FROM validation_issues
        JOIN font_files ON font_files.id = validation_issues.font_file_id
        JOIN font_faces ON font_faces.id = font_files.font_face_id
        JOIN families ON families.id = font_faces.family_id
        WHERE validation_issues.resolved_at IS NULL
        ORDER BY
            CASE validation_issues.severity WHEN 'error' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,
            families.name COLLATE NOCASE
        """
    ).fetchall()
    return [dict(row) for row in rows]


def find_font_file(
    conn: sqlite3.Connection, family_name: str, style: str, version: str
) -> dict | None:
    row = conn.execute(
        """
        SELECT font_files.id, font_files.path, font_files.version
        FROM font_files
        JOIN font_faces ON font_faces.id = font_files.font_face_id
        JOIN families ON families.id = font_faces.family_id
        WHERE families.name = ? COLLATE NOCASE
          AND font_faces.style = ? COLLATE NOCASE
          AND font_files.version = ?
        ORDER BY font_files.id
        """,
        (family_name, style, version),
    ).fetchone()
    return dict(row) if row is not None else None


def list_versions(conn: sqlite3.Connection, family_name: str, style: str) -> list[str | None]:
    rows = conn.execute(
        """
        SELECT DISTINCT font_files.version
        FROM font_files
        JOIN font_faces ON font_faces.id = font_files.font_face_id
        JOIN families ON families.id = font_faces.family_id
        WHERE families.name = ? COLLATE NOCASE AND font_faces.style = ? COLLATE NOCASE
        """,
        (family_name, style),
    ).fetchall()
    return [row["version"] for row in rows]
