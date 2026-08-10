from PIL import Image

from glyphmatrix.core.renderer import render_text_preview, render_waterfall_preview

from .fontbuilder import build_test_font


def test_render_text_preview_produces_nonblank_image(tmp_path):
    font_path = build_test_font(tmp_path / "test.ttf")
    out_path = tmp_path / "preview.png"

    result = render_text_preview(font_path, "A", out_path, font_size=72)

    assert result == out_path
    assert out_path.exists()

    image = Image.open(out_path)
    colors = image.getcolors(maxcolors=1_000_000)
    assert len(colors) > 1  # not a blank white canvas


def test_render_text_preview_scales_with_font_size(tmp_path):
    font_path = build_test_font(tmp_path / "test.ttf")

    small = render_text_preview(font_path, "A", tmp_path / "small.png", font_size=12)
    large = render_text_preview(font_path, "A", tmp_path / "large.png", font_size=72)

    assert Image.open(small).size < Image.open(large).size


def test_render_waterfall_preview_stacks_multiple_sizes(tmp_path):
    font_path = build_test_font(tmp_path / "test.ttf")

    single = render_text_preview(font_path, "A", tmp_path / "single.png", font_size=72)
    waterfall = render_waterfall_preview(
        font_path, tmp_path / "waterfall.png", text="A", sizes=(12, 24, 48, 72)
    )

    single_height = Image.open(single).size[1]
    waterfall_height = Image.open(waterfall).size[1]
    assert waterfall_height > single_height

    image = Image.open(waterfall)
    colors = image.getcolors(maxcolors=1_000_000)
    assert len(colors) > 1
