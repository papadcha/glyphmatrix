from __future__ import annotations

from pathlib import Path


def render_preview(font_file_path: str | Path, text: str, out_path: str | Path) -> None:
    """Raster preview export via fontTools + Pillow. GUI (canvas/WebGL) is V1.5+."""
    raise NotImplementedError
