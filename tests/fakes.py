from __future__ import annotations

from glyphmatrix.core.activation import ActivationProvider


class FakeActivationProvider(ActivationProvider):
    def __init__(self, fail_paths: frozenset[str] = frozenset()):
        self.fail_paths = fail_paths
        self.activated: list[str] = []
        self.deactivated: list[str] = []

    def activate(self, font_file_path: str) -> None:
        if font_file_path in self.fail_paths:
            raise RuntimeError("boom")
        self.activated.append(font_file_path)

    def deactivate(self, font_file_path: str) -> None:
        if font_file_path in self.fail_paths:
            raise RuntimeError("boom")
        self.deactivated.append(font_file_path)

    def is_active(self, font_file_path: str) -> bool:
        return font_file_path in self.activated
