from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass
class GlyphDiff:
    only_in_a: list[str]
    only_in_b: list[str]
    changed: list[str]
    unchanged_count: int


def compare_font_files(conn: sqlite3.Connection, font_file_id_a: int, font_file_id_b: int) -> GlyphDiff:
    glyphs_a = {
        row["glyph_name"]: row["outline_hash"]
        for row in conn.execute(
            "SELECT glyph_name, outline_hash FROM font_glyphs WHERE font_file_id = ?",
            (font_file_id_a,),
        )
    }
    glyphs_b = {
        row["glyph_name"]: row["outline_hash"]
        for row in conn.execute(
            "SELECT glyph_name, outline_hash FROM font_glyphs WHERE font_file_id = ?",
            (font_file_id_b,),
        )
    }

    names_a = set(glyphs_a)
    names_b = set(glyphs_b)
    common = names_a & names_b

    return GlyphDiff(
        only_in_a=sorted(names_a - names_b),
        only_in_b=sorted(names_b - names_a),
        changed=sorted(name for name in common if glyphs_a[name] != glyphs_b[name]),
        unchanged_count=sum(1 for name in common if glyphs_a[name] == glyphs_b[name]),
    )
