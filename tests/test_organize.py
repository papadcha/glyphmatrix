import csv
import json
import shutil
from pathlib import Path

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
    assert version_label("Converted by ALLTYPE", "(c) 1999 Nick Curtis") == ("1999", True)
    assert version_label(None, None) == ("No Version", False)


def test_plan_builds_vendor_family_version_layout(tmp_path):
    root = _messy_folder(tmp_path / "fonts")

    plan = {p.source.name: p for p in plan_organize(root)}

    assert plan["ARIMO-BOLD.TTF"].destination == root / "Monotype/Arimo/v1.23/Arimo Bold.ttf"
    assert plan["andlso.ttf"].destination == root / "Glyph Systems/Andalus/v5.92/Andalus Regular.ttf"
    assert plan["DOSAPP.FON"].destination == root / "Microsoft/Terminal/1991/Terminal Regular.fon"
    assert "copyright names several parties" in plan["andlso.ttf"].flags
    assert "no version; folder uses copyright year" in plan["DOSAPP.FON"].flags
    assert all(p.destination.relative_to(root).as_posix().isascii() for p in plan.values())
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
    assert rows["Microsoft/Terminal/1991/Terminal Regular.fon"]["Copyright years"] == "1991"

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
    assert "-> Monotype/Arimo/v1.23/Arimo Bold.ttf" in dry.output.replace("\\", "/")  # native separators
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

    targets = sorted(p.destination.relative_to(root).as_posix() for p in plan_organize(root))

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


def test_repeated_spaces_collapse_in_paths(tmp_path):
    root = tmp_path / "fonts"
    root.mkdir()
    build_test_font(root / "a.ttf", family="2Peas Blocks  Circles", manufacturer="X", version="Version 1.00")

    assert plan_organize(root)[0].destination == root / "X/2Peas Blocks Circles/v1.00/2Peas Blocks Circles Regular.ttf"


def test_version_label_ignores_numbers_glued_to_words():
    assert version_label("2peas Sweet Pea", None) == ("No Version", False)
    assert version_label("2peas Sweet Pea", "Typeface © Melissa Baxter, 2002.") == ("2002", True)
    assert version_label("Version 2", None) == ("v2", False)
    assert version_label("Version 2; 2009", None) == ("v2", False)


def test_apply_case_modes():
    from glyphmatrix.core.organize import apply_case

    assert apply_case("2Peas Sweet Pea Regular", "as-is") == "2Peas Sweet Pea Regular"
    assert apply_case("2Peas Sweet Pea Regular", "sentence") == "2peas sweet pea regular"
    assert apply_case("KH Dot Hibiya 24", "sentence") == "Kh dot hibiya 24"
    assert apply_case("MOonbeams Regular", "title") == "Moonbeams Regular"
    assert apply_case("Arimo Bold", "lower") == "arimo bold"


def test_case_applies_to_family_folder_and_file_name(tmp_path):
    root = tmp_path / "fonts"
    root.mkdir()
    build_test_font(root / "a.ttf", family="PEArennial", manufacturer="X", version="Version 1.00")

    item = plan_organize(root, case="sentence")[0]

    assert item.destination == root / "X/Pearennial/v1.00/Pearennial regular.ttf"


def test_cli_case_option(tmp_path):
    root = _messy_folder(tmp_path / "fonts")

    result = CliRunner().invoke(fontctl, ["--db", str(tmp_path / "x.db"), "organize", str(root),
                                          "--case", "sentence"])

    out = result.output.replace("\\", "/")  # the CLI prints native separators
    assert "-> Monotype/Arimo/v1.23/Arimo bold.ttf" in out
    assert "-> Glyph Systems/Andalus/v5.92/Andalus regular.ttf" in out


def test_names_equal_after_recasing_do_not_collide(tmp_path):
    root = tmp_path / "fonts"
    root.mkdir()
    build_test_font(root / "a.ttf", family="Foo", manufacturer="X", version="Version 1.00")
    build_test_font(root / "b.ttf", family="FOO", manufacturer="X", version="Version 1.00", extra_glyph=True)

    names = sorted(p.destination.name for p in plan_organize(root, case="sentence"))

    assert names == ["Foo regular (2).ttf", "Foo regular.ttf"]


def _family_folder(root):
    root.mkdir()
    sub = root / "Flea Market"
    sub.mkdir()
    for i, name in enumerate(["2Peas Flea Market", "2Peas Flea Market Block Regular",
                              "2Peas Flea Market Block Irregular"]):
        build_test_font(sub / f"{name}.ttf", family=name, style=name, manufacturer="X",
                        version="Version 1.00", a_glyph_size=500 + i)
    other = root / "Vintage"
    other.mkdir()
    build_test_font(other / "v.ttf", family="2Peas Vintage", manufacturer="X", version="Version 1.00", a_glyph_size=601)
    build_test_font(other / "d.ttf", family="2peas dreamland", manufacturer="X", version="Version 1.00", a_glyph_size=602)
    return root


