import pytest
from click.testing import CliRunner

from glyphmatrix.cli.main import fontctl
from glyphmatrix.core.organize import apply_organize, undo_organize
from glyphmatrix.core.parser import parse_font_file
from glyphmatrix.core.tidy import clean_holder, holder_from_claims, load_rules, plan_tidy, resolve_holder

from .fontbuilder import build_test_font

RULES = load_rules()


@pytest.mark.parametrize("raw, expected", [
    # RULES E2: canonical corrections
    ("(URW)++", "URW"),
    ("199 Southern Software, Inc", "Southern Software, Inc"),
    ("Bigelow & Holmes", "Bigelow & Holmes Inc"),
    ("Sharif FarsiWeb, Inc", "Sharif FarsiWeb"),
    ("ACES CONSULTANTS, Bangalore", "ACES Consultants"),
    ("AlQalam http://www.alqalam.net", "AlQalam"),
    ("Pat Snyder, 1797 Ross Inlet", "Pat Snyder"),
    ("Attari Qadri, Faisalabad", "Ishtiaq Ali Attari Qadri"),
    ("From the WSI-Font(s) Collection", "WSI-Fonts"),
    ("cleev@o2.pl - Author- Cleev - Sebastian Kostrubala", "Sebastian Kostrubala"),
    ("__ Sora Sagano", "Sora Sagano"),
    ("SoftMaker Software GmbH", "SoftMaker"),
    ("Typodermic Do not distribute", "Typodermic"),
    ("Meir Sadan -meir@sadan.com-, Oketz Fonts", "Meir Sadan"),
    ("Ray Larabie -rlarabie@hotmail.com", "Ray Larabie"),
    ("! from A. Carr", "A. Carr"),
    ("MÂns Greb‰ck", "Mans Greback"),
    ("HanYang I&C Co.,LTD", "HanYang I&C Co., Ltd"),
    ("The Comfortaa Project Authors (https---github.com/x)", "The Comfortaa Project Authors"),
    ("Brendel Informatik & SoftMaker", "SoftMaker/Brendel Informatik & SoftMaker"),
    ("Elfring Soft Fonts, All Rights Reserved", "Elfring Soft Fonts"),
    ('j4p4n with Reserved Font Name "sloppy-joetsu"', "j4p4n"),
    ("Brendel Informatik Cologne FRG & SoftMaker", "SoftMaker/Brendel Informatik & SoftMaker"),
    ("Southern Software, Inc", "Southern Software, Inc"),          # suffix is kept
    # RULES B2 #3-5 and E3: not publishers
    ("Fontographer 4.1", None), ("Converted by ALLTYPE", None), ("Made with Scanahand", None),
    ("Freeware! from somebody", None), ("ShareWare $10", None), ("Licensed under SIL OFL", None),
    ("Libertinage is based on Linux Libertine", None), ("stereotype designed and encoded by X", None),
    ("Generated", None), ("Version 2.0", None), ("v2.0", None), ("Notice not found in original font", None),
    ("FOR VIEWING ONLY, DO NOT DISTRIBUTE", None), ("http---www.foo.com", None), ("12,24,36", None),
    ("SIL", None), ("", None),
])
def test_clean_holder_follows_the_rules_table(raw, expected):
    assert clean_holder(raw, RULES) == expected


@pytest.mark.parametrize("text, expected", [
    # last modifier in a chain is the holder (B2 #6)
    ("Copyright (c) 1989 Adobe Systems. Copyright (c) 2001 Andreas Nolda.", "Andreas Nolda"),
    # "Portions (C) X" is ignored (B2 #1)
    ("Copyright 1993 Glyph Systems, Limited Partnership. Typeface Portions (C) The Monotype Corporation.",
     "Glyph Systems, Limited Partnership"),
    ("Digitized data copyright © 2010, Google Corporation.", "Google Inc"),
    # a claim that is only a tool falls back to the previous real one
    ("Copyright (c) 2005 Foo Fonts. (c) 2007 Fontographer", "Foo Fonts"),
    ("Made with Fontographer", None),
    (None, None),
    # real cases found in the library
    ("Freeware! from A. Carr Remember to vote! If you don't vote, you can't bitch!", "A. Carr"),
    ("Freeware! from somebody else", None),
    ("\\(c\\) 1996 SoftMaker Software GmbH", "SoftMaker"),
    ("(r) (c) 2003 [T\u2010 26] Chicago www.t26.com 773.862.1201".replace("\u2010 ", "\u2010"), "T-26"),
])
def test_holder_from_claims(text, expected):
    assert holder_from_claims(text, RULES)[0] == expected


