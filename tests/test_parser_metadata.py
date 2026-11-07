"""Format-specific metadata: FON copyright years / sizes / description, and
TrueType/OpenType collection members."""
import json

from click.testing import CliRunner
from fontTools.ttLib import TTCollection, TTFont

from glyphmatrix.cli.main import fontctl
from glyphmatrix.core.database import connect, init_schema
from glyphmatrix.core.foundry import copyright_years
from glyphmatrix.core.ingest import ingest_directory
from glyphmatrix.core.parser import parse_font_file

from .fonbuilder import build_test_fon
from .fontbuilder import build_test_font


def test_copyright_years():
    assert copyright_years("Copyright (C) Microsoft Corp 1991.  All rights reserved.") == [1991]
    assert copyright_years("(c) 1981, 1982, 1983, 1989 and 1993, Linotype") == [1981, 1982, 1983, 1989, 1993]
    assert copyright_years("Copyright (c) Keitarou Hiraki, Font Silo. 1990-2015") == [1990, 2015]
    assert copyright_years("Version 12345 build 1234567") == []
    assert copyright_years(None) == []


def test_fon_metadata(tmp_path):
    parsed = parse_font_file(build_test_fon(tmp_path / "test.fon"))

    assert parsed.family_name == "Test Raster"
    assert parsed.foundry == "Acme Type"
    assert parsed.metadata == {
        "copyright": "Copyright (C) Acme Type 1991-1993. All rights reserved.",
        "copyright_years": [1991, 1993],
        "description": "Test Raster 8x12",
        "pixel_sizes": ["6x8", "8x12"],
        "resolutions": ["96x96"],
        "charset": "OEM",
        "fnt_version": "2.0",
    }


def test_fon_metadata_skips_empty_fields(tmp_path):
    parsed = parse_font_file(build_test_fon(tmp_path / "test.fon", copyright="", description=""))

    assert parsed.foundry is None
    assert "copyright" not in parsed.metadata
    assert "copyright_years" not in parsed.metadata
    assert "description" not in parsed.metadata


def _build_ttc(tmp_path):
    regular = build_test_font(tmp_path / "a.ttf", family="Test Sans", style="Regular")
    bold = build_test_font(tmp_path / "b.ttf", family="Test Sans", style="Bold")
    collection = TTCollection()
    collection.fonts = [TTFont(regular), TTFont(bold)]
    out = tmp_path / "fonts" / "test.ttc"
    out.parent.mkdir()
    collection.save(out)
    return out


def test_ttc_parses_first_member_and_lists_all(tmp_path):
    parsed = parse_font_file(_build_ttc(tmp_path))

    assert parsed.format == "ttc"
    assert parsed.family_name == "Test Sans"
    assert parsed.style == "Regular"
    assert [(m["index"], m["family"], m["style"]) for m in parsed.metadata["collection"]] == [
        (0, "Test Sans", "Regular"),
        (1, "Test Sans", "Bold"),
    ]


def test_ingest_stores_metadata_and_info_shows_it(tmp_path):
    ttc = _build_ttc(tmp_path)
    build_test_fon(ttc.parent / "raster.fon")
    db = tmp_path / "library.db"
    conn = connect(db)
    init_schema(conn)

    run = ingest_directory(conn, ttc.parent)

    assert (run.files_added, run.errors) == (2, 0)
    stored = conn.execute("SELECT metadata_json FROM font_files WHERE format = 'fon'").fetchone()
    assert json.loads(stored["metadata_json"])["copyright_years"] == [1991, 1993]

    result = CliRunner().invoke(fontctl, ["--db", str(db), "info", "Test Raster"])
    assert result.exit_code == 0, result.output
    assert "copyright: 1991, 1993" in result.output
    assert "description: Test Raster 8x12" in result.output
    assert "bitmap sizes: 6x8, 8x12 px" in result.output

    result = CliRunner().invoke(fontctl, ["--db", str(db), "info", "Test Sans"])
    assert "collection #1: Test Sans Bold" in result.output


def test_version_from_unique_id_when_name_version_has_no_number(tmp_path):
    font_path = build_test_font(
        tmp_path / "test.ttf",
        version="Glyph Systems 5-April-96",
        unique_id="2.000;Glyf;AZ Topaz;2018;TR4-4.0.1.5095",
        font_revision=2.0,
    )

    parsed = parse_font_file(font_path)

    assert parsed.version == "2.000"
    assert parsed.metadata == {
        "version_string": "Glyph Systems 5-April-96",
        "version_source": "unique_id+head",
    }


def test_version_fallback_needs_head_to_agree(tmp_path):
    font_path = build_test_font(
        tmp_path / "test.ttf",
        version="Converted by some tool",
        unique_id="2.000;Vend;Name",
        font_revision=1.0,
    )

    parsed = parse_font_file(font_path)

    assert parsed.version == "Converted by some tool"
    assert parsed.metadata is None


def test_version_fallback_ignores_tool_unique_ids(tmp_path):
    # FontForge writes "FontForge 2.0 : Name : date" and head 1.0 by default.
    font_path = build_test_font(
        tmp_path / "test.ttf",
        version="This is a protected webfont",
        unique_id="FontForge 2.0 : Kharabeesh : 16-11-2011",
        font_revision=1.0,
    )

    assert parse_font_file(font_path).version == "This is a protected webfont"


def test_name_version_with_number_is_kept(tmp_path):
    font_path = build_test_font(
        tmp_path / "test.ttf", version="Version 1.23", unique_id="9.000;X;Y", font_revision=9.0
    )

    assert parse_font_file(font_path).version == "Version 1.23"


def test_single_font_with_ttc_extension_parses_as_plain_font(tmp_path):
    # No "ttcf" header: TTCollection() would reject it; TTFont() reads it.
    path = build_test_font(tmp_path / "single.ttc", family="Solo", style="Bold")

    parsed = parse_font_file(path)

    assert (parsed.family_name, parsed.style, parsed.format) == ("Solo", "Bold", "ttc")
    assert "collection" not in (parsed.metadata or {})


def test_features_of_a_ttc_read_the_first_member(tmp_path):
    from glyphmatrix.core.opentype_features import list_features

    assert list_features(_build_ttc(tmp_path)) == []  # used to raise TTLibFileIsCollectionError
