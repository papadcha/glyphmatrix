import json
import shutil

from click.testing import CliRunner

from glyphmatrix.cli.main import fontctl
from glyphmatrix.core.compare import compare_paths

from .fontbuilder import build_test_font


def test_same_name_and_version_but_different_outlines(tmp_path):
    a = build_test_font(tmp_path / "Sweet Pea.ttf", family="2Peas Sweet Pea", version="Version 2")
    b = build_test_font(tmp_path / "Sweet Pea-1.ttf", family="2Peas Sweet Pea", version="Version 2",
                        a_glyph_size=650, extra_glyph=True)

    result = compare_paths(a, b)

    assert result.identical is False
    assert result.glyphs.changed == ["A"]
    assert result.glyphs.only_in_b == ["B"]
    assert result.fields == {"glyph_count": (2, 3)}


def test_identical_files(tmp_path):
    a = build_test_font(tmp_path / "a.ttf")
    shutil.copy(a, tmp_path / "b.ttf")

    assert compare_paths(a, tmp_path / "b.ttf").identical is True


def test_cli_compare_files(tmp_path):
    a = build_test_font(tmp_path / "a.ttf", version="Version 2")
    b = build_test_font(tmp_path / "b.ttf", version="Version 2", a_glyph_size=650)

    text = CliRunner().invoke(fontctl, ["compare-files", str(a), str(b)])
    assert text.exit_code == 0, text.output
    assert "changed outline (1): A" in text.output

    as_json = json.loads(CliRunner().invoke(fontctl, ["compare-files", str(a), str(b), "--json"]).output)
    assert as_json["changed"] == ["A"]


def test_compare_explains_when_versions_resolve_to_one_file(tmp_path):
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    build_test_font(fonts / "a.ttf", family="Same", version="Version 2")
    build_test_font(fonts / "b.ttf", family="Same", version="Version 2", a_glyph_size=650)
    db = ["--db", str(tmp_path / "lib.db")]
    CliRunner().invoke(fontctl, [*db, "scan", str(fonts)])

    result = CliRunner().invoke(fontctl, [*db, "compare", "Same", "Regular", "Version 2", "Version 2"])

    assert result.exit_code != 0
    assert "compare-files" in result.output
