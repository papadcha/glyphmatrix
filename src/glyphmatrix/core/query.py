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