def test_a_publisher_pattern_names_the_holder_when_the_copyright_sign_is_broken(tmp_path):
    # Fonthead's fonts write "I1997 ..." for the (c) sign: no claim for holder_from_claims to read.
    font = tmp_path / "pesto.ttf"
    build_test_font(font, family="Pesto", style="Regular",
                    copyright="I1997 Ethan Dunham - Fonthead Design - http://www.fonthead.com")
    assert resolve_holder(parse_font_file(font), RULES)[:2] == ("Fonthead Design", "copyright")
    other = tmp_path / "other.ttf"
    build_test_font(other, family="Other", style="Regular", copyright="I1997 Someone Else")
    assert resolve_holder(parse_font_file(other), RULES)[0] is None


def _library(root):
    root.mkdir()
    build_test_font(root / "a.ttf", family="Aldine", style="Bold", version="Version 1.20",
                    copyright="Copyright (c) 1995 Brendel Informatik", manufacturer="SoftMaker Software GmbH")
    build_test_font(root / "a.otf", family="Aldine", style="Bold", version="Version 1.20",
                    copyright="Copyright (c) 1995 Brendel Informatik")
    build_test_font(root / "old.ttf", family="Aldine", style="Bold", version="Version 1.10",
                    copyright="Copyright (c) 1995 Brendel Informatik", a_glyph_size=650)
    build_test_font(root / "tool.ttf", family="Mystery", style="Regular", copyright="Made with Fontographer")
    return root


def test_plan_layout_formats_versions_and_unknown(tmp_path):
    root = _library(tmp_path / "fonts")

    plan = {i.source.name: i for i in plan_tidy(root)}

    assert plan["a.ttf"].destination == root / "Brendel Informatik/Aldine/ttf/Aldine Bold.ttf"
    assert plan["a.otf"].destination == root / "Brendel Informatik/Aldine/otf/Aldine Bold.otf"
    assert plan["old.ttf"].destination == root / "Brendel Informatik/Aldine/ttf/_versions/Aldine Bold (v1.10).ttf"
    assert plan["tool.ttf"].destination == root / "_Unknown/Mystery/Mystery Regular.ttf"
    assert "holder unknown" in plan["tool.ttf"].flags


def test_unreadable_file_goes_to_unknown_broken_and_collections_are_kept_whole(tmp_path):
    root = tmp_path / "fonts"
    root.mkdir()
    (root / "bad.ttf").write_bytes(b"this is not a font at all")

    plan = plan_tidy(root)

    assert plan[0].action == "move"
    assert plan[0].destination == root / "_Unknown/_broken/bad.ttf"


def test_tidy_apply_is_safe_idempotent_and_undoable(tmp_path):
    root = _library(tmp_path / "fonts")
    before = sorted(p.name for p in root.iterdir())

    result = apply_organize(plan_tidy(root), root)

    assert result.failure is None and result.errors == 0 and result.moved == 4
    assert (root / "Brendel Informatik/Aldine/ttf/_versions/Aldine Bold (v1.10).ttf").exists()
    second = plan_tidy(root)
    assert {i.action for i in second} == {"unchanged"}

    restored, problems = undo_organize(result.undo_log)
    assert (restored, problems) == (4, [])
    assert sorted(p.name for p in root.iterdir() if not p.name.startswith("_")) == before


def test_holder_spellings_that_differ_only_in_case_share_one_folder(tmp_path):
    root = tmp_path / "fonts"
    root.mkdir()
    build_test_font(root / "a.ttf", family="A", copyright="Copyright 2000 Vernon Adams")
    build_test_font(root / "b.ttf", family="B", copyright="Copyright 2000 vernon adams", a_glyph_size=650)
    (tmp_path / "out" / "Vernon Adams").mkdir(parents=True)

    plan = plan_tidy(root, tmp_path / "out")

    assert {i.destination.relative_to(tmp_path / "out").parts[0] for i in plan} == {"Vernon Adams"}


def test_cli_tidy_profile_and_user_rules(tmp_path):
    root = _library(tmp_path / "fonts")
    rules = tmp_path / "mine.toml"
    rules.write_text('[holder.exact]\n"brendel informatik" = "Brendel"\n', encoding="utf-8")
    runner = CliRunner()

    out = runner.invoke(fontctl, ["--db", str(tmp_path / "x.db"), "organize", str(root),
                                  "--profile", "tidy", "--rules", str(rules)])

    assert out.exit_code == 0, out.output
    assert "Brendel/Aldine/ttf/Aldine Bold.ttf" in out.output
    assert "dry run" in out.output
    assert (root / "a.ttf").exists()

    bad = runner.invoke(fontctl, ["--db", str(tmp_path / "x.db"), "organize", str(root), "--rules", str(rules)])
    assert bad.exit_code != 0


