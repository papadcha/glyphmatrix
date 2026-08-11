import sys
import types

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only activation API")

from glyphmatrix.platforms import windows as windows_module  # noqa: E402
from glyphmatrix.platforms.windows import WindowsActivationProvider  # noqa: E402


class _FakeGdi32:
    def __init__(self):
        self.added = []
        self.removed = []
        self.add_return = 1
        self.remove_return = 1

    def AddFontResourceExW(self, path, flags, pdv):
        self.added.append((path, flags))
        return self.add_return

    def RemoveFontResourceExW(self, path, flags, pdv):
        self.removed.append((path, flags))
        return self.remove_return


class _FakeUser32:
    def __init__(self):
        self.messages = []

    def SendMessageW(self, hwnd, msg, wparam, lparam):
        self.messages.append((hwnd, msg, wparam, lparam))


@pytest.fixture
def gdi32(monkeypatch):
    fake_gdi32 = _FakeGdi32()
    fake_user32 = _FakeUser32()
    fake_windll = types.SimpleNamespace(gdi32=fake_gdi32, user32=fake_user32)
    monkeypatch.setattr(windows_module.ctypes, "windll", fake_windll)
    return fake_gdi32, fake_user32


@pytest.fixture
def font_file(tmp_path):
    path = tmp_path / "Arial-Regular.ttf"
    path.write_bytes(b"fake font bytes")
    return path


def test_activate_calls_addfontresourceex_and_broadcasts(gdi32, font_file):
    fake_gdi32, fake_user32 = gdi32
    provider = WindowsActivationProvider()

    provider.activate(str(font_file))

    assert fake_gdi32.added == [(str(font_file), 0)]
    assert len(fake_user32.messages) == 1


def test_activate_missing_file_raises(gdi32, tmp_path):
    provider = WindowsActivationProvider()
    missing = tmp_path / "nope.ttf"

    with pytest.raises(FileNotFoundError):
        provider.activate(str(missing))


def test_activate_raises_when_addfontresourceex_fails(gdi32, font_file):
    fake_gdi32, _ = gdi32
    fake_gdi32.add_return = 0
    provider = WindowsActivationProvider()

    with pytest.raises(OSError):
        provider.activate(str(font_file))


def test_deactivate_calls_removefontresourceex_and_broadcasts(gdi32, font_file):
    fake_gdi32, fake_user32 = gdi32
    provider = WindowsActivationProvider()

    provider.deactivate(str(font_file))

    assert fake_gdi32.removed == [(str(font_file), 0)]
    assert len(fake_user32.messages) == 1


def test_deactivate_raises_when_removefontresourceex_fails(gdi32, font_file):
    fake_gdi32, _ = gdi32
    fake_gdi32.remove_return = 0
    provider = WindowsActivationProvider()

    with pytest.raises(OSError):
        provider.deactivate(str(font_file))


def test_is_active_raises_not_implemented(font_file):
    provider = WindowsActivationProvider()

    with pytest.raises(NotImplementedError):
        provider.is_active(str(font_file))
