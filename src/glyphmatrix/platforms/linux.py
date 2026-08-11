from __future__ import annotations

import subprocess
from pathlib import Path

from glyphmatrix.core.activation import ActivationProvider

# XDG per-user font directory — no root needed, and fontconfig watches it by
# convention. System-wide /usr/share/fonts is not used, same reasoning as
# macOS's USER_FONTS_DIR: out of scope for V0's single-user activation.
USER_FONTS_DIR = Path.home() / ".local" / "share" / "fonts"


class LinuxActivationProvider(ActivationProvider):
    """Font activation via fontconfig's per-user font directory — same
    symlink-not-copy approach as macOS (see MacOSActivationProvider), plus
    an `fc-cache` call since, unlike macOS, fontconfig doesn't reliably
    pick up new files without an explicit cache refresh."""

    def activate(self, font_file_path: str) -> None:
        source = Path(font_file_path).resolve()
        if not source.is_file():
            raise FileNotFoundError(font_file_path)

        USER_FONTS_DIR.mkdir(parents=True, exist_ok=True)
        link = USER_FONTS_DIR / source.name

        if link.is_symlink():
            if link.resolve() == source:
                return  # already active
            link.unlink()  # stale symlink for this filename — replace it
        elif link.exists():
            raise FileExistsError(
                f"{link} already exists and is not a glyphmatrix-managed symlink"
            )

        link.symlink_to(source)
        self._refresh_cache()

    def deactivate(self, font_file_path: str) -> None:
        source = Path(font_file_path).resolve()
        link = USER_FONTS_DIR / source.name
        if link.is_symlink() and link.resolve() == source:
            link.unlink()
            self._refresh_cache()

    def is_active(self, font_file_path: str) -> bool:
        source = Path(font_file_path).resolve()
        link = USER_FONTS_DIR / source.name
        return link.is_symlink() and link.resolve() == source

    def _refresh_cache(self) -> None:
        subprocess.run(
            ["fc-cache", "-f", str(USER_FONTS_DIR)], check=True, capture_output=True
        )