def test_fonts_extending_a_name_in_one_folder_become_one_family(tmp_path):
    root = _family_folder(tmp_path / "fonts")

    targets = sorted(p.destination.relative_to(root).as_posix() for p in plan_organize(root))

    assert targets == [
        "X/2Peas Flea Market/v1.00/2Peas Flea Market Block Irregular.ttf",
        "X/2Peas Flea Market/v1.00/2Peas Flea Market Block Regular.ttf",
        "X/2Peas Flea Market/v1.00/2Peas Flea Market Regular.ttf",
        "X/2Peas Vintage/v1.00/2Peas Vintage Regular.ttf",
        "X/2peas dreamland/v1.00/2peas dreamland Regular.ttf",
    ]


def test_family_grouping_needs_the_same_source_folder(tmp_path):
    root = tmp_path / "fonts"
    (root / "a").mkdir(parents=True)
    (root / "b").mkdir()
    build_test_font(root / "a/x.ttf", family="Silly", manufacturer="X", version="Version 1.00")
    build_test_font(root / "b/y.ttf", family="Silly Fill-In", manufacturer="X", version="Version 1.00", a_glyph_size=650)

    families = sorted(p.family for p in plan_organize(root))

    assert families == ["Silly", "Silly Fill-In"]


def test_case_variants_of_one_name_merge_and_grouping_can_be_disabled(tmp_path):
    root = tmp_path / "fonts"
    (root / "Flower Girl").mkdir(parents=True)
    build_test_font(root / "Flower Girl/a.ttf", family="2Peas Flower Girl", manufacturer="X", version="Version 1.00")
    build_test_font(root / "Flower Girl/b.ttf", family="2Peas flower girl", manufacturer="X",
                    version="Version 1.00", a_glyph_size=650)

    assert {p.family for p in plan_organize(root)} == {"2Peas Flower Girl"}
    assert {p.family for p in plan_organize(root, group_families=False)} == {"2Peas Flower Girl", "2Peas flower girl"}


def test_abbreviated_styles_join_their_family(tmp_path):
    from glyphmatrix.core.organize import _combine_style, _parse_style_tokens

    assert _parse_style_tokens("MedCon") == ["Medium", "Condensed"]
    assert _parse_style_tokens("ExtLig") == ["Extra Light"]
    assert _parse_style_tokens("EE") is None
    assert _parse_style_tokens("EEMed") is None
    assert _combine_style(["Condensed"], "Bold") == "Bold Condensed"
    assert _combine_style(["Medium"], "Italic") == "Medium Italic"

    root = tmp_path / "fonts"
    root.mkdir()
    specs = [
        ("t.ttf", "AvantGarGotItcT", "Regular"), ("tb.ttf", "AvantGarGotItcT", "Bold"),
        ("tmed.ttf", "AvantGarGotItcTMed", "Italic"), ("tdemcon.ttf", "AvantGarGotItcTDemCon", "Regular"),
        ("tcon.ttf", "AvantGarGotItcTCon", "Bold"), ("tee.ttf", "AvantGarGotItcTEE", "Regular"),
        ("teemed.ttf", "AvantGarGotItcTEEMed", "Regular"), ("l.ttf", "AvantGarGotItcL", "Regular"),
    ]
    for i, (name, family, style) in enumerate(specs):
        build_test_font(root / name, family=family, style=style, manufacturer="URW",
                        version="Version 1.005", a_glyph_size=500 + i)

    targets = {p.source.name: p.destination.relative_to(root).as_posix() for p in plan_organize(root)}

    assert targets["tmed.ttf"] == "URW/AvantGarGotItcT/v1.005/AvantGarGotItcT Medium Italic.ttf"
    assert targets["tdemcon.ttf"] == "URW/AvantGarGotItcT/v1.005/AvantGarGotItcT Demi Condensed.ttf"
    assert targets["tcon.ttf"] == "URW/AvantGarGotItcT/v1.005/AvantGarGotItcT Bold Condensed.ttf"
    assert targets["tee.ttf"] == "URW/AvantGarGotItcTEE/v1.005/AvantGarGotItcTEE Regular.ttf"
    assert targets["teemed.ttf"] == "URW/AvantGarGotItcTEE/v1.005/AvantGarGotItcTEE Medium.ttf"
    assert targets["l.ttf"] == "URW/AvantGarGotItcL/v1.005/AvantGarGotItcL Regular.ttf"


def test_inventory_catalogs_without_moving(tmp_path):
    from glyphmatrix.core.organize import write_inventory

    root = tmp_path / "Two Peas in a Bucket"
    series = root / "2Peas Blocks" / "2Peas Blocks - Baby" / "v1.00"
    series.mkdir(parents=True)
    build_test_font(series / "2Peas Blocks - Baby Regular.ttf", family="2Peas Blocks - Baby",
                    style="2Peas Blocks - Baby", version="Version 1.00",
                    copyright="Typeface © Melissa Baxter, 2002. All Rights Reserved")
    before = sorted(str(p) for p in root.rglob("*"))

    out, count = write_inventory(root, root / "2Peas Catalog.csv", vendor="Two Peas in a Bucket")

    assert count == 1
    assert sorted(str(p) for p in root.rglob("*") if p != out) == before
    with out.open(encoding="utf-8-sig") as fh:
        row = next(csv.DictReader(fh))
    assert row["Vendor"] == "Two Peas in a Bucket"
    assert row["Style"] == "Regular"
    assert row["Version folder"] == "v1.00"
    assert row["Copyright years"] == "2002"
    assert row["Path"] == "2Peas Blocks/2Peas Blocks - Baby/v1.00/2Peas Blocks - Baby Regular.ttf"


