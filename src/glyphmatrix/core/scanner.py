from __future__ import annotations

from pathlib import Path
from typing import Iterator

FONT_EXTENSIONS = (".ttf", ".otf", ".ttc", ".woff", ".woff2")


def scan_directory(root: str | Path) -> Iterator[Path]:
    """Yield font file paths under root. Discovery only — no parsing,
    no DB writes. See core/parser.py for metadata extraction."""
    raise NotImplementedError
