from __future__ import annotations

from pathlib import Path

from glyphmatrix.core.activation import ActivationProvider

# Per-user Font Book directory — no elevated privileges needed, and it's the
# same location Font Book itself manages. System-wide /Library/Fonts is not
# used: it needs root and would activate the font for every user, which is
# out of scope for V0's single-user, on-demand activation.
USER_FONTS_DIR = Path.home() / "Library" / "Fonts"


class MacOSActivationProvider(ActivationProvider):
    """Font activation via the user Library/Fonts directory (and Font Book's
    underlying mechanism). First real ActivationProvider — macOS-first per
    docs/proposal.md open decision #1.

    Activation is a symlink named after the source file, placed in
    USER_FONTS_DIR and pointing back at it — never a copy. This keeps the
    original file as the sole source of truth (proposal principle #2) and
    means deactivate can only ever remove a symlink we created, never a real
    file."""

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

    def deactivate(self, font_file_path: str) -> None:
        source = Path(font_file_path).resolve()
        link = USER_FONTS_DIR / source.name
        if link.is_symlink() and link.resolve() == source:
            link.unlink()

    def is_active(self, font_file_path: str) -> bool:
        source = Path(font_file_path).resolve()
        link = USER_FONTS_DIR / source.name
        return link.is_symlink() and link.resolve() == source