def test_cli_inventory(tmp_path):
    root = _messy_folder(tmp_path / "fonts")

    result = CliRunner().invoke(fontctl, ["inventory", str(root), str(tmp_path / "inv.csv")])

    assert result.exit_code == 0, result.output
    assert "(3 fonts)" in result.output
    assert (root / "ARIMO-BOLD.TTF").exists()


def test_identical_file_already_in_destination_is_a_duplicate(tmp_path):
    lib = tmp_path / "library"
    _messy_folder(tmp_path / "first")
    apply_organize(plan_organize(tmp_path / "first", lib), tmp_path / "first", lib)
    # Hand-arranged afterwards: moved into a series folder.
    series = lib / "Monotype" / "Series"
    series.mkdir()
    shutil.move(str(lib / "Monotype/Arimo"), str(series / "Arimo"))

    new = tmp_path / "new"
    new.mkdir()
    shutil.copy(series / "Arimo/v1.23/Arimo Bold.ttf", new / "copy of arimo.ttf")
    # Same family, style and version but different content: not a duplicate.
    build_test_font(new / "other arimo.ttf", family="Arimo", style="Bold",
                    manufacturer="Monotype Imaging Inc.", version="Version 1.23", a_glyph_size=777)

    plan = {p.source.name: p for p in plan_organize(new, lib)}

    assert plan["copy of arimo.ttf"].action == "duplicate"
    assert [f.replace("\\", "/") for f in plan["copy of arimo.ttf"].flags] == [
        "already in destination: Monotype/Series/Arimo/v1.23/Arimo Bold.ttf"]
    assert plan["other arimo.ttf"].action == "move"
    assert plan["other arimo.ttf"].destination == lib / "Monotype/Arimo/v1.23/Arimo Bold.ttf"


def test_in_place_organize_does_not_see_its_own_files_as_duplicates(tmp_path):
    root = _messy_folder(tmp_path / "fonts")

    assert {p.action for p in plan_organize(root)} == {"move"}


def test_undo_continues_past_a_failed_move_and_keeps_db_in_step(tmp_path, monkeypatch):
    from glyphmatrix.core import organize as organize_mod

    root = tmp_path / "fonts"
    root.mkdir()
    for style in ("Regular", "Bold", "Italic"):
        build_test_font(root / f"arimo-{style}.ttf", family="Arimo", style=style,
                        manufacturer="Monotype Imaging Inc.", version="Version 1.23")
    conn = connect(tmp_path / "lib.db")
    init_schema(conn)
    ingest_directory(conn, root)
    result = apply_organize(plan_organize(root), root, conn=conn)

    real_move = organize_mod._move_verified

    def flaky(src, dst, expected_hash):
        if dst.name == "arimo-Bold.ttf":
            raise OSError("disk hiccup")
        real_move(src, dst, expected_hash)

    monkeypatch.setattr(organize_mod, "_move_verified", flaky)
    restored, problems = undo_organize(result.undo_log, conn=conn)

    assert restored == 2
    assert len(problems) == 1 and "disk hiccup" in problems[0]
    paths = {r[0] for r in conn.execute("SELECT path FROM font_files")}
    assert all(Path(p).exists() for p in paths)
    assert str(root / "arimo-Regular.ttf") in paths


def _two_arimo_in_db(tmp_path):
    root = tmp_path / "fonts"
    root.mkdir()
    for style in ("Regular", "Bold"):
        build_test_font(root / f"arimo-{style}.ttf", family="Arimo", style=style,
                        manufacturer="Monotype Imaging Inc.", version="Version 1.23")
    conn = connect(tmp_path / "lib.db")
    init_schema(conn)
    ingest_directory(conn, root)
    plan = plan_organize(root)
    target = next(p.destination for p in plan if p.destination.name.endswith("Bold.ttf"))
    return root, conn, plan, target


def _plant_stale_row(conn, target):
    """A row left by an earlier scan of the destination; the file is gone from disk."""
    cur = conn.execute(
        "INSERT INTO font_files (path, filename, content_hash, source) VALUES (?, ?, 'old', 'user')",
        (str(target), target.name),
    )
    conn.commit()
    return cur.lastrowid


def test_stale_db_row_at_destination_is_replaced_with_a_warning(tmp_path):
    root, conn, plan, target = _two_arimo_in_db(tmp_path)
    _plant_stale_row(conn, target)

    result = apply_organize(plan, root, conn=conn)

    assert result.moved == 2
    assert result.failure is None
    assert result.catalog.exists()
    assert any("stale DB row" in w and "Rescan recommended" in w for w in result.warnings)
    paths = {r[0] for r in conn.execute("SELECT path FROM font_files")}
    assert len(paths) == 2 and all(Path(p).exists() for p in paths)