# --- versions and formats already in the destination -------------------------------------------

def _font(path, revision, version=None, style="Regular", ext_from=None, **kw):
    path.parent.mkdir(parents=True, exist_ok=True)
    return build_test_font(path, family="Fam", style=style, copyright="Copyright (c) 2001 Acme Type",
                           font_revision=revision, version=version or f"Version {revision}",
                           a_glyph_size=600 + int(revision * 10), **kw)


def _library_with(tmp_path, revision, name="Fam Regular.ttf"):
    lib = tmp_path / "lib"
    _font(lib / "Acme Type/Fam" / name, revision)
    return lib


def test_a_newer_version_replaces_the_library_primary_and_the_old_one_steps_aside(tmp_path):
    lib = _library_with(tmp_path, 1.0)
    old_bytes = (lib / "Acme Type/Fam/Fam Regular.ttf").read_bytes()
    _font(tmp_path / "new/Fam.ttf", 2.0)

    plan = plan_tidy(tmp_path / "new", lib)

    by = {i.source.name: i for i in plan if i.action == "move"}
    assert by["Fam.ttf"].destination == lib / "Acme Type/Fam/Fam Regular.ttf"
    assert by["Fam Regular.ttf"].destination == lib / "Acme Type/Fam/_versions/Fam Regular (v1.0).ttf"

    result = apply_organize(plan, tmp_path / "new", lib)

    assert result.failure is None and result.errors == 0
    assert (lib / "Acme Type/Fam/_versions/Fam Regular (v1.0).ttf").read_bytes() == old_bytes
    assert parse_font_file(lib / "Acme Type/Fam/Fam Regular.ttf").version == "Version 2.0"

    restored, problems = undo_organize(result.undo_log)
    assert problems == []
    assert (lib / "Acme Type/Fam/Fam Regular.ttf").read_bytes() == old_bytes


def test_an_older_version_goes_to_versions_and_the_library_is_left_alone(tmp_path):
    lib = _library_with(tmp_path, 3.0)
    _font(tmp_path / "new/Fam.ttf", 1.0)

    plan = plan_tidy(tmp_path / "new", lib)

    assert [i.action for i in plan] == ["move"]
    assert plan[0].destination == lib / "Acme Type/Fam/_versions/Fam Regular (v1.0).ttf"
    assert any("equal or newer" in f for f in plan[0].flags)


def test_a_second_format_gets_a_format_folder_when_the_library_already_has_the_first(tmp_path):
    lib = _library_with(tmp_path, 1.0)
    _font(tmp_path / "new/Fam.otf", 1.1)

    plan = plan_tidy(tmp_path / "new", lib)

    assert plan[0].destination == lib / "Acme Type/Fam/otf/Fam Regular.otf"


def test_versions_that_do_not_sort_as_text_are_ordered_by_head_revision(tmp_path):
    # PingFang: 13.0d1e3 (2.1), 17.d1e2 (2.7), 21.0d1e1 (5.0)
    new = tmp_path / "new"
    _font(new / "a/Fam.ttf", 2.1, version="13.0d1e3")
    _font(new / "b/Fam.ttf", 2.7, version="17.d1e2")
    _font(new / "c/Fam.ttf", 5.0, version="21.0d1e1")

    plan = {i.source.parent.name: i.destination.relative_to(tmp_path / "lib").as_posix()
            for i in plan_tidy(new, tmp_path / "lib")}

    assert plan["c"] == "Acme Type/Fam/Fam Regular.ttf"                   # revision 5.0 is the newest
    assert plan["b"] == "Acme Type/Fam/_versions/Fam Regular (v2.7).ttf"
    assert plan["a"] == "Acme Type/Fam/_versions/Fam Regular (v13.0).ttf"


def test_an_active_library_font_is_never_moved_aside(tmp_path):
    from glyphmatrix.core.database import connect, init_schema
    from glyphmatrix.core.ingest import ingest_directory

    lib = _library_with(tmp_path, 1.0)
    conn = connect(tmp_path / "x.db"); init_schema(conn)
    ingest_directory(conn, lib)
    row = conn.execute("SELECT id FROM font_files").fetchone()[0]
    conn.execute("INSERT INTO activations (font_file_id, platform, state) VALUES (?, 'macos', 'active')", (row,))
    conn.commit()
    _font(tmp_path / "new/Fam.ttf", 2.0)

    plan = plan_tidy(tmp_path / "new", lib, conn=conn)

    assert [i.action for i in plan] == ["move"]
    assert "_versions" in str(plan[0].destination) and any("active" in f for f in plan[0].flags)
