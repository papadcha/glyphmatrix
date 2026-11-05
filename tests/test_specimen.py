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


def test_symbol_only_fonts_use_the_symbol_charmap(tmp_path):
    from fontTools.ttLib import TTFont
    from fontTools.ttLib.tables._c_m_a_p import cmap_format_4

    root = tmp_path / "fonts"
    root.mkdir()
    path = build_test_font(root / "dings.ttf", family="Dings")
    font = TTFont(path)
    table = cmap_format_4(4)
    table.platformID, table.platEncID, table.language = 3, 0, 0
    table.cmap = {0xF041: "A"}
    font["cmap"].tables = [table]
    font.save(path)

    entry = collect(root)[0]

    assert (entry.sample, entry.encoding, entry.note) == ("\uf041", "symb", "symbol font")
    _, fonts, _ = export_specimen(root, tmp_path / "out.pdf")
    assert fonts == 1


def test_top_level_fonts_get_no_heading(tmp_path):
    root = tmp_path / "fonts"
    (root / "Fam" / "v1.00").mkdir(parents=True)
    build_test_font(root / "Fam" / "v1.00" / "a.ttf", extra_codepoints=LATIN)

    assert collect(root)[0].group == ""


def test_samples_are_sized_by_ink_and_trimmed_by_words(tmp_path):
    from glyphmatrix.core.specimen import MIN_GLYPH, TARGET_GLYPH, _fit_font

    small = build_test_font(tmp_path / "small.ttf", a_glyph_size=300, extra_codepoints=LATIN)
    big = build_test_font(tmp_path / "big.ttf", a_glyph_size=900, extra_codepoints=LATIN)

    font_small, _ = _fit_font(small, "A", 2000)
    font_big, _ = _fit_font(big, "A", 2000)
    for font in (font_small, font_big):
        box = font.getbbox("A")
        assert abs((box[3] - box[1]) - TARGET_GLYPH) <= 3
    assert font_small.size > font_big.size

    font, text = _fit_font(big, "A A A A A A A A A A A A A A A A A A A A", 300)
    box = font.getbbox("A")
    assert box[3] - box[1] >= MIN_GLYPH - 2
    assert font.getlength(text) <= 300
    assert text.endswith("A") and set(text) <= {"A", " "}


def test_word_art_fonts_show_their_letters(tmp_path):
    from fontTools.ttLib import TTFont

    root = tmp_path / "fonts"
    root.mkdir()
    letters = {ord(c): c for c in "abcdefgh"}
    path = build_test_font(root / "words.ttf", family="Back to School", extra_codepoints=letters)
    font = TTFont(path)
    for c in "abcdefgh":  # 300-unit-tall drawings, 1500 units wide: phrases, not letters
        font["hmtx"][c] = (1500, 0)
    font.save(path)

    entry = collect(root)[0]

    assert (entry.sample, entry.note) == ("abcdefgh", "word-art font")
