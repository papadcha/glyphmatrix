from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from glyphmatrix.core.parser import parse_font_file


@dataclass
class ValidationSummary:
    checked: int
    issues_opened: int
    issues_resolved: int


def _open_issue(conn: sqlite3.Connection, font_file_id: int, issue_type: str, severity: str, detail: str) -> bool:
    existing = conn.execute(
        "SELECT id FROM validation_issues WHERE font_file_id = ? AND issue_type = ? "
        "AND resolved_at IS NULL",
        (font_file_id, issue_type),
    ).fetchone()
    if existing is not None:
        return False
    conn.execute(
        "INSERT INTO validation_issues (font_file_id, severity, issue_type, detail) "
        "VALUES (?, ?, ?, ?)",
        (font_file_id, severity, issue_type, detail),
    )
    return True


def _resolve_issue(conn: sqlite3.Connection, font_file_id: int, issue_type: str) -> bool:
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "UPDATE validation_issues SET resolved_at = ? WHERE font_file_id = ? "
        "AND issue_type = ? AND resolved_at IS NULL",
        (now, font_file_id, issue_type),
    )
    return cur.rowcount > 0


def validate_library(conn: sqlite3.Connection) -> ValidationSummary:
    checked = opened = resolved = 0

    for row in conn.execute("SELECT id, path FROM font_files"):
        checked += 1
        font_file_id = row["id"]
        path = Path(row["path"])

        if not path.is_file():
            if _open_issue(conn, font_file_id, "missing_file", "error", f"file not found: {path}"):
                opened += 1
            continue
        if _resolve_issue(conn, font_file_id, "missing_file"):
            resolved += 1

        try:
            parse_font_file(path)
        except Exception as exc:
            if _open_issue(conn, font_file_id, "corrupt", "error", str(exc)):
                opened += 1
            continue
        if _resolve_issue(conn, font_file_id, "corrupt"):
            resolved += 1

    conn.commit()
    return ValidationSummary(checked=checked, issues_opened=opened, issues_resolved=resolved)