def test_stale_db_row_with_dependencies_is_kept_and_reported(tmp_path):
    root, conn, plan, target = _two_arimo_in_db(tmp_path)
    stale_id = _plant_stale_row(conn, target)
    conn.execute("INSERT INTO activations (font_file_id, platform, state) VALUES (?, 'macos', 'installed')",
                 (stale_id,))
    conn.commit()

    result = apply_organize(plan, root, conn=conn)

    assert result.moved == 2
    assert result.failure is None
    assert result.catalog.exists()
    assert any("has dependencies" in w for w in result.warnings)
    assert conn.execute("SELECT 1 FROM font_files WHERE id = ?", (stale_id,)).fetchone()


def test_db_failure_rolls_back_db_and_moves_files_back(tmp_path):
    root, conn, plan, _ = _two_arimo_in_db(tmp_path)
    before = sorted(tuple(r) for r in conn.execute("SELECT path, filename FROM font_files"))
    conn.execute(
        "CREATE TRIGGER boom BEFORE UPDATE ON font_files WHEN NEW.filename = 'Arimo Bold.ttf' "
        "BEGIN SELECT RAISE(ABORT, 'boom'); END"
    )
    names_before = sorted(p.name for p in root.iterdir())

    result = apply_organize(plan, root, conn=conn)

    assert result.failure and "boom" in result.failure
    assert result.moved == 0
    assert result.catalog is None
    assert sorted(p.name for p in root.iterdir()) == names_before
    assert sorted(tuple(r) for r in conn.execute("SELECT path, filename FROM font_files")) == before


def test_cli_exits_nonzero_and_prints_warnings(tmp_path):
    root, conn, plan, target = _two_arimo_in_db(tmp_path)
    _plant_stale_row(conn, target)
    conn.close()
    runner = CliRunner()
    db = ["--db", str(tmp_path / "lib.db")]

    done = runner.invoke(fontctl, [*db, "organize", str(root), "--apply"])
    assert done.exit_code == 0, done.output
    assert "warning: replaced stale DB row" in done.output


def _arimo_pair(root):
    root.mkdir()
    for style in ("Regular", "Bold"):
        build_test_font(root / f"arimo-{style}.ttf", family="Arimo", style=style,
                        manufacturer="Monotype Imaging Inc.", version="Version 1.23")


def test_organize_updates_db_rows_scanned_with_a_relative_path(tmp_path, monkeypatch):
    root = tmp_path / "fonts"
    _arimo_pair(root)
    conn = connect(tmp_path / "lib.db")
    init_schema(conn)
    monkeypatch.chdir(tmp_path)
    ingest_directory(conn, Path("fonts"))          # stored as "fonts/arimo-Bold.ttf"

    result = apply_organize(plan_organize(root.resolve()), root.resolve(), conn=conn)

    assert result.moved == 2
    paths = [r[0] for r in conn.execute("SELECT path FROM font_files")]
    assert len(paths) == 2
    assert all(Path(p).exists() for p in paths)    # today: still the old relative paths


def test_organize_updates_db_rows_scanned_through_a_symlink(tmp_path):
    real = tmp_path / "real"
    _arimo_pair(real)
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    conn = connect(tmp_path / "lib.db")
    init_schema(conn)
    ingest_directory(conn, link)                   # stored as ".../link/arimo-Bold.ttf"

    result = apply_organize(plan_organize(real), real, conn=conn)

    assert result.moved == 2
    paths = [r[0] for r in conn.execute("SELECT path FROM font_files")]
    assert len(paths) == 2
    assert all(Path(p).exists() for p in paths)


def _three_arimo(root):
    root.mkdir()
    for style in ("Regular", "Bold", "Italic"):
        build_test_font(root / f"arimo-{style}.ttf", family="Arimo", style=style,
                        manufacturer="Monotype Imaging Inc.", version="Version 1.23")


def test_files_missing_from_the_library_give_one_aggregate_warning(tmp_path):
    root = tmp_path / "fonts"
    _three_arimo(root)
    conn = connect(tmp_path / "lib.db")
    init_schema(conn)                                  # library exists but was never scanned

    result = apply_organize(plan_organize(root), root, conn=conn)

    assert result.moved == 3
    assert len([w for w in result.warnings if "not found in the library" in w]) == 1
    assert any(w.startswith("3 moved file(s) not found in the library") for w in result.warnings)


def test_cli_json_includes_the_not_in_library_warning(tmp_path):
    root = tmp_path / "fonts"
    _three_arimo(root)
    conn = connect(tmp_path / "lib.db")
    init_schema(conn)
    conn.close()

    out = CliRunner().invoke(fontctl, ["--db", str(tmp_path / "lib.db"), "organize", str(root),
                                       "--apply", "--json"])

    assert out.exit_code == 0, out.output
    warnings = json.loads(out.stdout)["result"]["warnings"]
    assert any(w.startswith("3 moved file(s) not found in the library") for w in warnings)


