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


# Broad tag added next to the fine-grained classification tags, so
# `tag find serif` finds Times whether it is tagged "transitional-serif"
# (sFamilyClass) or "cove" (PANOSE). Named like the CSS generic families;
# "sans-serif" is itself an sFamilyClass tag, so it doubles as the sans one.
_UMBRELLA_TAGS = {
    **dict.fromkeys(
        ("oldstyle-serif", "transitional-serif", "modern-serif", "clarendon-serif",
         "slab-serif", "freeform-serif"),
        "serif",
    ),
    **dict.fromkeys(
        ("cove", "obtuse-cove", "square-cove", "obtuse-square-cove", "square", "thin",
         "oval", "exaggerated", "triangle"),
        "serif",
    ),
    **dict.fromkeys(("normal-sans", "obtuse-sans", "perp-sans", "flared", "rounded"), "sans-serif"),
}


def classification_tags(parsed: ParsedFont) -> list[str]:
    """Auto tags for a face: its sFamilyClass and PANOSE classes, plus the
    serif/sans-serif umbrella they belong to."""
    tags = [t for t in (parsed.family_class, parsed.panose_class) if t]
    return tags + [_UMBRELLA_TAGS[t] for t in tags if t in _UMBRELLA_TAGS]


def find_or_create_family(conn: sqlite3.Connection, name: str, foundry: str | None = None) -> int:
    row = conn.execute("SELECT id FROM families WHERE name = ?", (name,)).fetchone()
    if row is not None:
        return row["id"]
    cur = conn.execute("INSERT INTO families (name, foundry) VALUES (?, ?)", (name, foundry))
    return cur.lastrowid


def _find_face(conn: sqlite3.Connection, family_id: int, parsed: ParsedFont) -> int | None:
    row = conn.execute(
        "SELECT id FROM font_faces WHERE family_id = ? AND style IS ? AND weight IS ? AND width IS ?",
        (family_id, parsed.style, parsed.weight, parsed.width),
    ).fetchone()
    return row["id"] if row is not None else None


def find_or_create_face(conn: sqlite3.Connection, family_id: int, parsed: ParsedFont) -> int:
    face_id = _find_face(conn, family_id, parsed)
    if face_id is not None:
        return face_id
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


def _resolve_known_face(
    conn: sqlite3.Connection, file_row: sqlite3.Row, family_id: int, parsed: ParsedFont
) -> int:
    """Face for a file already in the library whose parse may now differ (new
    content, or --reparse after a parser change). A face carries the user's
    tags and collections, so it is updated or merged, never left behind empty:
    - same family/style/weight/width: keep it;
    - the file is the face's only file: update the face in place, or if a face
      with the new values already exists, move the file there and carry the
      tags/collections over;
    - other files share the face: move only this file, leaving theirs as is."""
    old_id = file_row["font_face_id"]
    old = conn.execute("SELECT * FROM font_faces WHERE id = ?", (old_id,)).fetchone()
    if old is None:
        return find_or_create_face(conn, family_id, parsed)

    axes_json = json.dumps(parsed.axes) if parsed.axes else None
    if (old["family_id"], old["style"], old["weight"], old["width"]) == (
        family_id, parsed.style, parsed.weight, parsed.width
    ):
        conn.execute(
            "UPDATE font_faces SET is_variable = ?, axes_json = ? WHERE id = ?",
            (int(parsed.is_variable), axes_json, old_id),
        )
        return old_id

    shared = conn.execute(
        "SELECT COUNT(*) AS n FROM font_files WHERE font_face_id = ?", (old_id,)
    ).fetchone()["n"] > 1
    if shared:
        return find_or_create_face(conn, family_id, parsed)

    target_id = _find_face(conn, family_id, parsed)
    if target_id is None:
        conn.execute(
            "UPDATE font_faces SET family_id = ?, style = ?, weight = ?, width = ?, "
            "is_variable = ?, axes_json = ? WHERE id = ?",
            (family_id, parsed.style, parsed.weight, parsed.width,
             int(parsed.is_variable), axes_json, old_id),
        )
        new_id = old_id
    else:
        conn.execute("UPDATE font_files SET font_face_id = ? WHERE font_face_id = ?", (target_id, old_id))
        for table in ("font_tags", "collection_faces"):
            conn.execute(
                f"UPDATE OR IGNORE {table} SET font_face_id = ? WHERE font_face_id = ?", (target_id, old_id)
            )
            conn.execute(f"DELETE FROM {table} WHERE font_face_id = ?", (old_id,))
        conn.execute("DELETE FROM font_faces WHERE id = ?", (old_id,))
        new_id = target_id

    if old["family_id"] != family_id:
        conn.execute(
            "DELETE FROM families WHERE id = ? AND NOT EXISTS "
            "(SELECT 1 FROM font_faces WHERE family_id = ?)",
            (old["family_id"], old["family_id"]),
        )
    return new_id


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


