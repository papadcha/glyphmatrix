from glyphmatrix.core.scanner import scan_directory
from glyphmatrix.core.specimen import collect

from .fontbuilder import build_test_font


def test_hidden_and_nas_system_files_are_skipped(tmp_path):
    root = tmp_path / "Fonts"
    (root / "Acme").mkdir(parents=True)
    build_test_font(root / "Acme" / "Real.ttf")
    (root / "Acme" / "._Real.ttf").write_bytes(b"\x00\x05\x16\x07AppleDouble")
    for folder in ("#recycle", "@eaDir", ".Trashes", "Acme/@eaDir/Real.ttf"):
        (root / folder).mkdir(parents=True, exist_ok=True)
        build_test_font(root / folder / "Deleted.ttf")

    assert [p.relative_to(root).as_posix() for p in scan_directory(root)] == ["Acme/Real.ttf"]
    assert [e.path.name for e in collect(root)] == ["Real.ttf"]


def test_a_root_inside_a_hidden_folder_still_works(tmp_path):
    root = tmp_path / ".hidden" / "Fonts"
    root.mkdir(parents=True)
    build_test_font(root / "Real.ttf")

    assert [p.name for p in scan_directory(root)] == ["Real.ttf"]