def test_cli_undo_prints_problems_to_stderr_and_exits_nonzero(tmp_path, monkeypatch):
    from glyphmatrix.core import organize as organize_mod

    root = tmp_path / "fonts"
    _three_arimo(root)
    result = apply_organize(plan_organize(root), root)
    real_move = organize_mod._move_verified

    def flaky(src, dst, expected_hash):
        if dst.name == "arimo-Bold.ttf":
            raise OSError("disk hiccup")
        real_move(src, dst, expected_hash)

    monkeypatch.setattr(organize_mod, "_move_verified", flaky)

    out = CliRunner().invoke(fontctl, ["--db", str(tmp_path / "none.db"), "organize-undo",
                                       str(result.undo_log)])

    assert out.exit_code == 1
    assert "restored 2" in out.stdout
    assert "could not restore" in out.stderr and "disk hiccup" in out.stderr
    assert "could not restore" not in out.stdout


# --- apply_organize: failures around the move must never lose a file or leave an untracked copy ---

def test_undo_log_write_failure_keeps_the_original(tmp_path, monkeypatch):
    from glyphmatrix.core import organize as organize_mod

    root = tmp_path / "fonts"
    _three_arimo(root)
    real_writer = csv.writer

    class FailingWriter:
        def __init__(self, fh, *args, **kwargs):
            self._w = real_writer(fh, *args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._w, name)

        def writerow(self, row):
            row = list(row)                       # DictWriter hands over a generator
            if row and str(row[0]).endswith("arimo-Bold.ttf"):
                raise OSError(28, "No space left on device")
            return self._w.writerow(row)

    monkeypatch.setattr(organize_mod.csv, "writer", FailingWriter)

    result = apply_organize(plan_organize(root), root)

    assert (result.moved, result.errors) == (2, 1)
    assert (root / "arimo-Bold.ttf").exists()
    assert not list(root.rglob("Arimo Bold.ttf"))
    with result.undo_log.open(encoding="utf-8") as fh:
        assert len(list(csv.DictReader(fh))) == 2


def test_partial_copy_is_removed_when_copy_fails(tmp_path, monkeypatch):
    from glyphmatrix.core import organize as organize_mod

    root = tmp_path / "fonts"
    _three_arimo(root)
    real_copy = organize_mod.shutil.copy2

    def half_copy(src, dst, **kw):
        if Path(src).name == "arimo-Bold.ttf":
            Path(dst).write_bytes(b"truncated")
            raise OSError(5, "I/O error")
        return real_copy(src, dst, **kw)

    monkeypatch.setattr(organize_mod.shutil, "copy2", half_copy)

    result = apply_organize(plan_organize(root), root)

    assert (result.moved, result.errors) == (2, 1)
    assert (root / "arimo-Bold.ttf").exists()
    assert not list(root.rglob("Arimo Bold.ttf"))


def test_copy_is_removed_when_the_original_cannot_be_deleted(tmp_path, monkeypatch):
    root = tmp_path / "fonts"
    _three_arimo(root)
    real_unlink = Path.unlink

    def read_only_source(self, *a, **kw):
        if self.name == "arimo-Bold.ttf":
            raise PermissionError(13, "Permission denied")
        return real_unlink(self, *a, **kw)

    monkeypatch.setattr(Path, "unlink", read_only_source)

    result = apply_organize(plan_organize(root), root)

    assert (result.moved, result.errors) == (2, 1)
    assert (root / "arimo-Bold.ttf").exists()
    assert not list(root.rglob("Arimo Bold.ttf"))      # no untracked copy left behind


def test_a_failing_prune_is_a_warning_not_a_crash(tmp_path, monkeypatch):
    from glyphmatrix.core import organize as organize_mod

    root = tmp_path / "fonts"
    _three_arimo(root)
    conn = connect(tmp_path / "lib.db")
    init_schema(conn)
    ingest_directory(conn, root)

    def broken_prune(start, stop):
        raise OSError(13, "Permission denied")

    monkeypatch.setattr(organize_mod, "_prune_empty_dirs", broken_prune)

    result = apply_organize(plan_organize(root), root, conn=conn)

    assert result.moved == 3
    assert result.catalog.exists()
    assert any("could not remove" in w for w in result.warnings)
    paths = {r[0] for r in conn.execute("SELECT path FROM font_files")}
    assert len(paths) == 3 and all(Path(p).exists() for p in paths)


def test_undo_reads_a_log_with_non_utf8_file_names(tmp_path):
    log = tmp_path / "_organize-test.csv"
    odd = "/nas/caf\udce9.ttf"                          # a Latin-1 byte, as surrogateescape
    with log.open("w", encoding="utf-8", errors="surrogateescape", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["original_path", "new_path", "sha256"])
        w.writerow([odd, "/nas/Vendor/Cafe/v1/Cafe Regular.ttf", "0" * 64])

    restored, problems = undo_organize(log)            # must not raise UnicodeDecodeError

    assert restored == 0
    assert len(problems) == 1


