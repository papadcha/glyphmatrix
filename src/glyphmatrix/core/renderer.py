from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DEFAULT_TEXT = "The quick brown fox jumps over the lazy dog 0123456789"
WATERFALL_SIZES = (12, 18, 24, 36, 48, 72)
MARGIN = 20
BACKGROUND = "white"
FOREGROUND = "black"


def render_text_preview(
    font_file_path: str | Path, text: str, out_path: str | Path, font_size: int = 72
) -> Path:
    """Render `text` at `font_size` using the given font file, exported as a
    PNG. Canvas size comes from the actual rendered bounding box rather than
    a guessed constant — font metrics vary too much across families/sizes
    for a fixed canvas to avoid clipping or excess whitespace."""
    font = ImageFont.truetype(str(font_file_path), font_size)

    measuring_draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    bbox = measuring_draw.textbbox((0, 0), text, font=font)
    width = (bbox[2] - bbox[0]) + 2 * MARGIN
    height = (bbox[3] - bbox[1]) + 2 * MARGIN

    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.text((MARGIN - bbox[0], MARGIN - bbox[1]), text, font=font, fill=FOREGROUND)

    out_path = Path(out_path)
    image.save(out_path)
    return out_path


def render_waterfall_preview(
    font_file_path: str | Path,
    out_path: str | Path,
    text: str = DEFAULT_TEXT,
    sizes: tuple[int, ...] = WATERFALL_SIZES,
) -> Path:
    """Render `text` once per size in `sizes`, stacked vertically — the
    classic font-manager 'waterfall' specimen."""
    measuring_draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))

    lines = []
    max_width = 0
    total_height = MARGIN
    for size in sizes:
        font = ImageFont.truetype(str(font_file_path), size)
        bbox = measuring_draw.textbbox((0, 0), text, font=font)
        line_height = bbox[3] - bbox[1]
        lines.append((font, bbox, line_height))
        max_width = max(max_width, bbox[2] - bbox[0])
        total_height += line_height + MARGIN

    width = max_width + 2 * MARGIN
    image = Image.new("RGB", (width, total_height), BACKGROUND)
    draw = ImageDraw.Draw(image)

    y = MARGIN
    for font, bbox, line_height in lines:
        draw.text((MARGIN - bbox[0], y - bbox[1]), text, font=font, fill=FOREGROUND)
        y += line_height + MARGIN

    out_path = Path(out_path)
    image.save(out_path)
    return out_path
