from glyphmatrix.core.scanner import scan_directory

from .fontbuilder import build_test_font


def test_scan_directory_finds_font_files_recursively(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf")
    nested = tmp_path / "subfolder"
    nested.mkdir()
    build_test_font(nested / "Arial-Bold.ttf")
    (tmp_path / "readme.txt").write_text("not a font")

    found = {p.name for p in scan_directory(tmp_path)}

    assert found == {"Arial-Regular.ttf", "Arial-Bold.ttf"}


def test_scan_directory_is_case_insensitive_on_extension(tmp_path):
    build_test_font(tmp_path / "weird.TTF")

    found = list(scan_directory(tmp_path))

    assert len(found) == 1
