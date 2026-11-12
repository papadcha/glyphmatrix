import struct

import pytest
from fontTools.ttLib import TTCollection, TTFont

from glyphmatrix.core import organize as organize_mod
from glyphmatrix.core.extract import extract_member, member_count
from glyphmatrix.core.organize import apply_organize, undo_organize
from glyphmatrix.core.parser import parse_font_file
from glyphmatrix.core.tidy import plan_tidy

from .fontbuilder import build_test_font


def make_ttc(path, fonts):
    collection = TTCollection()
    collection.fonts = [TTFont(f) for f in fonts]
    collection.save(path)
    return path


def make_dfont(path, blobs):
    """A minimal Mac resource-fork file holding the given fonts as 'sfnt' resources."""
    data, offsets = b"", []
    for blob in blobs:
        offsets.append(len(data))
        data += struct.pack(">I", len(blob)) + blob
    n = len(blobs)
    type_list = struct.pack(">h", 0) + struct.pack(">4shH", b"sfnt", n - 1, 10)
    refs = b"".join(struct.pack(">hHI4x", i, 0xFFFF, off) for i, off in enumerate(offsets))
    name_list_off = 28 + len(type_list) + len(refs)
    header_len = 28
    map_len = header_len + len(type_list) + len(refs)
    header = struct.pack(">4L", 256, 256 + len(data), len(data), map_len)
    rmap = header + b"\0" * 8 + struct.pack(">HH", 28, name_list_off) + type_list + refs
    path.write_bytes(header + b"\0" * (256 - 16) + data + rmap)
    return path


def _two_fonts(tmp_path):
    a = build_test_font(tmp_path / "a.ttf", family="Duo", style="Regular",
                        copyright="Copyright (c) 2001 Duo Foundry")
    b = build_test_font(tmp_path / "b.ttf", family="Duo", style="Bold", a_glyph_size=650,
                        copyright="Copyright (c) 2001 Duo Foundry")
    return a, b


def test_ttc_members_are_extracted_as_standalone_fonts(tmp_path):
    a, b = _two_fonts(tmp_path)
    ttc = make_ttc(tmp_path / "duo.ttc", [a, b])

    assert member_count(ttc) == 2
    out = tmp_path / "m.ttf"
    out.write_bytes(extract_member(ttc, 1))
    assert parse_font_file(out).style == "Bold"
    assert extract_member(ttc, 1) == extract_member(ttc, 1)      # deterministic: the plan's hash holds at apply time


def test_dfont_members_are_extracted(tmp_path):
    a, b = _two_fonts(tmp_path)
    dfont = make_dfont(tmp_path / "duo.dfont", [a.read_bytes(), b.read_bytes()])

    assert member_count(dfont) == 2
    assert extract_member(dfont, 0) == a.read_bytes()
    assert extract_member(dfont, 1) == b.read_bytes()


def _folder_with_collections(tmp_path):
    root = tmp_path / "fonts"
    root.mkdir()
    a, b = _two_fonts(tmp_path)
    make_ttc(root / "duo.ttc", [a, b])
    c = build_test_font(tmp_path / "c.ttf", family="Solo", style="Regular", a_glyph_size=620,
                        copyright="Copyright (c) 1999 Solo Type")
    make_dfont(root / "solo.dfont", [c.read_bytes()])
    return root


def test_collections_are_kept_whole_and_their_fonts_land_in_holder_folders(tmp_path):
    root = _folder_with_collections(tmp_path)

    plan = plan_tidy(root)
    by_action = {}
    for item in plan:
        by_action.setdefault(item.action, []).append(item)

    assert len(by_action["extract"]) == 3
    targets = {i.destination.relative_to(root).as_posix() for i in plan if i.destination}
    assert "Duo Foundry/Duo/Duo Regular.ttf" in targets
    assert "Duo Foundry/Duo/Duo Bold.ttf" in targets
    assert "Solo Type/Solo/Solo Regular.ttf" in targets
    assert "_collections/duo.ttc" in targets and "_collections/solo.dfont" in targets


def test_apply_writes_members_moves_collections_and_undo_reverses_it(tmp_path):
    root = _folder_with_collections(tmp_path)
    original_ttc = (root / "duo.ttc").read_bytes()

    result = apply_organize(plan_tidy(root), root)

    assert result.failure is None and result.errors == 0
    assert (result.extracted, result.moved) == (3, 2)
    assert (root / "Duo Foundry/Duo/Duo Bold.ttf").exists()
    assert (root / "_collections/duo.ttc").read_bytes() == original_ttc
    assert not (root / "duo.ttc").exists()

    restored, problems = undo_organize(result.undo_log)

    assert problems == [] and restored == 5
    assert (root / "duo.ttc").read_bytes() == original_ttc
    assert not (root / "Duo Foundry").exists() and not (root / "Solo Type").exists()


def test_second_run_neither_repeats_nor_numbers_extracted_fonts(tmp_path):
    root = _folder_with_collections(tmp_path)
    apply_organize(plan_tidy(root), root)

    plan = plan_tidy(root)

    assert "extract" not in {i.action for i in plan}
    assert {i.action for i in plan if i.action != "duplicate"} == {"unchanged"}
    assert not any("(2)" in str(i.destination) for i in plan)


def test_a_failed_extraction_leaves_the_collection_where_it_was(tmp_path, monkeypatch):
    root = _folder_with_collections(tmp_path)
    plan = plan_tidy(root)

    def boom(path, index):
        if path.name == "duo.ttc" and index == 1:
            raise OSError("disk on fire")
        return extract_member(path, index)

    monkeypatch.setattr(organize_mod, "extract_member", boom)

    result = apply_organize(plan, root)

    assert (root / "duo.ttc").exists() and not (root / "_collections/duo.ttc").exists()
    assert result.errors == 2                       # the member and the collection that stayed
    assert (root / "_collections/solo.dfont").exists()


def test_an_extracted_font_never_overwrites_an_existing_file(tmp_path):
    root = _folder_with_collections(tmp_path)
    plan = plan_tidy(root)
    victim = next(i.destination for i in plan if i.action == "extract")
    victim.parent.mkdir(parents=True)
    victim.write_bytes(b"precious")

    result = apply_organize(plan, root)

    assert result.failure and result.extracted == 0
    assert victim.read_bytes() == b"precious"
    assert (root / "duo.ttc").exists()


def test_a_collection_named_ttf_is_still_a_collection(tmp_path):
    # PingFang_1.ttf in the real library: a 'ttcf' file with a .ttf extension
    root = tmp_path / "fonts"
    root.mkdir()
    a, b = _two_fonts(tmp_path)
    make_ttc(root / "Pack_1.ttf", [a, b])

    plan = plan_tidy(root)

    extracted = [i for i in plan if i.action == "extract"]
    assert len(extracted) == 2                                  # not read as one single font
    whole = next(i for i in plan if i.action == "move")
    assert whole.destination == root / "_collections/Pack_1.ttc"   # and renamed to what it is
    assert any("named .ttf" in f for f in whole.flags)

    result = apply_organize(plan, root)

    assert result.errors == 0 and result.extracted == 2
    assert (root / "_collections/Pack_1.ttc").read_bytes()[:4] == b"ttcf"
