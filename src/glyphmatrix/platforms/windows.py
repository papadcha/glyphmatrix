from __future__ import annotations

import ctypes
from pathlib import Path

from glyphmatrix.core.activation import ActivationProvider

_HWND_BROADCAST = 0xFFFF
_WM_FONTCHANGE = 0x001D


class WindowsActivationProvider(ActivationProvider):
    """Font activation via the GDI AddFontResourceEx/RemoveFontResourceEx
    APIs, called directly against the original file path — no copy, no
    registry write, no admin privileges needed. Fonts registered this way
    are visible session-wide to every process (we don't pass FR_PRIVATE)
    but don't persist across logoff/reboot — matching the tool's on-demand
    activation model without ever touching the Fonts folder.

    AddFontResourceEx is reference-counted: calling it twice for the same
    path needs two matching RemoveFontResourceEx calls to fully undo.
    activation_service.py guards against this by skipping the call
    entirely when its own records already say the file is active — this
    provider does not attempt its own idempotency check."""

    def activate(self, font_file_path: str) -> None:
        path = Path(font_file_path)
        if not path.is_file():
            raise FileNotFoundError(font_file_path)

        added = ctypes.windll.gdi32.AddFontResourceExW(str(path), 0, None)
        if added == 0:
            raise OSError(f"AddFontResourceEx failed for {path}")
        ctypes.windll.user32.SendMessageW(_HWND_BROADCAST, _WM_FONTCHANGE, 0, 0)

    def deactivate(self, font_file_path: str) -> None:
        path = Path(font_file_path)
        removed = ctypes.windll.gdi32.RemoveFontResourceExW(str(path), 0, None)
        if not removed:
            raise OSError(f"RemoveFontResourceEx failed for {path}")
        ctypes.windll.user32.SendMessageW(_HWND_BROADCAST, _WM_FONTCHANGE, 0, 0)

    def is_active(self, font_file_path: str) -> bool:
        raise NotImplementedError(
            "Windows has no API to query AddFontResourceEx registration state "
            "by path — GlyphMatrix tracks activation state itself (see the "
            "activations table / activation_service.py), which is "
            "authoritative instead of asking the OS."
        )
