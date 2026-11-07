from __future__ import annotations

from pathlib import Path
from typing import Iterator

# SFNT formats parse fully (see parser.py). Type 1 (.pfb/.pfa) and legacy
# bitmap formats (.bdf/.pcf/.fon/.dfont) are scanned/hashed/deduped but not
# parsed for family/style/glyph metadata yet — see core/parser.py and
# TODO.md.
FONT_EXTENSIONS = (
    ".ttf", ".otf", ".ttc", ".otc", ".woff", ".woff2",
    ".pfb", ".pfa", ".bdf", ".pcf", ".fon", ".dfont",
)


# Folders that never hold the user's fonts: NAS recycle bins and metadata
# (Synology #recycle/@eaDir, QNAP @Recycle/.@__thumb, #snapshot) and hidden
# system folders (.Trashes, .AppleDouble, .TemporaryItems, ...).
_SKIP_DIRS = {"#recycle", "@recycle", "#snapshot", "@eadir", "@__thumb", ".@__thumb"}


def is_skipped(path: Path, root: Path) -> bool:
    """Hidden files ("._Font.ttf" AppleDouble companions macOS writes on NAS
    and USB volumes, ".DS_Store") and anything inside a hidden or NAS-system
    folder below root."""
    if path.name.startswith("."):
        return True
    try:
        parts = path.relative_to(root).parts[:-1]
    except ValueError:
        parts = path.parts[:-1]
    return any(p.startswith(".") or p.casefold() in _SKIP_DIRS for p in parts)


def scan_directory(root: str | Path) -> Iterator[Path]:
    root = Path(root)
    for path in root.rglob("*"):
        if path.suffix.lower() in FONT_EXTENSIONS and not is_skipped(path, root) and path.is_file():
            yield path
