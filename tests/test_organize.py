import csv
import shutil

from click.testing import CliRunner

from glyphmatrix.cli.main import fontctl
from glyphmatrix.core.database import connect, init_schema
from glyphmatrix.core.ingest import ingest_directory
from glyphmatrix.core.organize import (
    CATALOG_NAME,
    apply_organize,
    plan_organize,
    short_vendor,
    undo_organize,
    version_label,
)

from .fonbuilder import build_test_fon
from .fontbuilder import build_test_font


def _messy_folder(root):
    root.mkdir()
    build_test_font(root / "ARIMO-BOLD.TTF", family="Arimo", style="Bold",
                    manufacturer="Monotype Imaging Inc.", version="Version 1.23")
    build_test_font(root / "andlso.ttf", family="Andalus", vendor_id="Glyf", version="Version 5.92",
                    copyright="Copyright 1993 Glyph Systems, Limited Partnership. Typeface Portions "
                              "(C) The Monotype Corporation All Rights Reserved.")
    build_test_fon(root / "DOSAPP.FON", face="Terminal",
                   copyright="Copyright (C) Microsoft Corp 1991.  All rights reserved.")
    return root


def test_short_vendor():
    assert short_vendor("Monotype Imaging Inc.") == "Monotype"
    assert short_vendor("Ascender Corporation") == "Ascender"
    assert short_vendor("Glyph Systems, Limited Partnership") == "Glyph Systems"
    assert short_vendor("Keitarou Hiraki, Font Silo") == "Font Silo"
    assert short_vendor(None) == "Unknown"


def test_version_label():
    assert version_label("Version 1.23", None) == ("v1.23", False)
    assert version_label("001.000", None) == ("v1.000", False)
    assert version_label("5.0d1", None) == ("v5.0", False)
    assert version_label("Converted by ALLTYPE", "(c) 1999 Nick Curtis") == ("©1999", True)
    assert version_label(None, None) == ("No Version", False)


def test_plan_builds_vendor_family_version_layout(tmp_path):
    root = _messy_folder(tmp_path / "fonts")

    plan = {p.source.name: p for p in plan_organize(root)}

    assert plan["ARIMO-BOLD.TTF"].destination == root / "Monotype/Arimo/v1.23/Arimo Bold.ttf"
    assert plan["andlso.ttf"].destination == root / "Glyph Systems/Andalus/v5.92/Andalus Regular.ttf"
    assert plan["DOSAPP.FON"].destination == root / "Microsoft/Terminal/©1991/Terminal Regular.fon"
    assert "copyright names several parties" in plan["andlso.ttf"].flags
    assert "no version; folder uses copyright year" in plan["DOSAPP.FON"].flags
    assert plan["ARIMO-BOLD.TTF"].flags == []


def test_plan_moves_nothing(tmp_path):
    root = _messy_folder(tmp_path / "fonts")
    before = sorted(p.name for p in root.iterdir())

    plan_organize(root)

    assert sorted(p.name for p in root.iterdir()) == before


def test_apply_moves_writes_catalog_and_undo_restores(tmp_path):
    root = _messy_folder(tmp_path / "fonts")
    originals = sorted(p.name for p in root.iterdir())

    result = apply_organize(plan_organize(root), root)

    assert result.moved == 3
    assert (root / "Monotype/Arimo/v1.23/Arimo Bold.ttf").exists()
    assert not (root / "ARIMO-BOLD.TTF").exists()
    with (root / CATALOG_NAME).open(encoding="utf-8-sig") as fh:
        rows = {r["Path"]: r for r in csv.DictReader(fh)}
    assert rows["Microsoft/Terminal/©1991/Terminal Regular.fon"]["Copyright years"] == "1991"

    restored, problems = undo_organize(result.undo_log)

    assert (restored, problems) == (3, [])
    assert not (root / "Monotype").exists()
    font_names = sorted(p.name for p in root.iterdir() if not p.name.startswith("_"))
    assert font_names == originals