def _metadata_json(parsed: ParsedFont) -> str | None:
    return json.dumps(parsed.metadata, ensure_ascii=False) if parsed.metadata else None


def ingest_font_file(
    conn: sqlite3.Connection, font_face_id: int, parsed: ParsedFont, source: str = "user",
    force: bool = False,
) -> tuple[int, str]:
    """Insert or update the font_files row for parsed.path. Returns
    (font_file_id, status) where status is 'added', 'changed', 'unchanged',
    or 'reparsed' (force=True on unchanged content: row and glyphs rewritten)."""
    existing = conn.execute(
        "SELECT id, content_hash FROM font_files WHERE path = ?", (str(parsed.path),)
    ).fetchone()

    same_content = existing is not None and existing["content_hash"] == parsed.content_hash
    if same_content and not force:
        return existing["id"], "unchanged"

    if existing is not None:
        font_file_id = existing["id"]
        conn.execute(
            "UPDATE font_files SET font_face_id=?, filename=?, format=?, content_hash=?, "
            "version=?, license=?, glyph_count=?, metadata_json=? WHERE id=?",
            (
                font_face_id,
                parsed.filename,
                parsed.format,
                parsed.content_hash,
                parsed.version,
                parsed.license,
                parsed.glyph_count,
                _metadata_json(parsed),
                font_file_id,
            ),
        )
        conn.execute("DELETE FROM font_glyphs WHERE font_file_id = ?", (font_file_id,))
        status = "reparsed" if same_content else "changed"
    else:
        cur = conn.execute(
            "INSERT INTO font_files (font_face_id, path, filename, format, content_hash, "
            "source, version, license, glyph_count, metadata_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                _metadata_json(parsed),
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


def ingest_directory(
    conn: sqlite3.Connection, root: str | Path, source: str = "user", reparse: bool = False
) -> ScanRun:
    """Scan root into the library. Files whose content is unchanged are left
    alone (no family/face lookups, so a parser change can't leave empty faces
    behind); reparse=True re-reads them too and updates their existing face
    in place."""
    root = Path(root)
    root_prefix = str(root).rstrip(os.sep) + os.sep
    started_at = datetime.now(timezone.utc).isoformat()
    seen_paths: set[str] = set()
    scanned = added = changed = reparsed = errors = 0

    for font_path in scan_directory(root):
        scanned += 1
        try:
            parsed = parse_font_file(font_path)
            known = conn.execute(
                "SELECT id, content_hash, font_face_id FROM font_files WHERE path = ?",
                (str(parsed.path),),
            ).fetchone()
            if known is not None and known["content_hash"] == parsed.content_hash and not reparse:
                seen_paths.add(str(font_path))
                continue
            family_id = find_or_create_family(conn, parsed.family_name, parsed.foundry)
            if known is None:
                face_id = find_or_create_face(conn, family_id, parsed)
            else:
                face_id = _resolve_known_face(conn, known, family_id, parsed)
            add_tags(conn, face_id, classification_tags(parsed))
            _, status = ingest_font_file(conn, face_id, parsed, source=source, force=reparse)
            seen_paths.add(str(font_path))
            if status == "added":
                added += 1
            elif status == "changed":
                changed += 1
            elif status == "reparsed":
                reparsed += 1
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
        files_reparsed=reparsed,
    )
