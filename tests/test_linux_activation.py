import pytest

from glyphmatrix.platforms import linux as linux_module
from glyphmatrix.platforms.linux import LinuxActivationProvider


class _FakeCompletedProcess:
    returncode = 0


@pytest.fixture
def fc_cache_calls(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return _FakeCompletedProcess()

    monkeypatch.setattr(linux_module.subprocess, "run", fake_run)
    return calls


@pytest.fixture
def provider(tmp_path, monkeypatch, fc_cache_calls):
    monkeypatch.setattr(linux_module, "USER_FONTS_DIR", tmp_path / "fonts")
    return LinuxActivationProvider()


@pytest.fixture
def font_file(tmp_path):
    path = tmp_path / "Arial-Regular.ttf"
    path.write_bytes(b"fake font bytes")
    return path


def test_activate_creates_symlink_and_refreshes_cache(provider, font_file, fc_cache_calls):
    provider.activate(str(font_file))

    link = linux_module.USER_FONTS_DIR / font_file.name
    assert link.is_symlink()
    assert link.resolve() == font_file.resolve()
    assert provider.is_active(str(font_file))
    assert fc_cache_calls == [["fc-cache", "-f", str(linux_module.USER_FONTS_DIR)]]


def test_activate_is_idempotent(provider, font_file, fc_cache_calls):
    provider.activate(str(font_file))
    provider.activate(str(font_file))  # should not raise

    assert provider.is_active(str(font_file))
    assert len(fc_cache_calls) == 1  # second call was a no-op, no refresh needed


def test_activate_missing_source_file_raises(provider, tmp_path):
    missing = tmp_path / "nope.ttf"
    with pytest.raises(FileNotFoundError):
        provider.activate(str(missing))


def test_activate_replaces_stale_symlink_for_same_filename(provider, tmp_path):
    folder_a = tmp_path / "a"
    folder_a.mkdir()
    folder_b = tmp_path / "b"
    folder_b.mkdir()
    font_a = folder_a / "Arial-Regular.ttf"
    font_a.write_bytes(b"font a")
    font_b = folder_b / "Arial-Regular.ttf"
    font_b.write_bytes(b"font b")

    provider.activate(str(font_a))
    provider.activate(str(font_b))

    link = linux_module.USER_FONTS_DIR / "Arial-Regular.ttf"
    assert link.resolve() == font_b.resolve()
    assert not provider.is_active(str(font_a))
    assert provider.is_active(str(font_b))


def test_activate_conflicts_with_unmanaged_real_file(provider, font_file):
    linux_module.USER_FONTS_DIR.mkdir(parents=True, exist_ok=True)
    real_file = linux_module.USER_FONTS_DIR / font_file.name
    real_file.write_bytes(b"a real font, not managed by glyphmatrix")

    with pytest.raises(FileExistsError):
        provider.activate(str(font_file))


def test_deactivate_removes_symlink_and_refreshes_cache(provider, font_file, fc_cache_calls):
    provider.activate(str(font_file))
    provider.deactivate(str(font_file))

    assert not provider.is_active(str(font_file))
    assert not (linux_module.USER_FONTS_DIR / font_file.name).exists()
    assert len(fc_cache_calls) == 2  # one for activate, one for deactivate


def test_deactivate_when_never_activated_is_noop(provider, font_file, fc_cache_calls):
    provider.deactivate(str(font_file))  # should not raise

    assert fc_cache_calls == []  # nothing to refresh


def test_deactivate_never_removes_unmanaged_file(provider, font_file):
    linux_module.USER_FONTS_DIR.mkdir(parents=True, exist_ok=True)
    real_file = linux_module.USER_FONTS_DIR / font_file.name
    real_file.write_bytes(b"a real font, not managed by glyphmatrix")

    provider.deactivate(str(font_file))

    assert real_file.exists()
    assert not real_file.is_symlink()


def test_is_active_false_when_never_activated(provider, font_file):
    assert not provider.is_active(str(font_file))