def test_second_run_is_a_no_op(tmp_path):
    root = _messy_folder(tmp_path / "fonts")
    apply_organize(plan_organize(root), root)

    plan = plan_organize(root)

    assert {p.action for p in plan} == {"unchanged"}


def test_duplicates_are_reported_not_moved(tmp_path):
    root = _messy_folder(tmp_path / "fonts")
    (root / "copy").mkdir()
    shutil.copy(root / "ARIMO-BOLD.TTF", root / "copy" / "arimo bold copy.ttf")

    plan = plan_organize(root)
    result = apply_organize(plan, root)

    assert result.duplicates == 1
    assert (root / "copy" / "arimo bold copy.ttf").exists()


def test_name_collision_gets_numbered(tmp_path):
    root = tmp_path / "fonts"
    root.mkdir()
    build_test_font(root / "a.ttf", family="Same", manufacturer="X", version="Version 1.0")
    build_test_font(root / "b.ttf", family="Same", manufacturer="X", version="Version 1.0", extra_glyph=True)

    targets = sorted(p.destination.name for p in plan_organize(root))

    assert targets == ["Same Regular (2).ttf", "Same Regular.ttf"]


def test_separate_destination_and_db_paths_follow(tmp_path):
    root = _messy_folder(tmp_path / "fonts")
    dest = tmp_path / "library"
    conn = connect(tmp_path / "lib.db")
    init_schema(conn)
    ingest_directory(conn, root)

    apply_organize(plan_organize(root, dest), root, dest, conn=conn)

    paths = {r["path"] for r in conn.execute("SELECT path FROM font_files")}
    assert str(dest / "Monotype/Arimo/v1.23/Arimo Bold.ttf") in paths
    assert not any(p.startswith(str(root)) for p in paths)


def test_cli_dry_run_then_apply(tmp_path):
    root = _messy_folder(tmp_path / "fonts")
    runner = CliRunner()
    db = ["--db", str(tmp_path / "lib.db")]

    dry = runner.invoke(fontctl, [*db, "organize", str(root)])
    assert dry.exit_code == 0, dry.output
    assert "-> Monotype/Arimo/v1.23/Arimo Bold.ttf" in dry.output
    assert "dry run: nothing moved" in dry.output
    assert (root / "ARIMO-BOLD.TTF").exists()

    applied = runner.invoke(fontctl, [*db, "organize", str(root), "--apply"])
    assert applied.exit_code == 0, applied.output
    assert "moved 3" in applied.output
    log = next(root.glob("_organize-*.csv"))

    undone = runner.invoke(fontctl, [*db, "organize-undo", str(log)])
    assert "restored 3" in undone.output
    assert (root / "ARIMO-BOLD.TTF").exists()


def test_size_variants_sharing_a_base_are_grouped(tmp_path):
    root = tmp_path / "fonts"
    root.mkdir()
    for name in ("KH Dot Hibiya 24", "KH Dot Hibiya 32", "Bauhaus 93"):
        build_test_font(root / f"{name}.ttf", family=name, manufacturer="X",
                        version="Version 1.00", extra_glyph=name.endswith("32"),
                        a_glyph_size=500 + len(name))

    targets = sorted(str(p.destination.relative_to(root)) for p in plan_organize(root))

    assert targets == [
        "X/Bauhaus 93/v1.00/Bauhaus 93 Regular.ttf",
        "X/KH Dot Hibiya/v1.00/KH Dot Hibiya 24.ttf",
        "X/KH Dot Hibiya/v1.00/KH Dot Hibiya 32.ttf",
    ]


def test_single_copyright_claim_is_not_flagged_as_several(tmp_path):
    root = tmp_path / "fonts"
    root.mkdir()
    build_test_font(root / "a.ttf", copyright="(C)Copyright DynaComware Corp. 2002",
                    vendor_id="DYNA", version="Version 1.00")

    assert plan_organize(root)[0].flags == []


