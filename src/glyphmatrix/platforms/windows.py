from __future__ import annotations

from glyphmatrix.core.activation import ActivationProvider


class WindowsActivationProvider(ActivationProvider):
    """Windows font activation via the AddFontResource/RemoveFontResource
    GDI APIs (or the user font folder for per-user installs)."""

    def activate(self, font_file_path: str) -> None:
        raise NotImplementedError

    def deactivate(self, font_file_path: str) -> None:
        raise NotImplementedError

    def is_active(self, font_file_path: str) -> bool:
        raise NotImplementedError
