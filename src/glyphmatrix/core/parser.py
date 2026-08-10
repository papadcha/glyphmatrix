from __future__ import annotations

from pathlib import Path

from glyphmatrix.core.models import FontFace, FontFile


def parse_font_file(path: str | Path) -> tuple[FontFace, FontFile]:
    """Extract family/face/file metadata from a font file via fontTools."""
    raise NotImplementedError
