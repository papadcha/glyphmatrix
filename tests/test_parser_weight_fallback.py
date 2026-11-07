import pytest

from glyphmatrix.core.parser import _weight_from_style, parse_font_file

from .fontbuilder import build_test_font


@pytest.mark.parametrize(
    "style,expected",
    [
        ("Black", 900),
        ("Heavy Italic", 900),
        ("Ultra", 900),
        ("Demi", 600),
        ("DemiBold", 600),
        ("Semi Bold Italic", 600),
        ("Bold", 700),
        ("BOLD", 700),
        ("ExtraBold", 800),
        ("Extra-Bold", 800),
        ("XBold", 800),
        ("Ultra Bold", 800),
        ("Thin", 100),
        ("Hairline", 100),
        ("Light", 300),
        ("ExtraLight", 200),
        ("Ultra Light Italic", 200),
        ("Medium", 500),
        ("Extra Condensed Bold", 700),
        ("BoldUltraCondensed", 700),
    ],
)
def test_weight_from_style(style, expected):
    assert _weight_from_style(style) == expected


@pytest.mark.parametrize(
    "style",
    [None, "", "Regular", "Italic", "Book", "Extra Condensed", "UltraExpanded", "Extra", "Bold Light"],
)
def test_weight_from_style_names_no_weight(style):
    assert _weight_from_style(style) is None


@pytest.mark.parametrize(
    "style,os2_weight,expected,from_style",
    [
        ("Black", 400, 900, True),
        ("Bold", 400, 700, True),
        ("Black", 900, 900, False),  # set value: no change
        ("Black Italic", 400, 900, True),
        ("Thin Bold", 400, 400, False),  # conflicting weights: no guess
        ("Roman", 400, 400, False),  # names the regular weight: nothing to fix
    ],
)
def test_parse_weight_fallback_cases(tmp_path, style, os2_weight, expected, from_style):
    path = build_test_font(tmp_path / "f.ttf", style=style, weight=os2_weight)

    parsed = parse_font_file(path)

    assert parsed.weight == expected
    assert (parsed.metadata or {}).get("weight_source") == ("style_name" if from_style else None)


def test_default_weight_class_falls_back_to_style_name(tmp_path):
    path = build_test_font(tmp_path / "f.ttf", style="Black")  # usWeightClass left at 400

    parsed = parse_font_file(path)

    assert parsed.weight == 900
    assert parsed.metadata["weight_source"] == "style_name"
    assert parsed.metadata["os2_weight_class"] == 400


def test_explicit_weight_class_is_kept(tmp_path):
    # Charter Black ships with usWeightClass 700; a set value is trusted.
    path = build_test_font(tmp_path / "f.ttf", family="Charter", style="Black", weight=700)

    parsed = parse_font_file(path)

    assert parsed.weight == 700
    assert parsed.metadata is None


def test_regular_style_keeps_400_without_metadata(tmp_path):
    parsed = parse_font_file(build_test_font(tmp_path / "f.ttf", style="Regular"))

    assert parsed.weight == 400
    assert parsed.metadata is None


def test_width_only_style_keeps_400(tmp_path):
    parsed = parse_font_file(build_test_font(tmp_path / "f.ttf", style="Extra Condensed"))

    assert parsed.weight == 400


@pytest.mark.parametrize("legacy,expected", [(1, 100), (3, 300), (5, 500), (7, 700), (9, 900)])
def test_legacy_1_to_9_weight_class_is_scaled(tmp_path, legacy, expected):
    parsed = parse_font_file(build_test_font(tmp_path / "f.ttf", style="Regular", weight=legacy))

    assert parsed.weight == expected
    assert parsed.metadata["weight_source"] == "os2_1_to_9_scale"
    assert parsed.metadata["os2_weight_class"] == legacy


def test_legacy_4_is_normal_so_style_name_still_applies(tmp_path):
    parsed = parse_font_file(build_test_font(tmp_path / "f.ttf", style="Black", weight=4))

    assert parsed.weight == 900
    assert parsed.metadata["weight_source"] == "style_name"
    assert parsed.metadata["os2_weight_class"] == 4  # the raw value from the file


@pytest.mark.parametrize("weight", [100, 250, 950, 1000])
def test_weight_class_outside_1_to_9_is_not_scaled(tmp_path, weight):
    parsed = parse_font_file(build_test_font(tmp_path / "f.ttf", style="Regular", weight=weight))

    assert parsed.weight == weight
    assert parsed.metadata is None
