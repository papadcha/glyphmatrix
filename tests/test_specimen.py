from click.testing import CliRunner

from glyphmatrix.cli.main import fontctl
from glyphmatrix.core.specimen import collect, export_specimen

from .fonbuilder import build_test_fon
from .fontbuilder import build_test_font

LATIN = {cp: f"g{cp:x}" for cp in map(ord, "The quickbrownfxjmpsvtlazydg0123456789") if cp != ord("A")}


def _folder(root):
    font_dir = root / "Acme" / "Test Sans" / "v1.00"
    font_dir.mkdir(parents=True)
    build_test_font(font_dir / "Test Sans Regular.ttf", family="Test Sans", style="Test Sans",
                    extra_codepoints=LATIN)
    build_test_font(font_dir / "Test Sans Bold.ttf", family="Test Sans", style="Bold",
                    extra_codepoints=LATIN)
    dingbats = root / "Acme" / "Dings" / "No Version"
    dingbats.mkdir(parents=True)
    build_test_font(dingbats / "Dings.ttf", family="Dings", extra_codepoints={0x2605: "star"})
    build_test_fon(root / "raster.fon")
    return root


def test_collect_labels_groups_and_fallbacks(tmp_path):
    entries = {e.path.name: e for e in collect(_folder(tmp_path / "fonts"))}

    assert entries["Test Sans Regular.ttf"].label == "Test Sans"
    assert entries["Test Sans Bold.ttf"].label == "Test Sans Bold"
    assert entries["Test Sans Bold.ttf"].group == "Acme"
    assert entries["Dings.ttf"].sample == "A★"
    assert entries["Dings.ttf"].note == "shows the font's own characters"
    assert entries["raster.fon"].sample is None


def test_export_writes_a_pdf(tmp_path):
    path, fonts, pages = export_specimen(_folder(tmp_path / "fonts"), tmp_path / "out.pdf")

    assert (fonts, pages) == (4, 1)
    assert path.read_bytes().startswith(b"%PDF")


def test_many_fonts_flow_onto_more_pages(tmp_path):
    root = tmp_path / "fonts"
    root.mkdir()
    for i in range(40):
        build_test_font(root / f"f{i}.ttf", family=f"Font {i:02d}", extra_codepoints=LATIN)

    _, fonts, pages = export_specimen(root, tmp_path / "out.pdf")

    assert fonts == 40
    assert pages >= 3


def test_cli_specimen(tmp_path):
    result = CliRunner().invoke(fontctl, ["specimen", str(_folder(tmp_path / "fonts")), str(tmp_path / "s.pdf")])

    assert result.exit_code == 0, result.output
    assert "4 fonts, 1 page)" in result.output
