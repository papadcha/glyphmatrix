from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GlyphDiff:
    only_in_a: list[str]
    only_in_b: list[str]
    changed: list[str]
    unchanged_count: int


def diff_glyphs(glyphs_a: dict[str, str], glyphs_b: dict[str, str]) -> GlyphDiff:
    """Diff two {glyph_name: outline_hash} maps."""
    names_a = set(glyphs_a)
    names_b = set(glyphs_b)
    common = names_a & names_b
    return GlyphDiff(
        only_in_a=sorted(names_a - names_b),
        only_in_b=sorted(names_b - names_a),
        changed=sorted(name for name in common if glyphs_a[name] != glyphs_b[name]),
        unchanged_count=sum(1 for name in common if glyphs_a[name] == glyphs_b[name]),
    )


_FILE_FIELDS = ("family_name", "style", "version", "foundry", "designer", "copyright", "glyph_count", "format")


@dataclass
class FileComparison:
    identical: bool  # byte-for-byte
    fields: dict[str, tuple]  # field -> (value_a, value_b), only those that differ
    sizes: tuple[int, int]
    glyphs: GlyphDiff


def compare_paths(path_a: str | Path, path_b: str | Path) -> FileComparison:
    """Compare two font files directly, without the library DB — for files
    that share family, style and version, which `compare` cannot tell apart."""
    from glyphmatrix.core.parser import parse_font_file

    a, b = parse_font_file(path_a), parse_font_file(path_b)
    fields = {
        name: (getattr(a, name), getattr(b, name))
        for name in _FILE_FIELDS
        if getattr(a, name) != getattr(b, name)
    }
    return FileComparison(
        identical=a.content_hash == b.content_hash,
        fields=fields,
        sizes=(Path(path_a).stat().st_size, Path(path_b).stat().st_size),
        glyphs=diff_glyphs(
            {g.glyph_name: g.outline_hash for g in a.glyphs},
            {g.glyph_name: g.outline_hash for g in b.glyphs},
        ),
    )


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

    return diff_glyphs(glyphs_a, glyphs_b)
