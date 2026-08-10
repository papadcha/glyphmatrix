from __future__ import annotations

from pathlib import Path
from typing import Iterator

FONT_EXTENSIONS = (".ttf", ".otf", ".ttc", ".woff", ".woff2")


def scan_directory(root: str | Path) -> Iterator[Path]:
    root = Path(root)
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in FONT_EXTENSIONS:
            yield path
