from __future__ import annotations

import sqlite3


def glyph_summary(conn: sqlite3.Connection, font_file_id: int) -> dict:
    row = conn.execute(
        """
        SELECT COUNT(*) AS glyph_count,
               MIN(unicode_codepoint) AS min_codepoint,
               MAX(unicode_codepoint) AS max_codepoint,
               COUNT(unicode_codepoint) AS mapped_count,
               MIN(contour_count) AS min_contours,
               MAX(contour_count) AS max_contours
        FROM font_glyphs
        WHERE font_file_id = ?
        """,
        (font_file_id,),
    ).fetchone()
    return dict(row)


def find_glyphs(
    conn: sqlite3.Connection,
    font_file_id: int,
    *,
    glyph_name: str | None = None,
    codepoint: int | None = None,
    name_search: str | None = None,
) -> list[dict]:
    """No filter given at all still scopes to font_file_id — callers
    decide whether "no filter" means "show everything" (glyph_inspector
    CLI treats it as a request for the summary instead, to avoid dumping
    thousands of lines by default)."""
    conditions = ["font_file_id = ?"]
    params: list = [font_file_id]

    if glyph_name is not None:
        conditions.append("glyph_name = ?")
        params.append(glyph_name)
    if codepoint is not None:
        conditions.append("unicode_codepoint = ?")
        params.append(codepoint)
    if name_search is not None:
        conditions.append("glyph_name LIKE ?")
        params.append(f"%{name_search}%")

    sql = (
        "SELECT glyph_name, unicode_codepoint, contour_count, advance_width, outline_hash "
        "FROM font_glyphs WHERE " + " AND ".join(conditions) + " ORDER BY glyph_name"
    )
    return [dict(row) for row in conn.execute(sql, params).fetchall()]
