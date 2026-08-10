from __future__ import annotations

from glyphmatrix.core.activation import ActivationProvider

_MESSAGE = "Linux activation not yet implemented — macOS-first, see docs/proposal.md"


class LinuxActivationProvider(ActivationProvider):
    """Not implemented — macOS-first per docs/proposal.md open decision #1."""

    def activate(self, font_file_path: str) -> None:
        raise NotImplementedError(_MESSAGE)

    def deactivate(self, font_file_path: str) -> None:
        raise NotImplementedError(_MESSAGE)

    def is_active(self, font_file_path: str) -> bool:
        raise NotImplementedError(_MESSAGE)
