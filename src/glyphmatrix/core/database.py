from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    schema_sql = resources.files("glyphmatrix.core").joinpath("schema.sql").read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    conn.commit()