def test_undo_ignores_a_log_row_whose_move_never_happened(tmp_path):
    from glyphmatrix.core import organize as organize_mod

    root = tmp_path / "fonts"
    root.mkdir()
    font = build_test_font(root / "arimo.ttf", family="Arimo")
    log = tmp_path / "_organize-test.csv"
    with log.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["original_path", "new_path", "sha256"])
        w.writerow([str(font), str(root / "Vendor/Arimo/v1/Arimo Regular.ttf"), organize_mod._sha256(font)])

    restored, problems = undo_organize(log)

    assert (restored, problems) == (0, [])
    assert font.exists()


# --- stale DB row at the destination: derived data goes with it, user state blocks the delete ---

def _library_with_a_stale_scanned_row(tmp_path):
    """Two fonts to organize, plus a row from a real scan (glyphs and all) of a file that
    has since been deleted and whose path is exactly where the Bold will land."""
    root, gone = tmp_path / "fonts", tmp_path / "gone"
    _arimo_pair(root)
    gone.mkdir()
    build_test_font(gone / "old.ttf", family="Other", manufacturer="X", version="Version 9.00")
    conn = connect(tmp_path / "lib.db")
    init_schema(conn)
    ingest_directory(conn, tmp_path)
    plan = plan_organize(root)
    target = next(p.destination for p in plan if p.destination.name.endswith("Bold.ttf"))
    stale_id = conn.execute("SELECT id FROM font_files WHERE filename = 'old.ttf'").fetchone()[0]
    conn.execute("UPDATE font_files SET path = ?, filename = ? WHERE id = ?",
                 (str(target), target.name, stale_id))
    conn.execute("INSERT INTO validation_issues (font_file_id, severity, issue_type, detail) "
                 "VALUES (?, 'info', 'test', 'x')", (stale_id,))
    conn.commit()
    (gone / "old.ttf").unlink()
    assert conn.execute("SELECT COUNT(*) FROM font_glyphs WHERE font_file_id = ?", (stale_id,)).fetchone()[0] > 0
    return root, conn, plan, target, stale_id


def _count(conn, table, stale_id):
    return conn.execute(f"SELECT COUNT(*) FROM {table} WHERE font_file_id = ?", (stale_id,)).fetchone()[0]


def test_stale_scanned_row_and_its_derived_data_are_deleted(tmp_path):
    root, conn, plan, target, stale_id = _library_with_a_stale_scanned_row(tmp_path)

    result = apply_organize(plan, root, conn=conn)

    assert result.moved == 2 and result.failure is None
    assert target.exists()
    assert conn.execute("SELECT 1 FROM font_files WHERE id = ?", (stale_id,)).fetchone() is None
    assert _count(conn, "font_glyphs", stale_id) == 0
    assert _count(conn, "validation_issues", stale_id) == 0
    assert conn.execute("SELECT COUNT(*) FROM font_files WHERE path = ?", (str(target),)).fetchone()[0] == 1
    assert any("stale DB row" in w and "Rescan recommended" in w for w in result.warnings)


def test_stale_scanned_row_with_an_activation_is_kept_whole(tmp_path):
    root, conn, plan, target, stale_id = _library_with_a_stale_scanned_row(tmp_path)
    glyphs = _count(conn, "font_glyphs", stale_id)
    conn.execute("INSERT INTO activations (font_file_id, platform, state) VALUES (?, 'macos', 'active')",
                 (stale_id,))
    conn.commit()

    result = apply_organize(plan, root, conn=conn)

    assert result.moved == 2 and result.failure is None
    assert target.exists() and result.catalog.exists()
    assert any("has dependencies" in w and "Rescan recommended" in w for w in result.warnings)
    assert conn.execute("SELECT 1 FROM font_files WHERE id = ?", (stale_id,)).fetchone()
    assert _count(conn, "activations", stale_id) == 1
    assert _count(conn, "font_glyphs", stale_id) == glyphs          # nothing deleted piecemeal
    assert _count(conn, "validation_issues", stale_id) == 1


def test_stale_scanned_row_in_a_package_is_kept_whole(tmp_path):
    root, conn, plan, target, stale_id = _library_with_a_stale_scanned_row(tmp_path)
    glyphs = _count(conn, "font_glyphs", stale_id)
    package_id = conn.execute("INSERT INTO packages (name) VALUES ('Pack')").lastrowid
    conn.execute("INSERT INTO package_files (package_id, font_file_id) VALUES (?, ?)", (package_id, stale_id))
    conn.commit()

    result = apply_organize(plan, root, conn=conn)

    assert result.moved == 2 and result.failure is None
    assert target.exists() and result.catalog.exists()
    assert any("has dependencies" in w and "Rescan recommended" in w for w in result.warnings)
    assert conn.execute("SELECT 1 FROM font_files WHERE id = ?", (stale_id,)).fetchone()
    assert _count(conn, "package_files", stale_id) == 1
    assert _count(conn, "font_glyphs", stale_id) == glyphs
    assert _count(conn, "validation_issues", stale_id) == 1


