from __future__ import annotations

import re
import sqlite3

# Face-level or file-level columns a term can filter on. Anything else
# raises — no silent typos.
_FIELD_COLUMNS = {
    "family": "families.name",
    "style": "font_faces.style",
    "foundry": "families.foundry",
    "width": "font_faces.width",
    "source": "font_files.source",
    "license": "font_files.license",
    "version": "font_files.version",
}


def evaluate_smart_query(conn: sqlite3.Connection, query: str) -> list[dict]:
    """DNF query over face/file/tag fields: 'foundry:Adobe style:Regular
    OR tag:script'. Space-separated field:value terms within a group are
    ANDed; groups split on ' OR ' (case-insensitive) are ORed — no
    parens, no mixed AND/OR precedence, matches the proposal's own "cheap
    query language, not NLP" framing (same spirit as query.search_library).
    A bare word (no ':') matches family/style/foundry/tag, same fields as
    search_library's free-text term.

    Raises ValueError on an unknown field or empty query — this is also
    how create_smart_collection validates a query before saving it."""
    query = query.strip()
    if not query:
        raise ValueError("smart query cannot be empty")

    groups = re.split(r"\s+OR\s+", query, flags=re.IGNORECASE)
    seen_face_ids: set[int] = set()
    results: list[dict] = []

    for group in groups:
        group = group.strip()
        if not group:
            continue
        for row in _evaluate_and_group(conn, group):
            if row["face_id"] not in seen_face_ids:
                seen_face_ids.add(row["face_id"])
                results.append(
                    {"face_id": row["face_id"], "family": row["family"], "style": row["style"]}
                )

    results.sort(key=lambda r: (r["family"].lower(), r["style"] or ""))
    return results


def _evaluate_and_group(conn: sqlite3.Connection, group: str) -> list[sqlite3.Row]:
    conditions: list[str] = []
    params: list = []
    needs_tags_join = False

    for token in group.split():
        if ":" in token:
            field, _, value = token.partition(":")
            field, value = field.strip().lower(), value.strip()
        else:
            field, value = "*", token

        if field == "tag":
            needs_tags_join = True
            conditions.append("tags.name = ? COLLATE NOCASE")
            params.append(value)
        elif field == "*":
            needs_tags_join = True
            pattern = f"%{value}%"
            conditions.append(
                "(families.name LIKE ? OR font_faces.style LIKE ? OR families.foundry LIKE ? "
                "OR tags.name LIKE ?)"
            )
            params.extend([pattern, pattern, pattern, pattern])
        elif field == "weight":
            try:
                weight_value = int(value)
            except ValueError:
                raise ValueError(f"weight must be a number, got {value!r}") from None
            conditions.append("font_faces.weight = ?")
            params.append(weight_value)
        elif field in _FIELD_COLUMNS:
            conditions.append(f"{_FIELD_COLUMNS[field]} LIKE ?")
            params.append(f"%{value}%")
        else:
            known = ", ".join(["tag", "weight", *_FIELD_COLUMNS])
            raise ValueError(f"unknown smart-query field {field!r} — known fields: {known}")

    where_clause = " AND ".join(conditions) if conditions else "1=1"
    tags_join = (
        "LEFT JOIN font_tags ON font_tags.font_face_id = font_faces.id "
        "LEFT JOIN tags ON tags.id = font_tags.tag_id"
        if needs_tags_join
        else ""
    )

    sql = f"""
        SELECT DISTINCT font_faces.id AS face_id, families.name AS family, font_faces.style
        FROM font_faces
        JOIN families ON families.id = font_faces.family_id
        LEFT JOIN font_files ON font_files.font_face_id = font_faces.id
        {tags_join}
        WHERE {where_clause}
    """
    return conn.execute(sql, params).fetchall()
