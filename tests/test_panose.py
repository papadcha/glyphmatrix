from glyphmatrix.core.panose import classify_panose


def test_all_zero_is_unset():
    assert classify_panose((0, 0, 0, 0, 0, 0, 0, 0, 0, 0)) is None


def test_empty_tuple_is_unset():
    assert classify_panose(()) is None


def test_latin_text_serif_style():
    assert classify_panose((2, 11, 5, 3, 2, 2, 2, 2, 2, 4)) == "normal-sans"
    assert classify_panose((2, 2, 5, 3, 2, 2, 2, 2, 2, 4)) == "cove"
    assert classify_panose((2, 15, 5, 3, 2, 2, 2, 2, 2, 4)) == "rounded"


def test_latin_text_any_or_no_fit_serif_style_is_unmapped():
    assert classify_panose((2, 0, 5, 3, 2, 2, 2, 2, 2, 4)) is None
    assert classify_panose((2, 1, 5, 3, 2, 2, 2, 2, 2, 4)) is None


def test_non_latin_text_family_kinds():
    assert classify_panose((3, 0, 0, 0, 0, 0, 0, 0, 0, 0)) == "hand-written"
    assert classify_panose((4, 0, 0, 0, 0, 0, 0, 0, 0, 0)) == "decorative"
    assert classify_panose((5, 0, 0, 0, 0, 0, 0, 0, 0, 0)) == "symbolic"


def test_any_or_no_fit_family_type_is_unmapped():
    assert classify_panose((0, 5, 0, 0, 0, 0, 0, 0, 0, 0)) is None
    assert classify_panose((1, 5, 0, 0, 0, 0, 0, 0, 0, 0)) is None
