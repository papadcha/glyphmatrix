from __future__ import annotations

from pathlib import Path
from typing import Iterator

# SFNT formats parse fully (see parser.py). Type 1 (.pfb/.pfa) and legacy
# bitmap formats (.bdf/.pcf/.fon/.dfont) are scanned/hashed/deduped but not
# parsed for family/style/glyph metadata yet — see core/parser.py and
# TODO.md.
FONT_EXTENSIONS = (
    ".ttf", ".otf", ".ttc", ".woff", ".woff2",
    ".pfb", ".pfa", ".bdf", ".pcf", ".fon", ".dfont",
)


def scan_directory(root: str | Path) -> Iterator[Path]:
    root = Path(root)
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in FONT_EXTENSIONS:
            yield path
