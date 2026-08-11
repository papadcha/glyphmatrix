from __future__ import annotations

import sqlite3


def list_conflicts(conn: sqlite3.Connection) -> list[dict]:
    """Faces (family+style) backed by 2+ files with *different* content —
    genuinely different fonts claiming the same identity. Distinct from
    core/duplicates.py (byte-identical files, harmless — activating either
    gives the same result) and the schema's own "a face can have more than
    one file" allowance (meant for ttf+otf pairs of the *same* font, not
    this). Activating two such files at once is what activation_service's
    per-face conflict check refuses."""
    rows = conn.execute(
        """
        SELECT font_faces.id AS font_face_id, families.name AS family, font_faces.style,
               font_files.path, font_files.content_hash, font_files.version, font_files.source
        FROM font_files
        JOIN font_faces ON font_faces.id = font_files.font_face_id
        JOIN families ON families.id = font_faces.family_id
        ORDER BY families.name COLLATE NOCASE, font_faces.style, font_files.path
        """
    ).fetchall()

    groups: dict[int, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["font_face_id"], []).append(dict(row))

    conflicts = []
    for files in groups.values():
        distinct_hashes = {f["content_hash"] for f in files}
        if len(distinct_hashes) > 1:
            conflicts.append(
                {
                    "family": files[0]["family"],
                    "style": files[0]["style"],
                    "files": [
                        {k: v for k, v in f.items() if k not in ("family", "style", "font_face_id")}
                        for f in files
                    ],
                }
            )
    return conflicts
