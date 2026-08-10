from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from glyphmatrix.core.models import ScanRun
from glyphmatrix.core.parser import ParsedFont, parse_font_file
from glyphmatrix.core.scanner import scan_directory
from glyphmatrix.core.tags import add_tags


def find_or_create_family(conn: sqlite3.Connection, name: str, foundry: str | None = None) -> int:
    row = conn.execute("SELECT id FROM families WHERE name = ?", (name,)).fetchone()
    if row is not None:
        return row["id"]
    cur = conn.execute("INSERT INTO families (name, foundry) VALUES (?, ?)", (name, foundry))
    return cur.lastrowid


def find_or_create_face(conn: sqlite3.Connection, family_id: int, parsed: ParsedFont) -> int:
    row = conn.execute(
        "SELECT id FROM font_faces WHERE family_id = ? AND style IS ? AND weight IS ? AND width IS ?",
        (family_id, parsed.style, parsed.weight, parsed.width),
    ).fetchone()
    if row is not None:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO font_faces (family_id, style, weight, width, is_variable, axes_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            family_id,
            parsed.style,
            parsed.weight,
            parsed.width,
            int(parsed.is_variable),
            json.dumps(parsed.axes) if parsed.axes else None,
        ),
    )
    return cur.lastrowid


def _flag_unsupported_format(conn: sqlite3.Connection, font_file_id: int, fmt: str) -> None:
    existing = conn.execute(
        "SELECT id FROM validation_issues WHERE font_file_id = ? AND issue_type = 'unsupported_format' "
        "AND resolved_at IS NULL",
        (font_file_id,),
    ).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO validation_issues (font_file_id, severity, issue_type, detail) "
            "VALUES (?, 'info', 'unsupported_format', ?)",
            (
                font_file_id,
                f"'.{fmt}' is tracked (path/hash/duplicates) but not parsed — "
                "no family/style/glyph metadata available yet",
            ),
        )


def ingest_font_file(
    conn: sqlite3.Connection, font_face_id: int, parsed: ParsedFont, source: str = "user"
) -> tuple[int, str]:
    """Insert or update the font_files row for parsed.path. Returns
    (font_file_id, status) where status is 'added', 'changed', or 'unchanged'."""
    existing = conn.execute(
        "SELECT id, content_hash FROM font_files WHERE path = ?", (str(parsed.path),)
    ).fetchone()

    if existing is not None and existing["content_hash"] == parsed.content_hash:
        return existing["id"], "unchanged"

    if existing is not None:
        font_file_id = existing["id"]
        conn.execute(
            "UPDATE font_files SET font_face_id=?, filename=?, format=?, content_hash=?, "
            "version=?, license=?, glyph_count=? WHERE id=?",
            (
                font_face_id,
                parsed.filename,
                parsed.format,
                parsed.content_hash,
                parsed.version,
                parsed.license,
                parsed.glyph_count,
                font_file_id,
            ),
        )
        conn.execute("DELETE FROM font_glyphs WHERE font_file_id = ?", (font_file_id,))
        status = "changed"
    else:
        cur = conn.execute(
            "INSERT INTO font_files (font_face_id, path, filename, format, content_hash, "
            "source, version, license, glyph_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                font_face_id,
                str(parsed.path),
                parsed.filename,
                parsed.format,
                parsed.content_hash,
                source,
                parsed.version,
                parsed.license,
                parsed.glyph_count,
            ),
        )
        font_file_id = cur.lastrowid
        status = "added"

    if not parsed.metadata_complete:
        _flag_unsupported_format(conn, font_file_id, parsed.format)

    conn.executemany(
        "INSERT INTO font_glyphs (font_file_id, glyph_name, unicode_codepoint, "
        "contour_count, advance_width, outline_hash) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (
                font_file_id,
                g.glyph_name,
                g.unicode_codepoint,
                g.contour_count,
                g.advance_width,
                g.outline_hash,
            )
            for g in parsed.glyphs
        ],
    )
    return font_file_id, status


def ingest_directory(conn: sqlite3.Connection, root: str | Path, source: str = "user") -> ScanRun:
    root = Path(root)
    root_prefix = str(root).rstrip(os.sep) + os.sep
    started_at = datetime.now(timezone.utc).isoformat()
    seen_paths: set[str] = set()
    scanned = added = changed = errors = 0

    for font_path in scan_directory(root):
        scanned += 1
        try:
            parsed = parse_font_file(font_path)
            family_id = find_or_create_family(conn, parsed.family_name, parsed.foundry)
            face_id = find_or_create_face(conn, family_id, parsed)
            if parsed.family_class:
                add_tags(conn, face_id, [parsed.family_class])
            _, status = ingest_font_file(conn, face_id, parsed, source=source)
            seen_paths.add(str(font_path))
            if status == "added":
                added += 1
            elif status == "changed":
                changed += 1
        except Exception:
            errors += 1

    # Rows for files under root that weren't seen this run are left in place,
    # not deleted — root could be a temporarily disconnected drive. Deciding
    # whether to flag/remove them is validator.py's job, not the scanner's.
    removed = 0
    for row in conn.execute(
        "SELECT path FROM font_files WHERE substr(path, 1, ?) = ?",
        (len(root_prefix), root_prefix),
    ):
        if row["path"] not in seen_paths:
            removed += 1

    finished_at = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO scan_runs (started_at, finished_at, files_scanned, files_added, "
        "files_changed, files_removed, errors) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (started_at, finished_at, scanned, added, changed, removed, errors),
    )
    conn.commit()

    return ScanRun(
        id=cur.lastrowid,
        started_at=started_at,
        finished_at=finished_at,
        files_scanned=scanned,
        files_added=added,
        files_changed=changed,
        files_removed=removed,
        errors=errors,
    )
