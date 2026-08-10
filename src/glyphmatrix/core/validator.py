from __future__ import annotations

from glyphmatrix.core.models import FontFile, ValidationIssue


def validate_font_file(font_file: FontFile) -> list[ValidationIssue]:
    """Check for corruption / missing glyphs / other structural issues."""
    raise NotImplementedError
