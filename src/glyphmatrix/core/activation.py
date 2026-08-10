from __future__ import annotations

from abc import ABC, abstractmethod

# V0 contract: only these two transitions exist. Anything else (sets,
# temporary activation, conflict handling) is V1.5 — see docs/proposal.md.
V0_STATES = ("installed", "active")


class ActivationProvider(ABC):
    """Platform-specific font activation. Core code depends only on this
    interface, never on a concrete platform module."""

    @abstractmethod
    def activate(self, font_file_path: str) -> None: ...

    @abstractmethod
    def deactivate(self, font_file_path: str) -> None: ...

    @abstractmethod
    def is_active(self, font_file_path: str) -> bool: ...
