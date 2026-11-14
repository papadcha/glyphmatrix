"""Type 1 header text: no font fixtures needed."""
from glyphmatrix.core import parser
from glyphmatrix.core.parser import _t1_text, parse_font_file


def test_t1_text_reads_mac_roman_and_octal_escapes_and_keeps_latin1():
    assert _t1_text("designed by Lopetz96:b\\237ro destruct") == "designed by Lopetz96:büro destruct"
    assert _t1_text("Paccer is designed by Lopetz, b\x9fro destruct") == "Paccer is designed by Lopetz, büro destruct"
    assert _t1_text("Copyright © 1995 Deniart Systems") == "Copyright © 1995 Deniart Systems"
    assert _t1_text(None) is None


def test_type1_is_opened_as_latin1_and_the_notice_becomes_the_copyright(monkeypatch, tmp_path):
    seen = {}

    class FakeT1:
        def __init__(self, path, encoding="ascii"):
            seen["encoding"] = encoding
            self.font = {"FontInfo": {"FamilyName": "Alchemy", "Notice": "Copyright © 1997 Deniart Systems."}}

        def parse(self):
            pass

    monkeypatch.setattr(parser, "T1Font", FakeT1)
    monkeypatch.setattr(parser, "_parse_type1_glyphs", lambda t1: ([], 0))
    path = tmp_path / "alchemy.pfb"
    path.write_bytes(b"x")
    parsed = parse_font_file(path)
    assert seen["encoding"] == "latin-1"
    assert parsed.copyright == "Copyright © 1997 Deniart Systems."


def test_buro_destruct_spellings_share_one_holder():
    from glyphmatrix.core.foundry import resolve_foundry
    from glyphmatrix.core.tidy import clean_holder, load_rules
    rules = load_rules()
    for spelling in ("buro destruct Berne capital", "büro destruct bern", "buro destruct berne captial",
                     "Lopetz, Buro Destruct", "Peter Korsman, buro destruct berne capital"):
        assert clean_holder(spelling, rules) == "Büro Destruct", spelling
    # no (c) sign in the old Type 1 header: the pattern names the publisher
    assert resolve_foundry(None, None, "Paccer is designed by Lopetz, büro destruct, Distribution: APPLY")[0] == "Büro Destruct"