def test_undo_removes_folders_shared_by_several_files(tmp_path):
    root = tmp_path / "fonts"
    root.mkdir()
    for style in ("Regular", "Bold", "Italic"):
        build_test_font(root / f"arimo-{style}.ttf", family="Arimo", style=style,
                        manufacturer="Monotype Imaging Inc.", version="Version 1.23")

    result = apply_organize(plan_organize(root), root)
    restored, problems = undo_organize(result.undo_log)

    assert (restored, problems) == (3, [])
    assert sorted(p.name for p in root.iterdir() if p.is_dir()) == []


def test_font_editor_defaults_are_not_vendors(tmp_path):
    root = tmp_path / "fonts"
    root.mkdir()
    build_test_font(root / "a.ttf", family="2Peas Airplanes", style="2Peas Airplanes",
                    manufacturer="High-Logic", vendor_id="HL  ", version="Version 2",
                    copyright="Typeface © (your company). 2006. All Rights Reserved")
    build_test_font(root / "b.ttf", family="2Peas Angel", vendor_id="MACR", extra_glyph=True,
                    copyright="Generated by Fontographer 4.1", version="Macromedia Fontographer 4.1 2/6/2005")

    plan = {p.source.name: p for p in plan_organize(root)}

    assert plan["a.ttf"].destination == root / "Unknown/2Peas Airplanes/v2/2Peas Airplanes Regular.ttf"
    assert plan["b.ttf"].vendor == "Unknown"
    assert "vendor unknown" in plan["a.ttf"].flags


def test_vendor_spellings_merge_and_options_override(tmp_path):
    root = tmp_path / "fonts"
    root.mkdir()
    build_test_font(root / "a.ttf", family="A", manufacturer="Two Peas in a Bucket", version="Version 1.0")
    build_test_font(root / "b.ttf", family="B", manufacturer="Two Peas in a Bucket", version="Version 1.0")
    build_test_font(root / "c.ttf", family="C", manufacturer="Two Peas In A Bucket", version="Version 1.0")
    build_test_font(root / "d.ttf", family="D", manufacturer="www.twopeasinabucket.com", version="Version 1.0")
    build_test_font(root / "e.ttf", family="E", version="Version 1.0",
                    copyright="Typeface © Melissa Baxter, 2002. All Rights Reserved")

    merged = {p.source.name: p.vendor for p in plan_organize(root)}
    assert merged["c.ttf"] == "Two Peas in a Bucket"
    assert merged["e.ttf"] == "Melissa Baxter"

    aliased = {p.source.name: p for p in plan_organize(
        root, vendor_aliases={"WWW.TWOPEASINABUCKET.COM": "Two Peas in a Bucket"})}
    assert aliased["d.ttf"].vendor == "Two Peas in a Bucket"

    forced = plan_organize(root, vendor="Two Peas in a Bucket")
    assert {p.vendor for p in forced} == {"Two Peas in a Bucket"}
    assert not any("vendor" in f for p in forced for f in p.flags)


def test_catalog_has_designer(tmp_path):
    root = tmp_path / "fonts"
    root.mkdir()
    build_test_font(root / "a.ttf", family="A", manufacturer="X", version="Version 1.0")
    from fontTools.ttLib import TTFont
    font = TTFont(root / "a.ttf")
    font["name"].setName("designed by Melissa Baxter", 9, 3, 1, 0x409)
    font.save(root / "a.ttf")

    apply_organize(plan_organize(root), root)

    with (root / CATALOG_NAME).open(encoding="utf-8-sig") as fh:
        assert next(csv.DictReader(fh))["Designer"] == "Melissa Baxter"


def test_cli_vendor_alias_validation(tmp_path):
    root = _messy_folder(tmp_path / "fonts")

    bad = CliRunner().invoke(fontctl, ["--db", str(tmp_path / "x.db"), "organize", str(root),
                                       "--vendor-alias", "nonsense"])

    assert bad.exit_code != 0
    assert "OLD=NEW" in bad.output
