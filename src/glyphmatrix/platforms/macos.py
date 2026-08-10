from __future__ import annotations

from glyphmatrix.core.activation import ActivationProvider


class MacOSActivationProvider(ActivationProvider):
    """Not implemented — Windows-first per docs/proposal.md open decision #1."""

    def activate(self, font_file_path: str) -> None:
        raise NotImplementedError

    def deactivate(self, font_file_path: str) -> None:
        raise NotImplementedError

    def is_active(self, font_file_path: str) -> bool:
        raise NotImplementedError