def test_failure_while_deleting_derived_data_rolls_everything_back(tmp_path):
    root, conn, plan, target, stale_id = _library_with_a_stale_scanned_row(tmp_path)
    names_before = sorted(p.name for p in root.iterdir())
    rows_before = sorted(tuple(r) for r in conn.execute("SELECT id, path FROM font_files"))
    glyphs = _count(conn, "font_glyphs", stale_id)
    conn.execute("CREATE TRIGGER boom BEFORE DELETE ON font_glyphs BEGIN SELECT RAISE(ABORT, 'boom'); END")

    result = apply_organize(plan, root, conn=conn)

    assert result.failure and "boom" in result.failure
    assert result.moved == 0 and result.catalog is None
    assert sorted(p.name for p in root.iterdir()) == names_before        # files are back
    assert sorted(tuple(r) for r in conn.execute("SELECT id, path FROM font_files")) == rows_before
    assert _count(conn, "font_glyphs", stale_id) == glyphs


def test_size_grouping_keeps_the_style_of_non_regular_members(tmp_path):
    root = tmp_path / "fonts"
    root.mkdir()
    for name, style, extra in (("KH Dot Hibiya 24", "Regular", False), ("KH Dot Hibiya 24", "Bold", True),
                               ("KH Dot Hibiya 32", "Regular", False)):
        build_test_font(root / f"{name} {style}.ttf", family=name, style=style, manufacturer="X",
                        version="Version 1.00", extra_glyph=extra, a_glyph_size=500 + len(name) + len(style))

    plan = plan_organize(root)

    targets = sorted(p.destination.relative_to(root).as_posix() for p in plan)
    assert targets == [
        "X/KH Dot Hibiya/v1.00/KH Dot Hibiya 24 Bold.ttf",
        "X/KH Dot Hibiya/v1.00/KH Dot Hibiya 24.ttf",
        "X/KH Dot Hibiya/v1.00/KH Dot Hibiya 32.ttf",
    ]
    assert not any("name already taken" in f for p in plan for f in p.flags)


# --- active fonts are never moved: the system font folder holds a link to the old path ---

def _activated(tmp_path, state="active", platform="windows"):
    root = tmp_path / "fonts"
    _three_arimo(root)
    conn = connect(tmp_path / "lib.db")
    init_schema(conn)
    ingest_directory(conn, root)
    bold_id = conn.execute("SELECT id FROM font_files WHERE filename = 'arimo-Bold.ttf'").fetchone()[0]
    conn.execute("INSERT INTO activations (font_file_id, platform, state) VALUES (?, ?, ?)",
                 (bold_id, platform, state))
    conn.commit()
    return root, conn, bold_id


def test_active_font_is_planned_as_active_and_left_alone(tmp_path):
    root, conn, bold_id = _activated(tmp_path)

    plan = plan_organize(root, conn=conn)
    actions = {p.source.name: p.action for p in plan}
    result = apply_organize(plan, root, conn=conn)

    assert actions == {"arimo-Bold.ttf": "active", "arimo-Italic.ttf": "move", "arimo-Regular.ttf": "move"}
    bold = next(p for p in plan if p.source.name == "arimo-Bold.ttf")
    assert bold.destination is None and any("deactivate" in f for f in bold.flags)
    assert (result.moved, result.skipped_active, result.errors) == (2, 1, 0)
    assert (root / "arimo-Bold.ttf").exists()
    assert conn.execute("SELECT path FROM font_files WHERE id = ?", (bold_id,)).fetchone()[0].endswith("arimo-Bold.ttf")
    assert conn.execute("SELECT state FROM activations WHERE font_file_id = ?", (bold_id,)).fetchone()[0] == "active"


def test_activation_on_any_platform_blocks_the_move(tmp_path):
    root, conn, _ = _activated(tmp_path, platform="linux")

    plan = plan_organize(root, conn=conn)

    assert [p.action for p in plan if p.source.name == "arimo-Bold.ttf"] == ["active"]


def test_installed_but_not_active_font_moves_normally(tmp_path):
    root, conn, _ = _activated(tmp_path, state="installed")

    result = apply_organize(plan_organize(root, conn=conn), root, conn=conn)

    assert (result.moved, result.skipped_active) == (3, 0)


def test_without_a_library_nothing_is_treated_as_active(tmp_path):
    root, conn, _ = _activated(tmp_path)

    assert {p.action for p in plan_organize(root)} == {"move"}


def test_cli_reports_active_fonts_in_text_and_json(tmp_path):
    root, conn, _ = _activated(tmp_path)
    conn.close()
    runner = CliRunner()
    db = ["--db", str(tmp_path / "lib.db")]

    dry = runner.invoke(fontctl, [*db, "organize", str(root)])
    assert dry.exit_code == 0, dry.output
    assert "2 to move, 1 active (skipped, deactivate first)" in dry.output
    assert "[active]" in dry.output

    applied = runner.invoke(fontctl, [*db, "organize", str(root), "--apply", "--json"])
    assert applied.exit_code == 0, applied.output
    result = json.loads(applied.stdout)["result"]
    assert result["moved"] == 2 and result["skipped_active"] == 1


