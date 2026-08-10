from __future__ import annotations

from glyphmatrix.core.models import FontFile


def find_duplicates(font_files: list[FontFile]) -> list[list[FontFile]]:
    """Group font files by content_hash; return groups with more than one file."""
    raise NotImplementedError