# --- the catalog is written after every file has moved: it must not take the run down with it ---

def test_catalog_survives_a_non_utf8_file_name(tmp_path):
    from glyphmatrix.core.organize import PlannedMove, write_catalog
    from glyphmatrix.core.parser import parse_font_file

    dest = tmp_path / "dest"
    parsed = parse_font_file(build_test_font(tmp_path / "f.ttf", family="Cafe"))
    odd_source = Path("/nas/caf\udce9.ttf")                    # Latin-1 byte on a UTF-8 system
    item = PlannedMove(odd_source, dest / "X/Cafe/v1/Cafe Regular.ttf", "move", vendor="X", family="Cafe",
                       style="Regular", version_label="v1", parsed=parsed)
    item.flags.append(f"identical to {odd_source}")
    (dest / "X/Cafe/v1").mkdir(parents=True)

    catalog = write_catalog([item], dest)                      # must not raise UnicodeEncodeError

    assert catalog.exists()
    assert not list(dest.glob("*.tmp"))
    write_catalog([], dest)                                    # and it reads back on the next run
    assert catalog.exists()


def test_catalog_failure_is_a_warning_and_leaves_no_temp_file(tmp_path, monkeypatch):
    from glyphmatrix.core import organize as organize_mod

    root = tmp_path / "fonts"
    _three_arimo(root)
    conn = connect(tmp_path / "lib.db")
    init_schema(conn)
    ingest_directory(conn, root)

    def locked(src, dst):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(organize_mod.os, "replace", locked)

    result = apply_organize(plan_organize(root), root, conn=conn)

    assert result.moved == 3 and result.failure is None
    assert result.catalog is None
    assert any("_Font Catalog.csv" in w and "Permission denied" in w for w in result.warnings)
    assert not list(root.glob("*.tmp"))
    paths = {r[0] for r in conn.execute("SELECT path FROM font_files")}
    assert len(paths) == 3 and all(Path(p).exists() for p in paths)


def test_plan_with_a_shared_destination_is_rejected_and_nothing_moves(tmp_path):
    root = _messy_folder(tmp_path / "fonts")
    plan = plan_organize(root)
    moves = [i for i in plan if i.action == "move"]
    moves[1].destination = Path(str(moves[0].destination).upper())   # same file on a case-insensitive disk
    before = sorted(p.name for p in root.iterdir())

    result = apply_organize(plan, root)

    assert result.failure and "rejected" in result.failure
    assert any("duplicate destination" in w for w in result.warnings)
    assert result.moved == 0
    assert sorted(p.name for p in root.iterdir()) == before


def test_plan_over_an_existing_file_is_rejected(tmp_path):
    root = _messy_folder(tmp_path / "fonts")
    plan = plan_organize(root)
    target = next(i for i in plan if i.action == "move").destination
    target.parent.mkdir(parents=True)
    target.write_bytes(b"someone else's file")

    result = apply_organize(plan, root)

    assert result.failure and result.moved == 0
    assert any("destination already exists" in w for w in result.warnings)
    assert target.read_bytes() == b"someone else's file"


def test_manifest_lists_every_move_with_its_hash(tmp_path):
    root = _messy_folder(tmp_path / "fonts")
    plan = plan_organize(root)

    result = apply_organize(plan, root)

    manifest = next(root.glob("_manifest-*.jsonl"))
    rows = [json.loads(line) for line in manifest.read_text().splitlines()]
    assert len(rows) == result.moved == 3
    assert {r["sha256"] for r in rows} == {i.content_hash for i in plan if i.action == "move"}


def test_same_file_name_with_different_content_is_not_a_duplicate(tmp_path):
    # RULES A10: a name proves nothing; only the content does.
    root = tmp_path / "fonts"
    (root / "a").mkdir(parents=True)
    (root / "b").mkdir()
    build_test_font(root / "a/SpectNext Regular.otf", family="SpectNext", style="Regular", manufacturer="X")
    build_test_font(root / "b/SpectNext Regular.otf", family="SpectNext Colour", style="Regular", manufacturer="X")

    plan = plan_organize(root)

    assert [i.action for i in plan] == ["move", "move"]
    assert len({i.content_hash for i in plan}) == 2


def test_uppercase_extension_is_scanned_and_no_font_lands_outside_a_vendor_folder(tmp_path):
    # RULES A8 + A9: absolute source path, upper-case extension.
    root = (tmp_path / "fonts").resolve()
    root.mkdir()
    build_test_font(root / "LOUD.TTF", family="Loud", style="Regular", manufacturer="Acme")
    build_test_font(root / "nomanufacturer.ttf", family="Quiet", style="Regular")

    plan = plan_organize(root)

    assert len(plan) == 2
    for item in plan:
        assert item.vendor
        assert item.destination.relative_to(root).parts[0] == item.vendor
        assert len(item.destination.relative_to(root).parts) >= 4
